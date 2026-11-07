/**
 * Restaurant Money Engine - Main Application Coordinator
 */

import { api, showToast } from "./api.js";
import { dashboard } from "./dashboard.js";
import { matrix } from "./matrix.js";
import { menu } from "./menu.js";
import { simulation } from "./simulation.js";

document.addEventListener("DOMContentLoaded", () => {
  setupTabs();
  setupHealthCheck();
  setupAuthModal();
  setupRestaurantSwitcher();

  // Initialize all domain modules
  dashboard.init();
  matrix.init();
  menu.init();
  simulation.init();
});

// Tab navigation handler
function setupTabs() {
  const tabButtons = document.querySelectorAll(".nav-tab-btn");
  const tabPanels = document.querySelectorAll(".tab-panel");

  tabButtons.forEach(btn => {
    btn.addEventListener("click", () => {
      const targetId = btn.getAttribute("data-tab");
      
      tabButtons.forEach(b => b.classList.remove("active"));
      tabPanels.forEach(p => p.classList.remove("active"));

      btn.classList.add("active");
      const targetPanel = document.getElementById(targetId);
      if (targetPanel) {
        targetPanel.classList.add("active");
      }
    });
  });
}

// Background health check polling
async function setupHealthCheck() {
  const dot = document.getElementById("header-health-dot");
  const label = document.getElementById("header-health-text");

  async function check() {
    try {
      const res = await api.get("/health");
      if (res && res.status === "healthy") {
        if (dot) dot.className = "indicator-dot online";
        if (label) label.textContent = `API Online (${res.environment || 'live'})`;
      } else {
        if (dot) dot.className = "indicator-dot offline";
        if (label) label.textContent = "API Degraded";
      }
    } catch {
      if (dot) dot.className = "indicator-dot offline";
      if (label) label.textContent = "Backend Offline";
    }
  }

  check();
  setInterval(check, 30000); // Check every 30s
}

// Auth modal for setting Supabase JWT or switching to Demo Mode
function setupAuthModal() {
  const authBtn = document.getElementById("btn-open-auth-modal");
  const authModal = document.getElementById("auth-modal");
  const closeBtn = document.getElementById("btn-close-auth-modal");
  const form = document.getElementById("auth-form");
  const tokenInput = document.getElementById("auth-token-input");
  const statusEl = document.getElementById("auth-status-chip");
  const clearBtn = document.getElementById("btn-clear-token");

  const updateStatusDisplay = () => {
    const hasToken = !!api.getToken();
    if (statusEl) {
      statusEl.textContent = hasToken ? "Supabase JWT Active" : "Demo Session Active";
      statusEl.className = `auth-chip ${hasToken ? 'auth-connected' : 'auth-demo'}`;
    }
    if (tokenInput) {
      tokenInput.value = api.getToken();
    }
  };

  updateStatusDisplay();

  if (authBtn && authModal) authBtn.addEventListener("click", () => authModal.showModal());
  if (closeBtn && authModal) closeBtn.addEventListener("click", () => authModal.close());

  if (form) {
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      const token = tokenInput?.value || "";
      api.setToken(token);
      updateStatusDisplay();
      if (authModal) authModal.close();
      showToast(token ? "Supabase JWT token applied!" : "Switched to demo session.", "success");
      
      // Reload active data with new token context
      dashboard.loadFinancials();
      matrix.loadMatrix();
      menu.loadMenu();
      simulation.runSimulation();
    });
  }

  if (clearBtn) {
    clearBtn.addEventListener("click", () => {
      api.setToken("");
      updateStatusDisplay();
      showToast("Cleared JWT token. Switched to demo session.", "info");
    });
  }
}

// Restaurant switcher mock
function setupRestaurantSwitcher() {
  const switcher = document.getElementById("restaurant-select");
  if (switcher) {
    switcher.addEventListener("change", (e) => {
      const selectedName = e.target.options[e.target.selectedIndex].text;
      showToast(`Switched active context to: ${selectedName}`, "info");
      // Trigger data reload for selected restaurant
      dashboard.loadFinancials();
      matrix.loadMatrix();
      menu.loadMenu();
    });
  }
}
