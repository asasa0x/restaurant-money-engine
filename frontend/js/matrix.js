/**
 * Restaurant Money Engine - Kasavana-Smith 2x2 Matrix
 */

import { api, EMPTY_STATE, showToast, formatCurrency } from "./api.js";

export const matrix = {
  state: {
    data: structuredClone(EMPTY_STATE.menu_matrix),
    activeCategory: "ALL"
  },

  async init() {
    this.bindEvents();
    await this.loadMatrix();
  },

  reset() {
    this.state.data = structuredClone(EMPTY_STATE.menu_matrix);
    this.render();
  },

  bindEvents() {
    const filterSelect = document.getElementById("matrix-category-filter");
    if (filterSelect) {
      filterSelect.addEventListener("change", (e) => {
        this.state.activeCategory = e.target.value;
        this.render();
      });
    }

    const refreshBtn = document.getElementById("btn-refresh-matrix");
    if (refreshBtn) {
      refreshBtn.addEventListener("click", () => this.loadMatrix());
    }
  },

  async loadMatrix() {
    if (!api.isAuthenticated()) {
      this.reset();
      return;
    }

    try {
      const res = await api.get("/api/v1/menu-matrix");
      if (res && res.data && res.data.quadrants) {
        this.state.data = res.data;
      } else {
        this.state.data = structuredClone(EMPTY_STATE.menu_matrix);
      }
    } catch (err) {
      this.state.data = structuredClone(EMPTY_STATE.menu_matrix);
      if (err.status !== 401) {
        showToast(`Failed to load menu matrix: ${err.message}`, "error");
      }
    }
    this.render();
  },

  render() {
    const data = this.state.data;
    const benchmarks = data.benchmarks || {};
    const quadrants = data.quadrants || { stars: [], plowhorses: [], puzzles: [], dogs: [] };

    // 1. Render Benchmark Header Chips
    const acmEl = document.getElementById("matrix-acm-val");
    const volEl = document.getElementById("matrix-vol-val");
    const totalItemsEl = document.getElementById("matrix-total-items");

    if (acmEl) acmEl.textContent = formatCurrency(benchmarks.average_contribution_margin || 0);
    if (volEl) volEl.textContent = `${benchmarks.popularity_threshold || 0} units`;

    const allItemsCount = (quadrants.stars?.length || 0) +
                         (quadrants.plowhorses?.length || 0) +
                         (quadrants.puzzles?.length || 0) +
                         (quadrants.dogs?.length || 0);
    if (totalItemsEl) totalItemsEl.textContent = `${allItemsCount} Dishes`;

    // Dynamically populate category filter options
    const filterSelect = document.getElementById("matrix-category-filter");
    if (filterSelect) {
      const allItems = [
        ...(quadrants.stars || []),
        ...(quadrants.plowhorses || []),
        ...(quadrants.puzzles || []),
        ...(quadrants.dogs || [])
      ];
      const categories = Array.from(new Set(allItems.map(i => i.category || "General"))).sort();
      filterSelect.innerHTML = `<option value="ALL">All Categories</option>` +
        categories.map(c => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`).join("");
      if (this.state.activeCategory !== "ALL" && !categories.includes(this.state.activeCategory)) {
        this.state.activeCategory = "ALL";
      }
      filterSelect.value = this.state.activeCategory;
    }

    // 2. Render Each Quadrant
    this.renderQuadrant("stars", quadrants.stars || []);
    this.renderQuadrant("plowhorses", quadrants.plowhorses || []);
    this.renderQuadrant("puzzles", quadrants.puzzles || []);
    this.renderQuadrant("dogs", quadrants.dogs || []);
  },

  renderQuadrant(quadrantKey, items) {
    const listEl = document.getElementById(`quadrant-${quadrantKey}-list`);
    const countBadge = document.getElementById(`quadrant-${quadrantKey}-count`);

    if (!listEl) return;
    listEl.innerHTML = "";

    const filtered = this.state.activeCategory === "ALL"
      ? items
      : items.filter(i => (i.category || "General").toUpperCase() === this.state.activeCategory.toUpperCase());

    if (countBadge) {
      countBadge.textContent = `${filtered.length} Items`;
    }

    if (filtered.length === 0) {
      listEl.innerHTML = `<div class="empty-quadrant-placeholder">No items in this quadrant</div>`;
      return;
    }

    filtered.forEach(item => {
      const card = document.createElement("div");
      card.className = "dish-matrix-card";

      const margin = item.contribution_margin ?? (item.price - item.cost);
      const foodCostPct = item.food_cost_pct ?? (item.price > 0 ? (item.cost / item.price * 100).toFixed(1) : 0);

      card.innerHTML = `
        <div class="dish-card-header">
          <div>
            <h4 class="dish-name">${escapeHtml(item.name)}</h4>
            <span class="dish-category">${escapeHtml(item.category || "General")}</span>
          </div>
          <div class="dish-pricing">
            <span class="dish-price">${formatCurrency(item.price)}</span>
            <span class="dish-margin">+${formatCurrency(margin)} margin</span>
          </div>
        </div>

        <div class="dish-metrics-row">
          <div class="metric-chip">
            <span class="chip-label">Volume:</span>
            <span class="chip-val">${item.volume || 0} sold</span>
          </div>
          <div class="metric-chip">
            <span class="chip-label">Plate Cost:</span>
            <span class="chip-val">${formatCurrency(item.cost)}</span>
          </div>
          <div class="metric-chip">
            <span class="chip-label">Food Cost:</span>
            <span class="chip-val ${foodCostPct > 35 ? "text-alert" : "text-healthy"}">${foodCostPct}%</span>
          </div>
        </div>

        <div class="dish-strategy-badge">
          <span class="strategy-icon">💡</span>
          <span class="strategy-text">${escapeHtml(item.action_recommendation || "Maintain quality and monitor")}</span>
        </div>
      `;

      listEl.appendChild(card);
    });
  }
};

function escapeHtml(str) {
  return String(str || "").replace(/[&<>'"]/g,
    tag => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[tag] || tag)
  );
}
