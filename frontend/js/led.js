/**
 * Live LED / Kitchen Display System (KDS) Board
 * Opens at /led.html?r=<restaurant_id> — auto-refreshes every 3 seconds.
 */

const params = new URLSearchParams(window.location.search);
const restaurantId = (params.get("r") || "").trim();
const initialMode = (params.get("mode") || "").trim().toLowerCase();

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

const POLL_MS = 3000;

const state = {
  orders: [],
  knownPending: new Set(),
  knownReady: new Set(),
  firstLoad: true,
  showItems: true,
  soundEnabled: true,
  token: localStorage.getItem("rme_auth_token") || "",
};

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

function hasKitchenAccess() {
  if (!state.token) return false;
  try {
    const rest = JSON.parse(localStorage.getItem("rme_auth_restaurant") || "null");
    if (rest?.id && restaurantId && rest.id !== restaurantId) return false;
  } catch {
    /* ignore */
  }
  return true;
}

function updateKitchenAuthButton() {
  const btn = $("led-kitchen-auth-btn");
  if (!btn) return;
  if (hasKitchenAccess()) {
    btn.textContent = "👨‍🍳 Kitchen Active (Sign Out)";
    btn.className = "btn btn-primary btn-sm";
  } else {
    btn.textContent = "👨‍🍳 Kitchen Sign In";
    btn.className = "btn btn-secondary btn-sm";
  }
}

async function setOrderStatus(order, status) {
  if (!hasKitchenAccess()) {
    $("led-auth-modal")?.showModal();
    return;
  }
  try {
    const response = await fetch(`${API_BASE}/api/v1/orders/${encodeURIComponent(order.id)}/status`, {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        Authorization: `Bearer ${state.token}`,
      },
      body: JSON.stringify({ status }),
    });
    if (response.status === 401) {
      state.token = "";
      localStorage.removeItem("rme_auth_token");
      updateKitchenAuthButton();
      renderBoard();
      $("led-auth-modal")?.showModal();
      return;
    }
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
    await fetchBoard();
  } catch (err) {
    $("led-sync-status").textContent = `Status update failed: ${err.message}`;
  }
}

function buildKitchenActions(order) {
  if (!hasKitchenAccess()) return null;
  const wrap = node("div", "led-actions");
  const addBtn = (label, cls, nextStatus, confirmMsg = null) => {
    const btn = node("button", `btn btn-xs ${cls}`, label);
    btn.type = "button";
    btn.addEventListener("click", () => {
      if (confirmMsg && !confirm(confirmMsg)) return;
      btn.disabled = true;
      setOrderStatus(order, nextStatus);
    });
    wrap.appendChild(btn);
  };

  if (order.status === "pending") {
    addBtn("✓ Accept", "btn-primary", "accepted");
    addBtn("✕ Cancel", "btn-danger", "cancelled", `Cancel order #${order.code}?`);
  } else if (order.status === "accepted") {
    addBtn("👨‍🍳 Preparing", "btn-secondary", "preparing");
    addBtn("✅ Mark Ready", "btn-primary", "ready");
    addBtn("✕ Cancel", "btn-danger", "cancelled", `Cancel order #${order.code}?`);
  } else if (order.status === "preparing") {
    addBtn("✅ Mark Ready", "btn-primary", "ready");
    addBtn("✕ Cancel", "btn-danger", "cancelled", `Cancel order #${order.code}?`);
  } else if (order.status === "ready") {
    addBtn("✔ Mark Complete", "btn-primary", "completed");
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
    timeRow.appendChild(node("span", "led-elapsed", elapsed ? `⏱ ${elapsed}` : ""));
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
    state.firstLoad = false;
    state.orders = incoming;

    $("led-sync-status").textContent = `Live · ${incoming.length} active order${incoming.length === 1 ? "" : "s"} · Auto-updates every 3s`;
    renderBoard();
  } catch (err) {
    $("led-sync-status").textContent = `Reconnecting… (${err.message})`;
  }
}

function updateClock() {
  const el = $("led-clock");
  if (el) el.textContent = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
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
if (initialMode === "kitchen" && !hasKitchenAccess()) {
  $("led-auth-modal")?.showModal();
}
updateClock();
setInterval(updateClock, 1000);
setInterval(() => { if (!state.firstLoad) renderBoard(); }, 1000);
fetchBoard();
setInterval(fetchBoard, POLL_MS);

