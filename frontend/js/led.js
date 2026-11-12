/**
 * Live LED / Kitchen Display System (KDS) Board
 * Opens at /led.html?r=<restaurant_id> — auto-refreshes every 3 seconds.
 */

const params = new URLSearchParams(window.location.search);
const restaurantId = (params.get("r") || "").trim();

const isLocalDev =
  (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1") &&
  window.location.port !== "5000";
const API_BASE = isLocalDev ? "http://127.0.0.1:5000" : "";

const POLL_MS = 3000;

const state = {
  orders: [],
  knownPending: new Set(),
  knownReady: new Set(),
  firstLoad: true,
  showItems: true,
  soundEnabled: true,
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
    timeRow.appendChild(node("span", "", placed ? `Placed ${placed}` : ""));
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
}

bindControls();
updateClock();
setInterval(updateClock, 1000);
setInterval(() => { if (!state.firstLoad) renderBoard(); }, 1000);
fetchBoard();
setInterval(fetchBoard, POLL_MS);
