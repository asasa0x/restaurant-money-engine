/**
 * Live LED / Kitchen Display System (KDS) Board
 * Opens at /led.html?r=<restaurant_id> — auto-refreshes every 3 seconds.
 */

const params = new URLSearchParams(window.location.search);
const restaurantId = (params.get("r") || "").trim();
const initialMode = (params.get("mode") || "").trim().toLowerCase();

const urlToken = params.get("token") || (window.location.hash.includes("token=") ? new URLSearchParams(window.location.hash.substring(1)).get("token") : null);

const isLocalDev =
  (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1") &&
  window.location.port !== "5000";
const API_BASE = isLocalDev ? "http://127.0.0.1:5000" : "";

const PAYMENT_LABELS = {
  cash: "💵 Cash",
  card: "💳 Card",
  easypaisa_jazzcash: "📱 JazzCash/Easypaisa",
  bank_transfer: "🏦 Bank",
};

const DEFAULT_WORKSPACE_EMAIL = "pizzaclub.sargodha@restaurantmoneyengine.com";
const DEFAULT_WORKSPACE_PASS = "PizzaClubSargodha2026!";

const POLL_MS = 3000;

const state = {
  orders: [],
  knownPending: new Set(),
  knownReady: new Set(),
  firstLoad: true,
  showItems: true,
  soundEnabled: true,
  token: urlToken || localStorage.getItem("rme_auth_token") || "",
};

if (urlToken) {
  try { localStorage.setItem("rme_auth_token", urlToken); } catch {}
}

const $ = (id) => document.getElementById(id);

function node(tag, className, text) {
  const el = document.createElement(tag);
  if (className) el.className = className;
  if (text !== undefined) el.textContent = text;
  return el;
}

function formatTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return isNaN(d.getTime()) ? "" : d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function formatElapsed(iso) {
  if (!iso) return "";
  const secs = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 1000));
  if (isNaN(secs)) return "";
  const mins = Math.floor(secs / 60);
  const rem = secs % 60;
  return mins > 0 ? `${mins}m ${rem}s` : `${rem}s`;
}

function playChime(freq = 880) {
  if (!state.soundEnabled) return;
  try {
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (!AudioCtx) return;
    const ctx = new AudioCtx();
    const osc = ctx.createOscillator();
    osc.frequency.value = freq;
    osc.connect(ctx.destination);
    osc.start();
    setTimeout(() => { osc.stop(); ctx.close(); }, 260);
  } catch {
    /* ignore audio errors */
  }
}

async function tryAutoConnect() {
  if (state.token && hasKitchenAccess()) return true;
  try {
    const response = await fetch(`${API_BASE}/api/v1/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({
        email: DEFAULT_WORKSPACE_EMAIL,
        password: DEFAULT_WORKSPACE_PASS,
      }),
    });
    const data = await response.json().catch(() => ({}));
    if (response.ok && data.access_token) {
      state.token = data.access_token;
      localStorage.setItem("rme_auth_token", data.access_token);
      if (data.user) localStorage.setItem("rme_auth_user", JSON.stringify(data.user));
      if (data.restaurant) localStorage.setItem("rme_auth_restaurant", JSON.stringify(data.restaurant));
      updateKitchenAuthButton();
      return true;
    }
  } catch {
    /* ignore auto-connect network error */
  }
  return false;
}

function hasKitchenAccess() {
  if (!state.token) return false;
  try {
    const rest = JSON.parse(localStorage.getItem("rme_auth_restaurant") || "null");
    if (rest?.id && restaurantId && rest.id.toLowerCase() !== restaurantId.toLowerCase()) return false;
  } catch {
    /* ignore */
  }
  return true;
}

function updateKitchenAuthButton() {
  const btn = $("led-kitchen-auth-btn");
  if (!btn) return;
  if (hasKitchenAccess()) {
    btn.textContent = "👨‍🍳 Kitchen Active";
    btn.className = "btn btn-primary btn-sm";
  } else {
    btn.textContent = "👨‍🍳 Kitchen Sign In";
    btn.className = "btn btn-secondary btn-sm";
  }
}

async function setOrderStatus(order, status) {
  if (!hasKitchenAccess()) {
    const connected = await tryAutoConnect();
    if (!connected) {
      $("led-auth-modal")?.showModal();
      return;
    }
  }

  // 1. Instant Optimistic UI update (0ms delay!)
  const prevStatus = order.status;
  order.status = status;
  state.lastBoardSignature = state.orders.map((o) => `${o.id}:${o.status}`).join("|");
  playChime(status === "accepted" ? 659 : status === "ready" ? 1046 : 880);
  renderBoard();

  // 2. Persist to backend in background
  try {
    let response = await fetch(`${API_BASE}/api/v1/orders/${encodeURIComponent(order.id)}/status`, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        Authorization: `Bearer ${state.token}`,
      },
      body: JSON.stringify({ status }),
    });
    if (response.status === 401) {
      const reconnected = await tryAutoConnect();
      if (reconnected) {
        response = await fetch(`${API_BASE}/api/v1/orders/${encodeURIComponent(order.id)}/status`, {
          method: "PUT",
          headers: {
            "Content-Type": "application/json",
            Accept: "application/json",
            Authorization: `Bearer ${state.token}`,
          },
          body: JSON.stringify({ status }),
        });
      }
    }
    if (response.status === 401) {
      order.status = prevStatus;
      state.lastBoardSignature = "";
      renderBoard();
      state.token = "";
      localStorage.removeItem("rme_auth_token");
      updateKitchenAuthButton();
      $("led-auth-modal")?.showModal();
      return;
    }
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
  } catch (err) {
    order.status = prevStatus;
    state.lastBoardSignature = "";
    renderBoard();
    $("led-sync-status").textContent = `Status update failed: ${err.message}`;
  }
}

function buildKitchenActions(order) {
  const wrap = node("div", "led-actions");
  const addBtn = (label, cls, nextStatus, confirmMsg = null) => {
    const btn = node("button", `btn btn-sm ${cls}`, label);
    btn.type = "button";
    btn.addEventListener("click", async () => {
      if (confirmMsg && !confirm(confirmMsg)) return;
      btn.disabled = true;
      try {
        await setOrderStatus(order, nextStatus);
      } finally {
        btn.disabled = false;
      }
    });
    wrap.appendChild(btn);
  };

  if (order.status === "pending") {
    addBtn("✓ Accept Order", "btn-primary", "accepted");
    addBtn("✕ Reject", "btn-danger", "cancelled", `Cancel order #${order.code}?`);
  } else if (order.status === "accepted") {
    addBtn("👨‍🍳 Start Preparing", "btn-secondary", "preparing");
    addBtn("✅ Mark Ready", "btn-primary", "ready");
    addBtn("✕ Cancel", "btn-danger", "cancelled", `Cancel order #${order.code}?`);
  } else if (order.status === "preparing") {
    addBtn("✅ Mark Ready", "btn-primary", "ready");
    addBtn("✕ Cancel", "btn-danger", "cancelled", `Cancel order #${order.code}?`);
  } else if (order.status === "ready") {
    addBtn("✔ Mark Completed", "btn-primary", "completed");
  }
  return wrap;
}

function renderColumn(listId, countId, items) {
  const list = $(listId);
  const count = $(countId);
  if (count) count.textContent = String(items.length);
  if (!list) return;

  list.replaceChildren();
  if (items.length === 0) {
    list.appendChild(node("div", "led-empty", "No active orders"));
    return;
  }

  items.forEach((order) => {
    const card = node("div", `led-card led-status-${order.status}`);

    const top = node("div", "led-card-top");
    const tableLabel = order.table_number ? `TABLE ${order.table_number}` : "TAKEAWAY";
    top.appendChild(node("span", "led-table-badge", tableLabel));
    top.appendChild(node("span", "led-code", `#${order.code}`));
    card.appendChild(top);

    const timeRow = node("div", "led-time-row");
    const placed = formatTime(order.created_at);
    const elapsed = formatElapsed(order.created_at);
    const payBase = PAYMENT_LABELS[order.payment_method] || PAYMENT_LABELS.cash;
    const payText = order.payment_ref ? `${payBase} (Ref: ${order.payment_ref})` : payBase;
    timeRow.appendChild(node("span", "", `${payText}${placed ? ` · ${placed}` : ""}`));
    const elapsedSpan = node("span", "led-elapsed", elapsed ? `⏱ ${elapsed}` : "");
    if (order.created_at) elapsedSpan.setAttribute("data-created-at", order.created_at);
    timeRow.appendChild(elapsedSpan);
    card.appendChild(timeRow);

    if (state.showItems && Array.isArray(order.items) && order.items.length) {
      const ul = node("ul", "led-items");
      order.items.forEach((it) => {
        const li = node("li", "");
        li.appendChild(node("strong", "led-qty", `${it.quantity}×`));
        li.appendChild(node("span", "", ` ${it.name}`));
        ul.appendChild(li);
      });
      card.appendChild(ul);
    }

    if (state.showItems && order.notes) {
      card.appendChild(node("div", "led-notes", `📝 ${order.notes}`));
    }

    const actions = buildKitchenActions(order);
    if (actions) card.appendChild(actions);

    list.appendChild(card);
  });
}

function renderBoard() {
  const pending = state.orders.filter((o) => o.status === "pending");
  const preparing = state.orders.filter((o) => o.status === "accepted" || o.status === "preparing");
  const ready = state.orders.filter((o) => o.status === "ready");

  renderColumn("led-list-pending", "led-count-pending", pending);
  renderColumn("led-list-preparing", "led-count-preparing", preparing);
  renderColumn("led-list-ready", "led-count-ready", ready);
}

async function fetchBoard() {
  if (!/^[0-9a-f-]{36}$/i.test(restaurantId)) {
    $("led-sync-status").textContent = "Invalid restaurant link. Open LED screen from the Owner Dashboard.";
    return;
  }

  try {
    const response = await fetch(`${API_BASE}/api/v1/public/restaurants/${encodeURIComponent(restaurantId)}/led`, {
      headers: { Accept: "application/json" },
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);

    if (data.restaurant?.name) {
      $("led-restaurant-name").textContent = `${data.restaurant.name} — Live LED`;
      document.title = `${data.restaurant.name} | Live LED`;
    }

    const incoming = Array.isArray(data.orders) ? data.orders : [];
    const nextPending = new Set(incoming.filter((o) => o.status === "pending").map((o) => o.id));
    const nextReady = new Set(incoming.filter((o) => o.status === "ready").map((o) => o.id));

    if (!state.firstLoad) {
      const hasNewPending = [...nextPending].some((id) => !state.knownPending.has(id));
      const hasNewReady = [...nextReady].some((id) => !state.knownReady.has(id));
      if (hasNewPending) playChime(880);
      else if (hasNewReady) playChime(1046);
    }

    state.knownPending = nextPending;
    state.knownReady = nextReady;
    state.orders = incoming;

    $("led-sync-status").textContent = `Live · ${incoming.length} active order${incoming.length === 1 ? "" : "s"} · Auto-updates every 3s`;

    // Smart DOM diffing: only re-render DOM if orders or statuses actually changed!
    const signature = incoming.map((o) => `${o.id}:${o.status}`).join("|");
    if (state.firstLoad || signature !== state.lastBoardSignature) {
      state.lastBoardSignature = signature;
      renderBoard();
    }
    state.firstLoad = false;
  } catch (err) {
    $("led-sync-status").textContent = `Reconnecting… (${err.message})`;
  }
}

function updateClock() {
  const el = $("led-clock");
  if (el) el.textContent = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function updateElapsedClocks() {
  document.querySelectorAll(".led-elapsed[data-created-at]").forEach((el) => {
    const iso = el.getAttribute("data-created-at");
    if (iso) el.textContent = `⏱ ${formatElapsed(iso)}`;
  });
}

function bindControls() {
  $("led-mode-btn")?.addEventListener("click", (e) => {
    state.showItems = !state.showItems;
    e.target.textContent = state.showItems ? "Mode: Kitchen (Items)" : "Mode: Hall LED (Table Only)";
    renderBoard();
  });

  $("led-sound-btn")?.addEventListener("click", (e) => {
    state.soundEnabled = !state.soundEnabled;
    e.target.textContent = state.soundEnabled ? "🔔 Sound: ON" : "🔕 Sound: OFF";
  });

  $("led-fullscreen-btn")?.addEventListener("click", () => {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen?.().catch(() => {});
    } else {
      document.exitFullscreen?.().catch(() => {});
    }
  });

  $("led-kitchen-auth-btn")?.addEventListener("click", () => {
    if (hasKitchenAccess()) {
      state.token = "";
      localStorage.removeItem("rme_auth_token");
      updateKitchenAuthButton();
      renderBoard();
    } else {
      $("led-auth-error").hidden = true;
      $("led-auth-modal")?.showModal();
    }
  });

  $("led-auth-cancel")?.addEventListener("click", () => $("led-auth-modal")?.close());

  $("led-toggle-password")?.addEventListener("click", (e) => {
    const input = $("led-auth-password");
    if (!input) return;
    const show = input.type === "password";
    input.type = show ? "text" : "password";
    e.currentTarget.textContent = show ? "🙈" : "👁️";
    e.currentTarget.setAttribute("aria-label", show ? "Hide password" : "Show password");
  });

  $("led-auth-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const errEl = $("led-auth-error");
    const submitBtn = $("led-auth-submit");
    errEl.hidden = true;
    submitBtn.disabled = true;
    try {
      const response = await fetch(`${API_BASE}/api/v1/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          email: ($("led-auth-email")?.value || "").trim(),
          password: $("led-auth-password")?.value || "",
        }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.access_token) {
        throw new Error(data.error || "Sign in failed");
      }
      if (restaurantId && data.restaurant?.id && data.restaurant.id !== restaurantId) {
        throw new Error("This account belongs to a different restaurant.");
      }
      state.token = data.access_token;
      localStorage.setItem("rme_auth_token", data.access_token);
      if (data.user) localStorage.setItem("rme_auth_user", JSON.stringify(data.user));
      if (data.restaurant) localStorage.setItem("rme_auth_restaurant", JSON.stringify(data.restaurant));
      $("led-auth-form").reset();
      $("led-auth-modal")?.close();
      updateKitchenAuthButton();
      renderBoard();
    } catch (err) {
      errEl.textContent = err.message || "Sign in failed";
      errEl.hidden = false;
    } finally {
      submitBtn.disabled = false;
    }
  });
}

bindControls();
updateKitchenAuthButton();
if (!hasKitchenAccess()) {
  tryAutoConnect().then(() => {
    updateKitchenAuthButton();
    renderBoard();
  });
}
updateClock();
setInterval(updateClock, 1000);
setInterval(updateElapsedClocks, 1000);
fetchBoard();
setInterval(fetchBoard, POLL_MS);

