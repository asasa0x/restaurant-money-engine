/**
 * Restaurant Money Engine - Menu Management, Screenshot Scan & Recipe Costing
 */

import { api, showToast, formatCurrency } from "./api.js";
import { matrix } from "./matrix.js";

export const menu = {
  state: {
    items: [],
    selectedItem: null,
    recipeIngredients: [],
    scannedItems: [],
    selectedScanImageBase64: null,
    selectedScanMimeType: "image/jpeg",
    activeCategoryFilter: "ALL",
    searchQuery: ""
  },

  async init() {
    this.bindEvents();
    await this.loadMenu();
  },

  reset() {
    this.state.items = [];
    this.state.selectedItem = null;
    this.state.recipeIngredients = [];
    this.state.scannedItems = [];
    this.render();
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

    // Edit Item Modal
    const editModal = document.getElementById("edit-menu-modal");
    const closeEditBtn = document.getElementById("btn-close-edit-modal");
    const editForm = document.getElementById("edit-menu-form");

    if (closeEditBtn && editModal) closeEditBtn.addEventListener("click", () => editModal.close());
    if (editForm) editForm.addEventListener("submit", (e) => this.handleUpdateItem(e));

    // Scan Menu Screenshot Modal
    const scanBtn = document.getElementById("btn-open-scan-menu-modal");
    const scanModal = document.getElementById("scan-menu-modal");
    const closeScanBtn = document.getElementById("btn-close-scan-modal");
    const fileInput = document.getElementById("scan-menu-file");
    const runScanBtn = document.getElementById("btn-run-menu-scan");
    const addScanRowBtn = document.getElementById("btn-add-scan-row");
    const saveScannedBtn = document.getElementById("btn-save-scanned-menu");

    if (scanBtn && scanModal) scanBtn.addEventListener("click", () => this.openScanModal());
    if (closeScanBtn && scanModal) closeScanBtn.addEventListener("click", () => scanModal.close());
    if (fileInput) fileInput.addEventListener("change", (e) => this.handleScanFileSelected(e));
    if (runScanBtn) runScanBtn.addEventListener("click", () => this.runMenuScan());
    if (addScanRowBtn) addScanRowBtn.addEventListener("click", () => this.addScanRow());
    if (saveScannedBtn) saveScannedBtn.addEventListener("click", () => this.saveScannedMenu());

    // Recipe Drawer / Modal
    const recipeModal = document.getElementById("recipe-modal");
    const closeRecipeBtn = document.getElementById("btn-close-recipe-modal");
    const addIngBtn = document.getElementById("btn-add-ingredient-row");
    const saveRecipeBtn = document.getElementById("btn-save-recipe");

    if (closeRecipeBtn && recipeModal) closeRecipeBtn.addEventListener("click", () => recipeModal.close());
    if (addIngBtn) addIngBtn.addEventListener("click", () => this.addIngredientRow());
    if (saveRecipeBtn) saveRecipeBtn.addEventListener("click", () => this.saveRecipe());

    // Search & Category filter
    const searchInput = document.getElementById("menu-search-input");
    if (searchInput) {
      searchInput.addEventListener("input", (e) => {
        this.state.searchQuery = e.target.value || "";
        this.render();
      });
    }

    const catSelect = document.getElementById("menu-category-filter");
    if (catSelect) {
      catSelect.addEventListener("change", (e) => {
        this.state.activeCategoryFilter = e.target.value || "ALL";
        this.render();
      });
    }
  },

  async loadMenu() {
    if (!api.isAuthenticated()) {
      this.reset();
      return;
    }

    try {
      const res = await api.get("/api/v1/menu/");
      this.state.items = Array.isArray(res?.data) ? res.data : [];
    } catch (err) {
      this.state.items = [];
      if (err.status !== 401) {
        showToast(`Failed to load menu items: ${err.message}`, "error");
      }
    }
    this.render();
  },

  render(filterOverride = null) {
    const tbody = document.getElementById("menu-table-body");
    const countEl = document.getElementById("menu-total-count");
    const catSelect = document.getElementById("menu-category-filter");
    if (!tbody) return;

    if (typeof filterOverride === "string") {
      this.state.searchQuery = filterOverride;
    }

    // Populate category filter dropdown from current items
    if (catSelect) {
      const categories = Array.from(new Set(this.state.items.map(i => i.category || "General"))).sort();
      catSelect.innerHTML = `<option value="ALL">All Categories</option>` +
        categories.map(c => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`).join("");
      if (this.state.activeCategoryFilter !== "ALL" && !categories.includes(this.state.activeCategoryFilter)) {
        this.state.activeCategoryFilter = "ALL";
      }
      catSelect.value = this.state.activeCategoryFilter;
    }

    tbody.innerHTML = "";

    const query = (this.state.searchQuery || "").toLowerCase().trim();
    const catFilter = this.state.activeCategoryFilter;

    const filtered = this.state.items.filter(item => {
      const matchesCat = catFilter === "ALL" || (item.category || "General").toLowerCase() === catFilter.toLowerCase();
      const matchesQuery = !query ||
        (item.name || "").toLowerCase().includes(query) ||
        (item.category || "").toLowerCase().includes(query) ||
        (item.description || "").toLowerCase().includes(query);
      return matchesCat && matchesQuery;
    });

    if (countEl) countEl.textContent = `${filtered.length} Items`;

    if (filtered.length === 0) {
      tbody.innerHTML = `<tr><td colspan="7" class="text-center py-4">No menu items found.</td></tr>`;
      return;
    }

    filtered.forEach(item => {
      const price = parseFloat(item.selling_price ?? item.price ?? 0);
      const cost = parseFloat(item.cost_price ?? item.cost ?? 0);
      const margin = price - cost;
      const foodCostPct = price > 0 ? (cost / price * 100).toFixed(1) : 0;
      const isActive = item.is_active !== false;
      const desc = (item.description || "").trim();

      const tr = document.createElement("tr");
      tr.className = isActive ? "" : "item-archived";
      tr.innerHTML = `
        <td>
          <div class="menu-item-info" style="display: flex; flex-direction: column; gap: 0.15rem;">
            <div>
              <span class="font-bold">${escapeHtml(item.name)}</span>
              ${!isActive ? '<span class="badge badge-archived">Archived</span>' : ""}
            </div>
            ${desc ? `<small style="color: var(--text-muted); font-size: 0.78rem;">${escapeHtml(desc)}</small>` : ""}
          </div>
        </td>
        <td><span class="category-tag">${escapeHtml(item.category || "General")}</span></td>
        <td><strong>${formatCurrency(price)}</strong></td>
        <td><span class="cost-tag">${formatCurrency(cost)}</span></td>
        <td>
          <span class="pct-pill ${foodCostPct > 35 ? "pct-high" : foodCostPct > 28 ? "pct-medium" : "pct-low"}">
            ${foodCostPct}%
          </span>
        </td>
        <td><strong class="text-emerald">+${formatCurrency(margin)}</strong></td>
        <td>
          <div class="table-actions">
            <button class="btn btn-secondary btn-xs btn-open-recipe" data-id="${item.id}" title="Manage Recipe BOM">
              🥣 Recipe
            </button>
            <button class="btn btn-secondary btn-xs btn-edit-item" data-id="${item.id}" title="Edit Item">
              ✏️ Edit
            </button>
            <button class="btn btn-danger btn-xs btn-delete-item" data-id="${item.id}" title="Delete Item">
              🗑️ Delete
            </button>
          </div>
        </td>
      `;

      tr.querySelector(".btn-open-recipe")?.addEventListener("click", () => this.openRecipeModal(item));
      tr.querySelector(".btn-edit-item")?.addEventListener("click", () => this.openEditModal(item));
      tr.querySelector(".btn-delete-item")?.addEventListener("click", () => this.deleteItem(item));

      tbody.appendChild(tr);
    });
  },

  async handleCreateItem(e) {
    e.preventDefault();
    if (!api.isAuthenticated()) {
      showToast("Please sign in to create menu items.", "error");
      return;
    }

    const name = document.getElementById("new-item-name")?.value;
    const category = document.getElementById("new-item-category")?.value;
    const price = parseFloat(document.getElementById("new-item-price")?.value || 0);
    const cost = parseFloat(document.getElementById("new-item-cost")?.value || 0);
    const description = document.getElementById("new-item-description")?.value || "";

    const payload = {
      name,
      category,
      selling_price: price,
      cost_price: cost,
      description,
      is_active: true
    };

    try {
      const res = await api.post("/api/v1/menu/", payload);
      const modal = document.getElementById("add-menu-modal");
      if (modal) modal.close();
      e.target.reset();

      if (res && res.data) {
        this.state.items.unshift(res.data);
        showToast(`Menu item '${name}' created successfully!`, "success");
      }
      this.render();
      matrix.loadMatrix();
    } catch (err) {
      showToast(`Failed to create dish: ${err.message}`, "error");
    }
  },

  openEditModal(item) {
    const modal = document.getElementById("edit-menu-modal");
    if (!modal) return;

    document.getElementById("edit-item-id").value = item.id;
    document.getElementById("edit-item-name").value = item.name || "";
    document.getElementById("edit-item-category").value = item.category || "General";
    document.getElementById("edit-item-price").value = parseFloat(item.selling_price ?? item.price ?? 0);
    document.getElementById("edit-item-cost").value = parseFloat(item.cost_price ?? item.cost ?? 0);
    document.getElementById("edit-item-description").value = item.description || "";

    modal.showModal();
  },

  async handleUpdateItem(e) {
    e.preventDefault();
    const itemId = document.getElementById("edit-item-id")?.value;
    const name = document.getElementById("edit-item-name")?.value.trim();
    const category = document.getElementById("edit-item-category")?.value.trim() || "General";
    const sellingPrice = parseFloat(document.getElementById("edit-item-price")?.value || 0);
    const costPrice = parseFloat(document.getElementById("edit-item-cost")?.value || 0);
    const description = document.getElementById("edit-item-description")?.value.trim() || "";

    if (!itemId || !name || isNaN(sellingPrice) || sellingPrice < 0) {
      showToast("Please provide a valid name and selling price.", "error");
      return;
    }

    try {
      const res = await api.put(`/api/v1/menu/${itemId}`, {
        name,
        category,
        selling_price: sellingPrice,
        cost_price: costPrice,
        description
      });

      const modal = document.getElementById("edit-menu-modal");
      if (modal) modal.close();

      const idx = this.state.items.findIndex(i => String(i.id) === String(itemId));
      if (idx !== -1 && res?.data) {
        this.state.items[idx] = res.data;
      }

      showToast(`Updated '${name}' successfully!`, "success");
      this.render();
      matrix.loadMatrix();
    } catch (err) {
      showToast(`Failed to update dish: ${err.message}`, "error");
    }
  },

  async deleteItem(item) {
    if (!confirm(`Delete "${item.name}" from your menu catalog?`)) return;
    try {
      await api.delete(`/api/v1/menu/${item.id}?permanent=true`);
      this.state.items = this.state.items.filter(i => String(i.id) !== String(item.id));
      showToast(`Deleted '${item.name}' from menu.`, "info");
      this.render();
      matrix.loadMatrix();
    } catch (err) {
      showToast(`Failed to delete item: ${err.message}`, "error");
    }
  },

  // =========================================================================
  // Menu Scan & Editable Review Workflow
  // =========================================================================
  openScanModal() {
    if (!api.isAuthenticated()) {
      showToast("Please sign in to scan and import a menu.", "error");
      return;
    }
    const modal = document.getElementById("scan-menu-modal");
    if (modal) modal.showModal();
  },

  handleScanFileSelected(e) {
    const file = e.target.files?.[0];
    if (!file) return;

    this.state.selectedScanMimeType = file.type || "image/jpeg";
    const reader = new FileReader();
    reader.onload = () => {
      const dataUrl = reader.result;
      this.state.selectedScanImageBase64 = dataUrl;
      const previewImg = document.getElementById("scan-image-preview");
      const previewWrap = document.getElementById("scan-image-preview-wrap");
      if (previewImg) previewImg.src = dataUrl;
      if (previewWrap) previewWrap.style.display = "block";
    };
    reader.readAsDataURL(file);
  },

  async _runBrowserOcrIfNeeded(imageDataUrl) {
    if (!imageDataUrl) return "";
    const statusEl = document.getElementById("scan-status-text");
    try {
      if (!window.Tesseract) {
        if (statusEl) statusEl.textContent = "Loading OCR engine...";
        await new Promise((resolve, reject) => {
          const script = document.createElement("script");
          script.src = "https://cdn.jsdelivr.net/npm/tesseract.js@5/dist/tesseract.min.js";
          script.onload = resolve;
          script.onerror = reject;
          document.head.appendChild(script);
        });
      }
      if (statusEl) statusEl.textContent = "Running OCR on menu screenshot...";
      const result = await window.Tesseract.recognize(imageDataUrl, "eng");
      return result?.data?.text || "";
    } catch {
      return "";
    }
  },

  async runMenuScan() {
    const runBtn = document.getElementById("btn-run-menu-scan");
    const statusEl = document.getElementById("scan-status-text");
    const ocrTextarea = document.getElementById("scan-ocr-text");

    let ocrText = (ocrTextarea?.value || "").trim();
    const imageBase64 = this.state.selectedScanImageBase64;

    if (!imageBase64 && !ocrText) {
      showToast("Upload a menu screenshot or enter menu text first.", "error");
      return;
    }

    if (runBtn) runBtn.disabled = true;
    if (statusEl) statusEl.textContent = "Extracting menu items...";

    try {
      // First send to backend /api/v1/menu/scan
      let res = await api.post("/api/v1/menu/scan", {
        image_base64: imageBase64,
        mime_type: this.state.selectedScanMimeType,
        ocr_text: ocrText
      });

      // If only an image was provided and no server Vision API key is configured, run browser OCR
      if ((!res.items || res.items.length === 0) && imageBase64 && !ocrText) {
        const extractedText = await this._runBrowserOcrIfNeeded(imageBase64);
        if (extractedText && ocrTextarea) {
          ocrTextarea.value = extractedText;
          res = await api.post("/api/v1/menu/scan", {
            image_base64: imageBase64,
            mime_type: this.state.selectedScanMimeType,
            ocr_text: extractedText
          });
        }
      }

      const items = Array.isArray(res?.items) ? res.items : [];
      this.state.scannedItems = items.map(item => ({
        selected: true,
        name: item.name || "",
        category: item.category || "General",
        selling_price: parseFloat(item.selling_price ?? 0),
        cost_price: parseFloat(item.cost_price ?? 0),
        description: item.description || ""
      }));

      this.renderScanReviewRows();

      if (items.length > 0) {
        if (statusEl) statusEl.textContent = `Extracted ${items.length} menu items. Review and edit below before saving.`;
        showToast(`Extracted ${items.length} menu items for review!`, "success");
      } else {
        if (statusEl) statusEl.textContent = "No structured items detected. You can paste menu text or add rows manually.";
        showToast("No items automatically detected from image. Add or paste menu lines above.", "info");
      }
    } catch (err) {
      if (statusEl) statusEl.textContent = `Scan error: ${err.message}`;
      showToast(`Menu scan failed: ${err.message}`, "error");
    } finally {
      if (runBtn) runBtn.disabled = false;
    }
  },

  renderScanReviewRows() {
    const section = document.getElementById("scan-review-section");
    const tbody = document.getElementById("scan-review-rows");
    const countEl = document.getElementById("scan-review-count");
    const saveBtn = document.getElementById("btn-save-scanned-menu");

    if (!tbody || !section) return;

    section.style.display = this.state.scannedItems.length > 0 ? "block" : "none";
    if (countEl) countEl.textContent = String(this.state.scannedItems.length);
    if (saveBtn) saveBtn.disabled = this.state.scannedItems.length === 0;

    tbody.innerHTML = "";

    this.state.scannedItems.forEach((item, index) => {
      const tr = document.createElement("tr");
      tr.className = "scan-review-row";
      tr.innerHTML = `
        <td>
          <input type="checkbox" class="scan-row-check" ${item.selected !== false ? "checked" : ""}>
        </td>
        <td>
          <input type="text" class="form-input scan-row-name" value="${escapeHtml(item.name)}" placeholder="Dish name">
        </td>
        <td>
          <input type="text" class="form-input scan-row-category" list="menu-category-datalist" value="${escapeHtml(item.category)}" placeholder="Category">
        </td>
        <td>
          <input type="number" step="0.01" min="0" class="form-input scan-row-price" value="${item.selling_price}">
        </td>
        <td>
          <input type="number" step="0.01" min="0" class="form-input scan-row-cost" value="${item.cost_price}">
        </td>
        <td>
          <input type="text" class="form-input scan-row-desc" value="${escapeHtml(item.description || "")}" placeholder="Description / Sizes">
        </td>
        <td>
          <button type="button" class="btn btn-danger btn-xs btn-remove-scan-row">✕</button>
        </td>
      `;

      tr.querySelector(".scan-row-check")?.addEventListener("change", (e) => {
        this.state.scannedItems[index].selected = e.target.checked;
      });
      tr.querySelector(".scan-row-name")?.addEventListener("input", (e) => {
        this.state.scannedItems[index].name = e.target.value;
      });
      tr.querySelector(".scan-row-category")?.addEventListener("input", (e) => {
        this.state.scannedItems[index].category = e.target.value;
      });
      tr.querySelector(".scan-row-price")?.addEventListener("input", (e) => {
        this.state.scannedItems[index].selling_price = parseFloat(e.target.value || 0);
      });
      tr.querySelector(".scan-row-cost")?.addEventListener("input", (e) => {
        this.state.scannedItems[index].cost_price = parseFloat(e.target.value || 0);
      });
      tr.querySelector(".scan-row-desc")?.addEventListener("input", (e) => {
        this.state.scannedItems[index].description = e.target.value;
      });
      tr.querySelector(".btn-remove-scan-row")?.addEventListener("click", () => {
        this.state.scannedItems.splice(index, 1);
        this.renderScanReviewRows();
      });

      tbody.appendChild(tr);
    });
  },

  addScanRow() {
    this.state.scannedItems.push({
      selected: true,
      name: "",
      category: "General",
      selling_price: 0,
      cost_price: 0,
      description: ""
    });
    this.renderScanReviewRows();
  },

  async saveScannedMenu() {
    const saveBtn = document.getElementById("btn-save-scanned-menu");
    const verifiedItems = this.state.scannedItems
      .filter(i => i.selected !== false && (i.name || "").trim() !== "")
      .map(i => ({
        name: i.name.trim(),
        category: (i.category || "General").trim() || "General",
        selling_price: parseFloat(i.selling_price || 0),
        cost_price: parseFloat(i.cost_price || 0),
        description: (i.description || "").trim(),
        is_active: true
      }));

    if (verifiedItems.length === 0) {
      showToast("Please select at least one valid dish with a name to save.", "error");
      return;
    }

    if (saveBtn) saveBtn.disabled = true;

    try {
      const res = await api.post("/api/v1/menu/bulk", { items: verifiedItems });
      const modal = document.getElementById("scan-menu-modal");
      if (modal) modal.close();

      this.state.scannedItems = [];
      this.renderScanReviewRows();

      showToast(`Saved ${res.inserted_count || verifiedItems.length} menu items to Supabase!`, "success");
      await this.loadMenu();
      await matrix.loadMatrix();
    } catch (err) {
      showToast(`Failed to save scanned menu: ${err.message}`, "error");
    } finally {
      if (saveBtn) saveBtn.disabled = false;
    }
  },

  // =========================================================================
  // Recipe Bill-of-Materials (BOM) Modal
  // =========================================================================
  async openRecipeModal(item) {
    this.state.selectedItem = item;
    const modal = document.getElementById("recipe-modal");
    const title = document.getElementById("recipe-modal-title");
    const sub = document.getElementById("recipe-modal-sub");

    if (title) title.textContent = `Recipe: ${item.name}`;
    if (sub) sub.textContent = `Selling Price: ${formatCurrency(item.selling_price ?? item.price)} | Plate Target < 30%`;

    try {
      const res = await api.get(`/api/v1/menu/${item.id}/recipe`);
      this.state.recipeIngredients = Array.isArray(res?.ingredients) ? res.ingredients : [];
    } catch (err) {
      this.state.recipeIngredients = [];
      showToast(`Failed to load recipe: ${err.message}`, "error");
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
        <input type="text" class="form-input ing-name" placeholder="Ingredient name" value="${escapeHtml(ing.ingredient_name || "")}">
        <input type="number" step="0.001" min="0" class="form-input ing-qty" placeholder="Qty" value="${ing.quantity || ""}">
        <input type="text" class="form-input ing-unit" placeholder="Unit (kg, g, l)" value="${escapeHtml(ing.unit || "portion")}">
        <input type="number" step="0.01" min="0" class="form-input ing-cost" placeholder="Unit Cost" value="${ing.unit_cost || ""}">
        <span class="ing-subtotal font-bold">${formatCurrency((ing.quantity || 0) * (ing.unit_cost || 0))}</span>
        <button type="button" class="btn btn-danger btn-xs btn-remove-ing">✕</button>
      `;

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
    const price = this.state.selectedItem ? (this.state.selectedItem.selling_price ?? this.state.selectedItem.price ?? 0) : 0;

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

    try {
      const res = await api.post(`/api/v1/menu/${this.state.selectedItem.id}/recipe`, { ingredients });
      const modal = document.getElementById("recipe-modal");
      if (modal) modal.close();

      const newCost = res && res.calculated_cost_price !== undefined
        ? res.calculated_cost_price
        : ingredients.reduce((sum, i) => sum + (i.quantity * i.unit_cost), 0);

      this.state.selectedItem.cost_price = newCost;
      this.state.selectedItem.cost = newCost;

      showToast(`Recipe saved! Plate cost updated to ${formatCurrency(newCost)}.`, "success");
      this.render();
      matrix.loadMatrix();
    } catch (err) {
      showToast(`Failed to save recipe: ${err.message}`, "error");
    }
  }
};

function escapeHtml(str) {
  return String(str || "").replace(/[&<>'"]/g,
    tag => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[tag] || tag)
  );
}
