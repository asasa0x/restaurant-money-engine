/**
 * Customer QR ordering page: scan QR -> menu -> add to cart -> place order -> live status.
 * Prices shown here are for display only; the server re-prices every order from the database.
 */

const params = new URLSearchParams(window.location.search);
const restaurantId = (params.get("r") || "").trim();
const tableFromQr = (params.get("t") || "").trim().slice(0, 30);

const isLocalDev =
  (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1") &&
  window.location.port !== "5000";
const API_BASE = isLocalDev ? "http://127.0.0.1:5000" : "";

const CART_KEY = `rme_cart_${restaurantId}`;
const LAST_ORDER_KEY = `rme_last_order_${restaurantId}`;
const NAME_KEY = "rme_customer_name";
const FINAL_STATUSES = ["completed", "cancelled"];

const state = {
  restaurant: null,
  items: [],
  cart: {},
  category: "ALL",
  search: "",
  trackTimer: null,
};

const $ = (id) => document.getElementById(id);

async function call(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", Accept: "application/json" },
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const err = new Error(data.error || `Request failed (${response.status})`);
    err.status = response.status;
    err.code = data.code;
    throw err;
  }
  return data;
}

function money(value) {
  const amount = Number(value || 0);
  const currency = (state.restaurant?.currency || "USD").toUpperCase();
  if (currency === "PKR" || currency === "RS") {
    return `Rs. ${amount.toLocaleString("en-PK", { maximumFractionDigits: 2 })}`;
  }
  try {
    return new Intl.NumberFormat("en-US", { style: "currency", currency }).format(amount);
  } catch {
    return `${currency} ${amount.toFixed(2)}`;
  }
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

// ---------------------------------------------------------------- cart state
function loadCart() {
  try {
    const saved = JSON.parse(localStorage.getItem(CART_KEY) || "{}");
    const valid = new Set(state.items.map((i) => i.id));
    state.cart = {};
    Object.entries(saved).forEach(([id, qty]) => {
      if (valid.has(id) && Number.isInteger(qty) && qty > 0) state.cart[id] = Math.min(qty, 50);
    });
  } catch {
    state.cart = {};
  }
}

function saveCart() {
  localStorage.setItem(CART_KEY, JSON.stringify(state.cart));
}

function cartTotals() {
  let count = 0;
  let total = 0;
  state.items.forEach((item) => {
    const qty = state.cart[item.id] || 0;
    count += qty;
    total += qty * item.price;
  });
  return { count, total };
}

function setQty(itemId, qty) {
  const next = Math.max(0, Math.min(50, qty));
  if (next === 0) delete state.cart[itemId];
  else state.cart[itemId] = next;
  saveCart();
  renderMenu();
  renderCartBar();
  if ($("co-cart-modal").open) renderCartModal();
}

// ------------------------------------------------------------------ menu UI
function renderCategories() {
  const nav = $("co-categories");
  nav.replaceChildren();
  const categories = ["ALL", ...Array.from(new Set(state.items.map((i) => i.category)))];
  categories.forEach((cat) => {
    const chip = el("button", `co-chip${state.category === cat ? " active" : ""}`, cat === "ALL" ? "All" : cat);
    chip.type = "button";
    chip.addEventListener("click", () => {
      state.category = cat;
      renderCategories();
      renderMenu();
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
    nav.appendChild(chip);
  });
}

function stepper(item) {
  const qty = state.cart[item.id] || 0;
  const wrap = el("div", "co-stepper");
  if (qty === 0) {
    const add = el("button", "btn btn-primary btn-xs co-add-btn", "+ Add");
    add.type = "button";
    add.addEventListener("click", () => setQty(item.id, 1));
    wrap.appendChild(add);
    return wrap;
  }
  const minus = el("button", "", "−");
  minus.type = "button";
  minus.setAttribute("aria-label", `Remove one ${item.name}`);
  minus.addEventListener("click", () => setQty(item.id, qty - 1));
  const plus = el("button", "add", "+");
  plus.type = "button";
  plus.setAttribute("aria-label", `Add one ${item.name}`);
  plus.addEventListener("click", () => setQty(item.id, qty + 1));
  wrap.append(minus, el("span", "qty", String(qty)), plus);
  return wrap;
}

function renderMenu() {
  const container = $("co-menu");
  container.replaceChildren();
  const query = state.search.toLowerCase().trim();
  const visible = state.items.filter((item) => {
    const catOk = state.category === "ALL" || item.category === state.category;
    const textOk = !query || item.name.toLowerCase().includes(query) || item.description.toLowerCase().includes(query);
    return catOk && textOk;
  });

  const status = $("co-status");
  if (visible.length === 0) {
    status.textContent = state.items.length ? "No dishes match your search." : "This menu is empty right now.";
    status.className = "co-status";
    status.hidden = false;
    return;
  }
  status.hidden = true;

  const grouped = new Map();
  visible.forEach((item) => {
    if (!grouped.has(item.category)) grouped.set(item.category, []);
    grouped.get(item.category).push(item);
  });

  grouped.forEach((items, category) => {
    const section = el("section", "co-section");
    section.appendChild(el("h2", "", category));
    items.forEach((item) => {
      const row = el("div", "co-item");
      const info = el("div", "co-item-info");
      info.appendChild(el("div", "co-item-name", item.name));
      if (item.description) info.appendChild(el("div", "co-item-desc", item.description));
      info.appendChild(el("div", "co-item-price", money(item.price)));
      row.append(info, stepper(item));
      section.appendChild(row);
    });
    container.appendChild(section);
  });
}

function renderCartBar() {
  const { count, total } = cartTotals();
  const bar = $("co-cart-bar");
  bar.hidden = count === 0;
  $("co-cart-count").textContent = String(count);
  $("co-cart-total").textContent = money(total);
}

// ------------------------------------------------------------------ checkout
function renderCartModal() {
  const lines = $("co-cart-lines");
  lines.replaceChildren();
  state.items.forEach((item) => {
    const qty = state.cart[item.id];
    if (!qty) return;
    const line = el("div", "co-cart-line");
    const info = el("div");
    info.appendChild(el("div", "name", item.name));
    info.appendChild(el("div", "sub", `${money(item.price)} × ${qty} = ${money(item.price * qty)}`));
    line.append(info, stepper(item));
    lines.appendChild(line);
  });
  $("co-cart-modal-total").textContent = money(cartTotals().total);
}

function showFormError(message) {
  const box = $("co-form-error");
  box.textContent = message || "";
  box.hidden = !message;
}

function openCart() {
  if (cartTotals().count === 0) return;
  showFormError("");
  $("co-table").value = $("co-table").value || tableFromQr;
  $("co-name").value = $("co-name").value || localStorage.getItem(NAME_KEY) || "";
  renderCartModal();
  $("co-cart-modal").showModal();
}

async function placeOrder(event) {
  event.preventDefault();
  showFormError("");

  const name = $("co-name").value.trim();
  const table = $("co-table").value.trim();
  const phone = $("co-phone").value.trim();
  const notes = $("co-notes").value.trim();
  const items = Object.entries(state.cart).map(([menu_item_id, quantity]) => ({ menu_item_id, quantity }));

  if (items.length === 0) return showFormError("Your cart is empty.");
  if (!name) return showFormError("Please enter your name.");
  if (!table && !phone) return showFormError("Enter your table number, or a phone number if you are not at a table.");

  const button = $("co-place-order");
  button.disabled = true;
  button.textContent = "Placing order…";
  try {
    const res = await call(`/api/v1/public/restaurants/${encodeURIComponent(restaurantId)}/orders`, {
      method: "POST",
      body: JSON.stringify({
        customer_name: name,
        table_number: table || null,
        customer_phone: phone || null,
        notes: notes || null,
        items,
      }),
    });
    localStorage.setItem(NAME_KEY, name);
    localStorage.setItem(LAST_ORDER_KEY, res.order.id);
    state.cart = {};
    saveCart();
    $("co-cart-modal").close();
    $("co-notes").value = "";
    renderMenu();
    renderCartBar();
    showSuccess(res.order);
  } catch (err) {
    if (err.code === "ITEMS_UNAVAILABLE") {
      showFormError(err.message);
      await loadMenu(false);
      renderCartModal();
    } else {
      showFormError(err.message || "Could not place your order. Please try again.");
    }
  } finally {
    button.disabled = false;
    button.textContent = "Place Order";
  }
}

// ------------------------------------------------------- confirmation/tracking
function showSuccess(order) {
  $("co-success-code").textContent = order.code;
  $("co-success-total").textContent = money(order.total);
  const lines = $("co-success-lines");
  lines.replaceChildren();
  (order.items || []).forEach((item) => {
    const row = el("div");
    row.append(el("span", "", `${item.quantity} × ${item.name}`), el("span", "", money(item.line_total)));
    lines.appendChild(row);
  });
  setStatus(order.status);
  const modal = $("co-success-modal");
  if (!modal.open) modal.showModal();
  startTracking(order.id);
}

function setStatus(status) {
  const pill = $("co-success-status");
  pill.textContent = status;
  pill.className = `co-status-pill ${status}`;
  const titles = {
    pending: "Order placed!",
    accepted: "Order accepted",
    preparing: "Being prepared",
    ready: "Your order is ready!",
    completed: "Order completed",
    cancelled: "Order cancelled",
  };
  $("co-success-title").textContent = titles[status] || "Order update";
}

function startTracking(orderId) {
  clearInterval(state.trackTimer);
  const poll = async () => {
    try {
      const res = await call(`/api/v1/public/orders/${encodeURIComponent(orderId)}`);
      setStatus(res.order.status);
      if (FINAL_STATUSES.includes(res.order.status)) {
        clearInterval(state.trackTimer);
        localStorage.removeItem(LAST_ORDER_KEY);
      }
    } catch {
      /* transient network error: keep polling */
    }
  };
  state.trackTimer = setInterval(poll, 10000);
}

async function resumeTrackedOrder() {
  const orderId = localStorage.getItem(LAST_ORDER_KEY);
  if (!orderId) return;
  try {
    const res = await call(`/api/v1/public/orders/${encodeURIComponent(orderId)}`);
    if (FINAL_STATUSES.includes(res.order.status)) {
      localStorage.removeItem(LAST_ORDER_KEY);
      return;
    }
    showSuccess(res.order);
  } catch {
    localStorage.removeItem(LAST_ORDER_KEY);
  }
}

// -------------------------------------------------------------------- startup
async function loadMenu(showLoading = true) {
  const status = $("co-status");
  if (showLoading) {
    status.textContent = "Loading menu…";
    status.className = "co-status";
    status.hidden = false;
  }
  const res = await call(`/api/v1/public/restaurants/${encodeURIComponent(restaurantId)}/menu`);
  state.restaurant = res.restaurant;
  state.items = res.items;
  document.title = `${res.restaurant.name} | Order Online`;
  $("co-restaurant-name").textContent = res.restaurant.name;
  $("co-search").hidden = false;
  loadCart();
  renderCategories();
  renderMenu();
  renderCartBar();
}

function bindEvents() {
  $("co-cart-bar").addEventListener("click", openCart);
  $("co-cart-close").addEventListener("click", () => $("co-cart-modal").close());
  $("co-checkout-form").addEventListener("submit", placeOrder);
  $("co-search").addEventListener("input", (e) => {
    state.search = e.target.value || "";
    renderMenu();
  });
  $("co-new-order").addEventListener("click", () => {
    clearInterval(state.trackTimer);
    localStorage.removeItem(LAST_ORDER_KEY);
    $("co-success-modal").close();
  });
  $("co-success-modal").addEventListener("close", () => {
    /* keep polling in background only while a modal is open */
    if (!$("co-success-modal").open) clearInterval(state.trackTimer);
  });
}

async function init() {
  bindEvents();
  if (tableFromQr) {
    const badge = $("co-table-badge");
    badge.textContent = `Table ${tableFromQr}`;
    badge.hidden = false;
    $("co-table").value = tableFromQr;
  }

  if (!/^[0-9a-f-]{36}$/i.test(restaurantId)) {
    const status = $("co-status");
    status.textContent = "This QR code is invalid. Please ask the staff for help.";
    status.className = "co-status error";
    $("co-restaurant-name").textContent = "Menu unavailable";
    return;
  }

  try {
    await loadMenu();
    await resumeTrackedOrder();
  } catch (err) {
    const status = $("co-status");
    status.textContent = err.status === 404
      ? "Restaurant not found. Please ask the staff for help."
      : "Could not load the menu. Check your connection and refresh.";
    status.className = "co-status error";
    $("co-restaurant-name").textContent = "Menu unavailable";
  }
}

init();
