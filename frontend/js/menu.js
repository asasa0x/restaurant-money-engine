/**
 * Restaurant Money Engine - Menu Management & Recipe Costing
 */

import { api, DEMO_STORE, showToast, formatCurrency } from "./api.js";

export const menu = {
  state: {
    items: [...DEMO_STORE.menu_items],
    selectedItem: null,
    recipeIngredients: []
  },

  async init() {
    this.bindEvents();
    await this.loadMenu();
  },

  bindEvents() {
    // Add Item Modal
    const addBtn = document.getElementById("btn-open-add-menu-modal");
    const addModal = document.getElementById("add-menu-modal");
    const closeAddBtn = document.getElementById("btn-close-add-modal");
    const addForm = document.getElementById("add-menu-form");

    if (addBtn && addModal) addBtn.addEventListener("click", () => addModal.showModal());
    if (closeAddBtn && addModal) closeAddBtn.addEventListener("click", () => addModal.close());
    if (addForm) addForm.addEventListener("submit", (e) => this.handleCreateItem(e));

    // Recipe Drawer / Modal
    const recipeModal = document.getElementById("recipe-modal");
    const closeRecipeBtn = document.getElementById("btn-close-recipe-modal");
    const addIngBtn = document.getElementById("btn-add-ingredient-row");
    const saveRecipeBtn = document.getElementById("btn-save-recipe");

    if (closeRecipeBtn && recipeModal) closeRecipeBtn.addEventListener("click", () => recipeModal.close());
    if (addIngBtn) addIngBtn.addEventListener("click", () => this.addIngredientRow());
    if (saveRecipeBtn) saveRecipeBtn.addEventListener("click", () => this.saveRecipe());

    // Search filter
    const searchInput = document.getElementById("menu-search-input");
    if (searchInput) {
      searchInput.addEventListener("input", (e) => this.render(e.target.value));
    }
  },

  async loadMenu() {
    const res = await api.get("/api/v1/menu/");
    if (res && !res.__isFallback && res.data) {
      this.state.items = res.data;
    } else {
      this.state.items = [...DEMO_STORE.menu_items];
    }
    this.render();
  },

  render(filterText = "") {
    const tbody = document.getElementById("menu-table-body");
    const countEl = document.getElementById("menu-total-count");
    if (!tbody) return;

    tbody.innerHTML = "";

    const query = filterText.toLowerCase().trim();
    const filtered = this.state.items.filter(item => 
      !query || 
      item.name.toLowerCase().includes(query) || 
      (item.category || "").toLowerCase().includes(query)
    );

    if (countEl) countEl.textContent = `${filtered.length} Items`;

    if (filtered.length === 0) {
      tbody.innerHTML = `<tr><td colspan="7" class="text-center py-4">No menu items found.</td></tr>`;
      return;
    }

    filtered.forEach(item => {
      const price = parseFloat(item.selling_price || item.price || 0);
      const cost = parseFloat(item.cost_price || item.cost || 0);
      const margin = price - cost;
      const foodCostPct = price > 0 ? (cost / price * 100).toFixed(1) : 0;
      const isActive = item.is_active !== false;

      const tr = document.createElement("tr");
      tr.className = isActive ? "" : "item-archived";
      tr.innerHTML = `
        <td>
          <div class="menu-item-info">
            <span class="font-bold">${escapeHtml(item.name)}</span>
            ${!isActive ? '<span class="badge badge-archived">Archived</span>' : ''}
          </div>
        </td>
        <td><span class="category-tag">${escapeHtml(item.category || "General")}</span></td>
        <td><strong>${formatCurrency(price)}</strong></td>
        <td><span class="cost-tag">${formatCurrency(cost)}</span></td>
        <td>
          <span class="pct-pill ${foodCostPct > 35 ? 'pct-high' : foodCostPct > 28 ? 'pct-medium' : 'pct-low'}">
            ${foodCostPct}%
          </span>
        </td>
        <td><strong class="text-emerald">+${formatCurrency(margin)}</strong></td>
        <td>
          <div class="table-actions">
            <button class="btn btn-secondary btn-xs btn-open-recipe" data-id="${item.id}">
              🥣 Recipe
            </button>
            <button class="btn btn-secondary btn-xs btn-edit-price" data-id="${item.id}" data-price="${price}">
              ✏️ Price
            </button>
            ${isActive ? `
              <button class="btn btn-danger btn-xs btn-archive-item" data-id="${item.id}">
                Archive
              </button>
            ` : ''}
          </div>
        </td>
      `;

      // Event listeners for row buttons
      tr.querySelector(".btn-open-recipe")?.addEventListener("click", () => this.openRecipeModal(item));
      tr.querySelector(".btn-edit-price")?.addEventListener("click", () => this.editItemPrice(item));
      tr.querySelector(".btn-archive-item")?.addEventListener("click", () => this.archiveItem(item.id));

      tbody.appendChild(tr);
    });
  },

  async handleCreateItem(e) {
    e.preventDefault();
    const name = document.getElementById("new-item-name")?.value;
    const category = document.getElementById("new-item-category")?.value;
    const price = parseFloat(document.getElementById("new-item-price")?.value || 0);
    const cost = parseFloat(document.getElementById("new-item-cost")?.value || 0);

    const payload = {
      name,
      category,
      selling_price: price,
      cost_price: cost,
      is_active: true
    };

    const res = await api.post("/api/v1/menu/", payload);
    const modal = document.getElementById("add-menu-modal");
    if (modal) modal.close();
    e.target.reset();

    if (res && !res.__isFallback && res.data) {
      this.state.items.unshift(res.data);
      showToast(`Menu item '${name}' created successfully!`, "success");
    } else {
      // Local fallback creation
      const fakeItem = { id: `local_${Date.now()}`, ...payload, unit_margin: price - cost };
      this.state.items.unshift(fakeItem);
      showToast(`Menu item '${name}' added (Local Session)`, "info");
    }

    this.render();
  },

  async editItemPrice(item) {
    const currentPrice = item.selling_price || item.price || 0;
    const newPriceStr = prompt(`Update selling price for "${item.name}":`, currentPrice.toFixed(2));
    if (!newPriceStr) return;

    const newPrice = parseFloat(newPriceStr);
    if (isNaN(newPrice) || newPrice < 0) {
      showToast("Invalid selling price entered", "error");
      return;
    }

    const res = await api.put(`/api/v1/menu/${item.id}`, { selling_price: newPrice });
    item.selling_price = newPrice;
    item.price = newPrice;
    showToast(`Price for '${item.name}' updated to ${formatCurrency(newPrice)}`, "success");
    this.render();
  },

  async archiveItem(itemId) {
    if (!confirm("Are you sure you want to archive this menu item?")) return;
    await api.delete(`/api/v1/menu/${itemId}`);
    const found = this.state.items.find(i => i.id == itemId);
    if (found) found.is_active = false;
    showToast("Menu item archived", "info");
    this.render();
  },

  async openRecipeModal(item) {
    this.state.selectedItem = item;
    const modal = document.getElementById("recipe-modal");
    const title = document.getElementById("recipe-modal-title");
    const sub = document.getElementById("recipe-modal-sub");

    if (title) title.textContent = `Recipe: ${item.name}`;
    if (sub) sub.textContent = `Selling Price: ${formatCurrency(item.selling_price || item.price)} | Plate Target < 30%`;

    // Fetch existing recipe ingredients from API or fallback store
    const res = await api.get(`/api/v1/menu/${item.id}/recipe`);
    if (res && !res.__isFallback && res.ingredients) {
      this.state.recipeIngredients = res.ingredients;
    } else {
      this.state.recipeIngredients = DEMO_STORE.recipes[String(item.id)] ? [...DEMO_STORE.recipes[String(item.id)]] : [];
    }

    this.renderRecipeRows();
    if (modal) modal.showModal();
  },

  renderRecipeRows() {
    const container = document.getElementById("recipe-ingredients-rows");
    if (!container) return;
    container.innerHTML = "";

    this.state.recipeIngredients.forEach((ing, index) => {
      const row = document.createElement("div");
      row.className = "recipe-ing-row";
      row.innerHTML = `
        <input type="text" class="form-input ing-name" placeholder="Ingredient name" value="${escapeHtml(ing.ingredient_name || '')}">
        <input type="number" step="0.001" min="0" class="form-input ing-qty" placeholder="Qty" value="${ing.quantity || ''}">
        <input type="text" class="form-input ing-unit" placeholder="Unit (kg, g, l)" value="${escapeHtml(ing.unit || 'portion')}">
        <input type="number" step="0.01" min="0" class="form-input ing-cost" placeholder="Unit Cost ($)" value="${ing.unit_cost || ''}">
        <span class="ing-subtotal font-bold">${formatCurrency((ing.quantity || 0) * (ing.unit_cost || 0))}</span>
        <button type="button" class="btn btn-danger btn-xs btn-remove-ing">✕</button>
      `;

      // Live subtotal recalculation on input
      const updateSub = () => {
        const q = parseFloat(row.querySelector(".ing-qty").value || 0);
        const c = parseFloat(row.querySelector(".ing-cost").value || 0);
        row.querySelector(".ing-subtotal").textContent = formatCurrency(q * c);
        this.updateTotalRecipePreview();
      };

      row.querySelector(".ing-qty").addEventListener("input", updateSub);
      row.querySelector(".ing-cost").addEventListener("input", updateSub);
      row.querySelector(".btn-remove-ing").addEventListener("click", () => {
        this.state.recipeIngredients.splice(index, 1);
        this.renderRecipeRows();
      });

      container.appendChild(row);
    });

    this.updateTotalRecipePreview();
  },

  addIngredientRow() {
    this.state.recipeIngredients.push({
      ingredient_name: "",
      quantity: 0.1,
      unit: "kg",
      unit_cost: 5.0
    });
    this.renderRecipeRows();
  },

  updateTotalRecipePreview() {
    const container = document.getElementById("recipe-ingredients-rows");
    if (!container) return;

    let total = 0;
    container.querySelectorAll(".recipe-ing-row").forEach(row => {
      const q = parseFloat(row.querySelector(".ing-qty")?.value || 0);
      const c = parseFloat(row.querySelector(".ing-cost")?.value || 0);
      total += q * c;
    });

    const totalEl = document.getElementById("recipe-total-calculated");
    const marginEl = document.getElementById("recipe-margin-preview");
    const price = this.state.selectedItem ? (this.state.selectedItem.selling_price || this.state.selectedItem.price || 0) : 0;

    if (totalEl) totalEl.textContent = formatCurrency(total);
    if (marginEl) {
      const margin = price - total;
      const pct = price > 0 ? (total / price * 100).toFixed(1) : 0;
      marginEl.textContent = `Portion Margin: +${formatCurrency(margin)} (${pct}% food cost)`;
    }
  },

  async saveRecipe() {
    if (!this.state.selectedItem) return;
    const container = document.getElementById("recipe-ingredients-rows");
    const ingredients = [];

    container.querySelectorAll(".recipe-ing-row").forEach(row => {
      const name = row.querySelector(".ing-name")?.value.trim();
      const qty = parseFloat(row.querySelector(".ing-qty")?.value || 0);
      const unit = row.querySelector(".ing-unit")?.value.trim() || "portion";
      const unitCost = parseFloat(row.querySelector(".ing-cost")?.value || 0);

      if (name && qty > 0) {
        ingredients.push({
          ingredient_name: name,
          quantity: qty,
          unit: unit,
          unit_cost: unitCost
        });
      }
    });

    const res = await api.post(`/api/v1/menu/${this.state.selectedItem.id}/recipe`, { ingredients });
    const modal = document.getElementById("recipe-modal");
    if (modal) modal.close();

    const newCost = res && res.calculated_cost_price !== undefined
      ? res.calculated_cost_price
      : ingredients.reduce((sum, i) => sum + (i.quantity * i.unit_cost), 0);

    // Update state item cost
    this.state.selectedItem.cost_price = newCost;
    this.state.selectedItem.cost = newCost;
    DEMO_STORE.recipes[String(this.state.selectedItem.id)] = ingredients;

    showToast(`Recipe saved! Plate cost updated to ${formatCurrency(newCost)}.`, "success");
    this.render();
  }
};

function escapeHtml(str) {
  return String(str || "").replace(/[&<>'"]/g, 
    tag => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[tag] || tag)
  );
}

