/**
 * Restaurant Money Engine - Orders & QR Menu (owner / staff side)
 * Generates table QR codes for the customer ordering page and manages incoming orders.
 */

import { api, showToast, formatCurrency } from "./api.js";

const QR_LIB_URL = "js/vendor/qrcode.min.js";
const POLL_MS = 5000;

const NEXT_STEP = {
  pending: { status: "accepted", label: "Accept" },
  accepted: { status: "preparing", label: "Start Preparing" },
  preparing: { status: "ready", label: "Mark Ready" },
  ready: { status: "completed", label: "Complete" },
};

export const orders = {
  state: {
    items: [],
    knownIds: new Set(),
    firstLoadDone: false,
    filter: "ALL",
    timer: null,
    qrUrl: "",
  },

  reset() {
    clearInterval(this.state.timer);
    this.state.timer = null;
    this.state.items = [];
    this.state.knownIds = new Set();
    this.state.firstLoadDone = false;
    this.state.qrUrl = "";
    this.render();
    const qrBox = document.getElementById("qr-result");
    if (qrBox) qrBox.hidden = true;
  },

  bindEvents() {
    document.getElementById("btn-generate-qr")?.addEventListener("click", () => this.generateQr());
    document.getElementById("btn-copy-qr-link")?.addEventListener("click", () => this.copyLink());
    document.getElementById("btn-download-qr")?.addEventListener("click", () => this.downloadQr());
    document.getElementById("btn-print-qr")?.addEventListener("click", () => this.printQr());
    document.getElementById("btn-print-bulk-qr")?.addEventListener("click", () => this.printBulkQr());
    document.getElementById("btn-open-led-board")?.addEventListener("click", () => this.openLedBoard());
    document.getElementById("btn-refresh-orders")?.addEventListener("click", () => this.loadOrders(true));
    document.getElementById("orders-status-filter")?.addEventListener("change", (e) => {
      this.state.filter = e.target.value || "ALL";
      this.render();
    });
  },

  startPolling() {
    clearInterval(this.state.timer);
    this.state.timer = setInterval(() => {
      if (api.isAuthenticated() && !document.hidden) this.loadOrders(false);
    }, POLL_MS);
  },

  // ----------------------------------------------------------------- orders
  async loadOrders(manual = false) {
    if (!api.isAuthenticated()) {
      this.reset();
      return;
    }
    const list = document.getElementById("orders-list");
    try {
      const res = await api.get("/api/v1/orders?limit=100");
      const incoming = Array.isArray(res?.data) ? res.data : [];

      if (this.state.firstLoadDone) {
        const fresh = incoming.filter((o) => !this.state.knownIds.has(o.id) && o.status === "pending");
        if (fresh.length) {
          showToast(`🔔 ${fresh.length} new order${fresh.length > 1 ? "s" : ""} received!`, "success");
          this.beep();
        }
      }
      this.state.knownIds = new Set(incoming.map((o) => o.id));
      this.state.firstLoadDone = true;
      this.state.items = incoming;
      this.render();
      if (manual) showToast("Orders refreshed.", "info");
      this.startPolling();
    } catch (err) {
      this.state.items = [];
      if (list) {
        list.replaceChildren(
          this.node(
            "div",
            "orders-empty",
            err.status === 500 || err.status === 503
              ? "Orders are not available yet. Make sure database migration 004_customer_orders.sql has been run in Supabase."
              : `Could not load orders: ${err.message}`
          )
        );
      }
      if (err.status !== 401) showToast(`Failed to load orders: ${err.message}`, "error");
    }
  },

  node(tag, className, text) {
    const n = document.createElement(tag);
    if (className) n.className = className;
    if (text !== undefined) n.textContent = text;
    return n;
  },

  render() {
    const list = document.getElementById("orders-list");
    const countEl = document.getElementById("orders-pending-count");
    if (!list) return;

    const pending = this.state.items.filter((o) => o.status === "pending").length;
    if (countEl) countEl.textContent = `${pending} pending`;

    const visible = this.state.items.filter((o) => this.state.filter === "ALL" || o.status === this.state.filter);
    list.replaceChildren();

    if (visible.length === 0) {
      list.appendChild(this.node("div", "orders-empty", api.isAuthenticated()
        ? "No orders yet. Orders placed from your QR menu will appear here."
        : "Sign in to see orders."));
      return;
    }

    visible.forEach((order) => {
      const card = this.node("div", `order-card order-${order.status}`);

      const head = this.node("div", "order-card-head");
      const title = this.node("div", "order-title-group");
      const where = order.table_number ? `TABLE ${order.table_number}` : "TAKEAWAY";
      title.appendChild(this.node("span", "order-table-badge", where));
      title.appendChild(this.node("strong", "order-code", `#${order.code}`));
      title.appendChild(this.node("span", "order-meta", ` · ${order.customer_name || "Customer"}`));
      head.append(title, this.node("span", `order-status-pill ${order.status}`, order.status));
      card.appendChild(head);

      const time = order.created_at ? new Date(order.created_at) : null;
      const metaBits = [];
      if (time && !isNaN(time)) metaBits.push(time.toLocaleString());
      if (order.customer_phone) metaBits.push(`📞 ${order.customer_phone}`);
      if (metaBits.length) card.appendChild(this.node("div", "order-meta", metaBits.join("  ·  ")));

      const lines = this.node("div", "order-lines");
      (order.items || []).forEach((item) => {
        const row = this.node("div", "order-line");
        row.append(
          this.node("span", "", `${item.quantity} × ${item.item_name}`),
          this.node("span", "", formatCurrency(item.line_total))
        );
        lines.appendChild(row);
      });
      card.appendChild(lines);

      if (order.notes) card.appendChild(this.node("div", "order-notes", `📝 ${order.notes}`));

      const foot = this.node("div", "order-card-foot");
      foot.appendChild(this.node("strong", "", `Total ${formatCurrency(order.total)}`));
      const actions = this.node("div", "order-actions");
      const next = NEXT_STEP[order.status];
      if (next) {
        const btn = this.node("button", "btn btn-primary btn-xs", next.label);
        btn.type = "button";
        btn.addEventListener("click", () => this.setStatus(order, next.status));
        actions.appendChild(btn);
      }
      if (order.status !== "completed" && order.status !== "cancelled") {
        const cancel = this.node("button", "btn btn-danger btn-xs", "Cancel");
        cancel.type = "button";
        cancel.addEventListener("click", () => {
          if (confirm(`Cancel order #${order.code}?`)) this.setStatus(order, "cancelled");
        });
        actions.appendChild(cancel);
      }
      foot.appendChild(actions);
      card.appendChild(foot);
      list.appendChild(card);
    });
  },

  async setStatus(order, status) {
    try {
      await api.put(`/api/v1/orders/${order.id}/status`, { status });
      order.status = status;
      this.render();
      showToast(`Order #${order.code} → ${status}`, "success");
    } catch (err) {
      showToast(`Could not update order: ${err.message}`, "error");
    }
  },

  beep() {
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      const osc = ctx.createOscillator();
      osc.frequency.value = 880;
      osc.connect(ctx.destination);
      osc.start();
      setTimeout(() => { osc.stop(); ctx.close(); }, 250);
    } catch {
      /* audio not available */
    }
  },

  // --------------------------------------------------------------------- QR
  menuLink() {
    const restaurant = api.getRestaurant();
    if (!restaurant?.id) return "";
    const table = (document.getElementById("qr-table-number")?.value || "").trim();
    let url = `${window.location.origin}/order.html?r=${encodeURIComponent(restaurant.id)}`;
    if (table) url += `&t=${encodeURIComponent(table)}`;
    return url;
  },

  async _loadQrLib() {
    if (typeof window.qrcode === "function") return;
    await new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = QR_LIB_URL;
      script.onload = resolve;
      script.onerror = () => reject(new Error("Could not load local QR generator library."));
      document.head.appendChild(script);
    });
  },

  _drawQrToCanvas(canvas, text, size = 260, quietModules = 2) {
    const qr = window.qrcode(0, "M");
    qr.addData(text);
    qr.make();

    const count = qr.getModuleCount();
    const totalModules = count + quietModules * 2;
    const cellSize = Math.floor(size / totalModules) || 4;
    const actualSize = totalModules * cellSize;

    canvas.width = actualSize;
    canvas.height = actualSize;
    const ctx = canvas.getContext("2d");
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, actualSize, actualSize);

    ctx.fillStyle = "#0b0f19";
    for (let r = 0; r < count; r += 1) {
      for (let c = 0; c < count; c += 1) {
        if (qr.isDark(r, c)) {
          ctx.fillRect((c + quietModules) * cellSize, (r + quietModules) * cellSize, cellSize, cellSize);
        }
      }
    }
  },

  async generateQr() {
    if (!api.isAuthenticated()) {
      showToast("Please sign in first.", "error");
      return;
    }
    const url = this.menuLink();
    if (!url) return;
    try {
      await this._loadQrLib();
      const canvas = document.getElementById("qr-canvas");
      this._drawQrToCanvas(canvas, url, 260, 2);
      this.state.qrUrl = url;
      const table = (document.getElementById("qr-table-number")?.value || "").trim();
      document.getElementById("qr-link-input").value = url;
      document.getElementById("qr-caption").textContent = table ? `Table ${table}` : "All tables (no table number)";
      document.getElementById("qr-result").hidden = false;
    } catch (err) {
      showToast(err.message || "Could not generate QR code", "error");
    }
  },

  async copyLink() {
    const input = document.getElementById("qr-link-input");
    if (!input?.value) return;
    try {
      await navigator.clipboard.writeText(input.value);
      showToast("Menu link copied!", "success");
    } catch {
      input.select();
      showToast("Press Ctrl+C to copy the selected link.", "info");
    }
  },

  downloadQr() {
    const canvas = document.getElementById("qr-canvas");
    if (!canvas || !this.state.qrUrl) return;
    const table = (document.getElementById("qr-table-number")?.value || "").trim();
    const link = document.createElement("a");
    link.download = `menu-qr${table ? `-table-${table}` : ""}.png`;
    link.href = canvas.toDataURL("image/png");
    link.click();
  },

  printQr() {
    const canvas = document.getElementById("qr-canvas");
    if (!canvas || !this.state.qrUrl) return;
    const win = window.open("", "_blank", "width=480,height=640");
    if (!win) {
      showToast("Allow pop-ups to print the QR code.", "error");
      return;
    }
    const doc = win.document;
    doc.title = "Menu QR";
    doc.body.style.cssText = "font-family:sans-serif;text-align:center;padding:24px";
    const name = doc.createElement("h1");
    name.textContent = api.getRestaurant()?.name || "Our Menu";
    const sub = doc.createElement("p");
    sub.textContent = "Scan to view the menu & order";
    sub.style.fontSize = "18px";
    const img = doc.createElement("img");
    img.src = canvas.toDataURL("image/png");
    img.style.width = "320px";
    const table = doc.createElement("h2");
    table.textContent = document.getElementById("qr-caption")?.textContent || "";
    doc.body.append(name, sub, img, table);
    win.focus();
    img.onload = () => win.print();
  },

  openLedBoard() {
    const restaurant = api.getRestaurant();
    if (!restaurant?.id) {
      showToast("Please sign in first.", "error");
      return;
    }
    const url = `${window.location.origin}/led.html?r=${encodeURIComponent(restaurant.id)}`;
    window.open(url, "_blank", "noopener");
  },

  async printBulkQr() {
    if (!api.isAuthenticated()) {
      showToast("Please sign in first.", "error");
      return;
    }
    const restaurant = api.getRestaurant();
    if (!restaurant?.id) return;

    const fromVal = parseInt(document.getElementById("qr-bulk-from")?.value || "1", 10);
    const toVal = parseInt(document.getElementById("qr-bulk-to")?.value || "50", 10);
    if (isNaN(fromVal) || isNaN(toVal) || fromVal < 1 || toVal < fromVal || toVal - fromVal >= 200) {
      showToast("Enter a valid table range (max 200 tables at once, e.g. 1 to 50).", "error");
      return;
    }

    try {
      await this._loadQrLib();
      const win = window.open("", "_blank", "width=960,height=720");
      if (!win) {
        showToast("Allow pop-ups to generate the printable bulk QR sheet.", "error");
        return;
      }

      const doc = win.document;
      doc.title = `${restaurant.name} — Table QRs (${fromVal} to ${toVal})`;
      const style = doc.createElement("style");
      style.textContent = `
        body { font-family: sans-serif; margin: 16px; color: #111827; }
        .bar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
        .grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; }
        .card { border: 1.5px solid #cbd5e1; border-radius: 10px; padding: 12px 8px; text-align: center; page-break-inside: avoid; }
        .card h3 { margin: 0 0 4px; font-size: 13px; color: #475569; }
        .card h2 { margin: 6px 0 2px; font-size: 18px; }
        .card p { margin: 0; font-size: 11px; color: #64748b; }
        @media print { .bar { display: none; } body { margin: 8px; } }
      `;
      doc.head.appendChild(style);

      const bar = doc.createElement("div");
      bar.className = "bar";
      const heading = doc.createElement("strong");
      heading.textContent = `${restaurant.name} — Tables ${fromVal} to ${toVal}`;
      const printBtn = doc.createElement("button");
      printBtn.textContent = "Print / Save as PDF";
      printBtn.style.cssText = "padding:8px 14px;font-weight:bold;cursor:pointer;";
      printBtn.onclick = () => win.print();
      bar.append(heading, printBtn);
      doc.body.appendChild(bar);

      const grid = doc.createElement("div");
      grid.className = "grid";
      const tempCanvas = doc.createElement("canvas");

      for (let t = fromVal; t <= toVal; t += 1) {
        const url = `${window.location.origin}/order.html?r=${encodeURIComponent(restaurant.id)}&t=${t}`;
        this._drawQrToCanvas(tempCanvas, url, 170, 2);

        const card = doc.createElement("div");
        card.className = "card";
        const rName = doc.createElement("h3");
        rName.textContent = restaurant.name || "Menu";
        const img = doc.createElement("img");
        img.src = tempCanvas.toDataURL("image/png");
        img.style.width = "145px";
        const tTitle = doc.createElement("h2");
        tTitle.textContent = `TABLE ${t}`;
        const hint = doc.createElement("p");
        hint.textContent = "Scan to Order";
        card.append(rName, img, tTitle, hint);
        grid.appendChild(card);
      }

      doc.body.appendChild(grid);
      win.focus();
      showToast(`Generated ${toVal - fromVal + 1} Table QRs (${fromVal}–${toVal})!`, "success");
    } catch (err) {
      showToast(err.message || "Could not generate bulk QR sheet", "error");
    }
  },
};

