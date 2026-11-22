/**
 * Restaurant Money Engine - Kasavana-Smith 2x2 Matrix
 */

import { api, EMPTY_STATE, showToast, formatCurrency } from "./api.js";

export const matrix = {
  state: {
    data: structuredClone(EMPTY_STATE.menu_matrix),
    activeCategory: "ALL",
    activeQuadrant: "ALL"
  },

  async init() {
    this.bindEvents();
    await this.loadMatrix();
  },

  reset() {
    this.state.data = structuredClone(EMPTY_STATE.menu_matrix);
    this.state.activeQuadrant = "ALL";
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
      refreshBtn.addEventListener("click", async () => {
        await this.loadMatrix();
        showToast("Kasavana-Smith Menu Matrix refreshed!", "info");
      });
    }

    // Quadrant switcher tabs (All, Stars, Plowhorses, Puzzles, Dogs)
    document.querySelectorAll(".matrix-qtab").forEach((tab) => {
      tab.addEventListener("click", (e) => {
        const q = e.currentTarget.getAttribute("data-quadrant") || "ALL";
        this.state.activeQuadrant = q;
        document.querySelectorAll(".matrix-qtab").forEach((t) => {
          t.classList.toggle("active", (t.getAttribute("data-quadrant") || "ALL") === q);
        });
        this.filterQuadrantBoxes();
      });
    });
  },

  filterQuadrantBoxes() {
    const q = this.state.activeQuadrant || "ALL";
    document.querySelectorAll("[data-quadrant-box]").forEach((box) => {
      const boxKey = box.getAttribute("data-quadrant-box");
      if (q === "ALL" || q === boxKey) {
        box.style.display = "";
      } else {
        box.style.display = "none";
      }
    });
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

    // Update tab counts
    const qAll = document.getElementById("qtab-count-all");
    const qStars = document.getElementById("qtab-count-stars");
    const qPlow = document.getElementById("qtab-count-plowhorses");
    const qPuzzles = document.getElementById("qtab-count-puzzles");
    const qDogs = document.getElementById("qtab-count-dogs");

    if (qAll) qAll.textContent = String(allItemsCount);
    if (qStars) qStars.textContent = String(quadrants.stars?.length || 0);
    if (qPlow) qPlow.textContent = String(quadrants.plowhorses?.length || 0);
    if (qPuzzles) qPuzzles.textContent = String(quadrants.puzzles?.length || 0);
    if (qDogs) qDogs.textContent = String(quadrants.dogs?.length || 0);

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
    if (document.getElementById("quadrant-puzzles-list")) {
      this.renderQuadrant("puzzles", quadrants.puzzles || []);
    }
    this.renderQuadrant("dogs", quadrants.dogs || []);

    // 3. Apply active quadrant visibility filter
    this.filterQuadrantBoxes();
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
      listEl.innerHTML = `<div class="empty-quadrant-placeholder" style="grid-column: 1 / -1;">No items in this quadrant for selected category.</div>`;
      return;
    }

    // Tarteeb (Natural Sequential Sorting: Deal-1, Deal-2, Deal-3 ... Deal-10, Deal-11, Deal-12):
    const sorted = [...filtered].sort((a, b) => {
      const nameA = String(a.name || "").trim();
      const nameB = String(b.name || "").trim();
      return nameA.localeCompare(nameB, undefined, { numeric: true, sensitivity: "base" });
    });

    sorted.forEach((item, idx) => {
      const card = document.createElement("div");
      card.className = "dish-matrix-card";

      const margin = item.contribution_margin ?? ((Number(item.price) || 0) - (Number(item.cost) || 0));
      const foodCostPct = item.food_cost_pct ?? (Number(item.price) > 0 ? ((Number(item.cost) / Number(item.price)) * 100).toFixed(1) : 0);
      const totalProfit = item.total_profit ?? (margin * (Number(item.volume) || 0));

      card.innerHTML = `
        <div class="dish-card-header">
          <div>
            <h4 class="dish-name">
              <span class="dish-rank-tag">#${idx + 1}</span>
              ${escapeHtml(item.name)}
            </h4>
            <span class="dish-category">${escapeHtml(item.category || "General")}</span>
          </div>
          <div class="dish-pricing">
            <span class="dish-price">${formatCurrency(item.price)}</span>
            <span class="dish-margin">+${formatCurrency(margin)} margin</span>
          </div>
        </div>

        <div class="dish-metrics-row">
          <div class="metric-chip">
            <span class="chip-label">📦 Volume:</span>
            <span class="chip-val">${item.volume || 0} sold</span>
          </div>
          <div class="metric-chip">
            <span class="chip-label">🥩 Plate Cost:</span>
            <span class="chip-val">${formatCurrency(item.cost)}</span>
          </div>
          <div class="metric-chip">
            <span class="chip-label">📊 Food Cost:</span>
            <span class="chip-val ${Number(foodCostPct) > 35 ? "text-alert" : "text-healthy"}">${foodCostPct}%</span>
          </div>
          ${Number(totalProfit) > 0 ? `
          <div class="metric-chip" title="Total gross profit generated">
            <span class="chip-label">💰 Profit:</span>
            <span class="chip-val text-emerald">${formatCurrency(totalProfit)}</span>
          </div>` : ""}
        </div>

        <div class="dish-strategy-badge">
          <span class="strategy-icon">💡</span>
          <span class="strategy-text">${escapeHtml(item.action_recommendation || "Maintain quality and monitor")}</span>
        </div>

        <div class="dish-card-actions">
          <button type="button" class="btn btn-matrix-edit" title="Edit Selling Price, Plate Cost, or Details">
            ✏️ Edit Price &amp; Cost
          </button>
          <button type="button" class="btn btn-matrix-sim" title="Simulate price &amp; margin optimizations">
            📈 Simulator
          </button>
        </div>
      `;

      card.querySelector(".btn-matrix-edit")?.addEventListener("click", () => {
        openEditDishModal(item);
      });

      card.querySelector(".btn-matrix-sim")?.addEventListener("click", () => {
        const simTab = document.querySelector('[data-tab="tab-simulation"]');
        if (simTab) simTab.click();
      });

      listEl.appendChild(card);
    });
  }
};

function openEditDishModal(item) {
  const modal = document.getElementById("edit-menu-modal");
  if (!modal) return;
  const setVal = (id, val) => {
    const el = document.getElementById(id);
    if (el) el.value = val;
  };
  setVal("edit-item-id", item.id || "");
  setVal("edit-item-name", item.name || "");
  setVal("edit-item-category", item.category || "General");
  setVal("edit-item-price", parseFloat(item.selling_price ?? item.price ?? 0));
  setVal("edit-item-cost", parseFloat(item.cost_price ?? item.cost ?? 0));
  setVal("edit-item-description", item.description || "");
  modal.showModal();
}

function escapeHtml(str) {
  return String(str || "").replace(/[&<>'"]/g,
    tag => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[tag] || tag)
  );
}
