/**
 * Restaurant Money Engine - Main Application Coordinator
 */

import { api, showToast } from "./api.js";
import { dashboard } from "./dashboard.js";
import { matrix } from "./matrix.js";
import { menu } from "./menu.js";
import { simulation } from "./simulation.js";

document.addEventListener("DOMContentLoaded", async () => {
  setupTabs();
  setupHealthCheck();
  setupAuthModal();

  // Bind domain module events
  dashboard.bindEvents();
  matrix.bindEvents();
  menu.bindEvents();
  simulation.bindEvents();

  // Verify existing session or prompt login
  await initializeSession();
});

async function initializeSession() {
  if (!api.isAuthenticated()) {
    resetAllViews();
    const authModal = document.getElementById("auth-modal");
    if (authModal && !authModal.open) {
      authModal.showModal();
    }
    return;
  }

  try {
    const me = await api.get("/api/v1/auth/me");
    if (me && me.user && me.restaurant) {
      api.setSession({
        access_token: api.getToken(),
        user: me.user,
        restaurant: me.restaurant
      });
      updateAuthHeaderUI();
      await reloadAllModules();
    }
  } catch {
    api.clearSession();
    updateAuthHeaderUI();
    resetAllViews();
  }
}

async function reloadAllModules() {
  await Promise.all([
    dashboard.loadFinancials(),
    matrix.loadMatrix(),
    menu.loadMenu(),
    simulation.runSimulation()
  ]);
}

function resetAllViews() {
  dashboard.reset();
  matrix.reset();
  menu.reset();
  simulation.reset();
}

function updateAuthHeaderUI() {
  const statusEl = document.getElementById("auth-status-chip");
  const switcher = document.getElementById("restaurant-select");
  const clearBtn = document.getElementById("btn-clear-token");
  const openBtn = document.getElementById("btn-open-auth-modal");

  const isAuth = api.isAuthenticated();
  const user = api.getUser();
  const restaurant = api.getRestaurant();

  if (statusEl) {
    statusEl.textContent = isAuth
      ? (user?.email ? `${user.email}` : "Authenticated")
      : "Not Signed In";
    statusEl.className = `auth-chip ${isAuth ? "auth-connected" : "auth-demo"}`;
  }

  if (switcher) {
    switcher.innerHTML = "";
    const opt = document.createElement("option");
    if (isAuth && restaurant) {
      opt.value = restaurant.id || "";
      opt.textContent = `${restaurant.name} (${restaurant.currency || "USD"})`;
    } else {
      opt.value = "";
      opt.textContent = "Sign in to load restaurant";
    }
    switcher.appendChild(opt);
  }

  if (clearBtn) {
    clearBtn.style.display = isAuth ? "inline-flex" : "none";
  }

  if (openBtn) {
    openBtn.textContent = isAuth ? "Account" : "Sign In / Account";
  }
}

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
        if (label) label.textContent = `API Online (${res.environment || "live"})`;
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
  setInterval(check, 30000);
}

// Real Supabase Auth modal (Login & Restaurant Account Signup)
function setupAuthModal() {
  const authBtn = document.getElementById("btn-open-auth-modal");
  const authModal = document.getElementById("auth-modal");
  const closeBtn = document.getElementById("btn-close-auth-modal");
  const form = document.getElementById("auth-form");
  const clearBtn = document.getElementById("btn-clear-token");

  const modeLoginBtn = document.getElementById("btn-mode-login");
  const modeSignupBtn = document.getElementById("btn-mode-signup");
  const headingEl = document.getElementById("auth-modal-heading");
  const restGroupEl = document.getElementById("auth-restaurant-group");
  const restInputEl = document.getElementById("auth-restaurant-name");
  const emailInputEl = document.getElementById("auth-email-input");
  const passwordInputEl = document.getElementById("auth-password-input");
  const submitBtnEl = document.getElementById("btn-submit-auth");

  let mode = "login"; // "login" | "signup"

  const setMode = (nextMode) => {
    mode = nextMode;
    const isSignup = mode === "signup";
    if (headingEl) {
      headingEl.textContent = isSignup ? "Create Restaurant Account" : "Restaurant Account Sign In";
    }
    if (restGroupEl) {
      restGroupEl.style.display = isSignup ? "block" : "none";
    }
    if (restInputEl) {
      restInputEl.required = isSignup;
    }
    if (submitBtnEl) {
      submitBtnEl.textContent = isSignup ? "Create Account & Sign In" : "Sign In";
    }
    if (modeLoginBtn) {
      modeLoginBtn.className = `btn ${isSignup ? "btn-secondary" : "btn-primary"} btn-xs`;
    }
    if (modeSignupBtn) {
      modeSignupBtn.className = `btn ${isSignup ? "btn-primary" : "btn-secondary"} btn-xs`;
    }
  };

  if (modeLoginBtn) modeLoginBtn.addEventListener("click", () => setMode("login"));
  if (modeSignupBtn) modeSignupBtn.addEventListener("click", () => setMode("signup"));

  updateAuthHeaderUI();

  if (authBtn && authModal) authBtn.addEventListener("click", () => authModal.showModal());
  if (closeBtn && authModal) closeBtn.addEventListener("click", () => authModal.close());

  window.addEventListener("rme:unauthorized", () => {
    api.clearSession();
    updateAuthHeaderUI();
    resetAllViews();
    if (authModal && !authModal.open) {
      authModal.showModal();
    }
  });

  if (form) {
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const email = (emailInputEl?.value || "").trim();
      const password = passwordInputEl?.value || "";
      const restaurantName = (restInputEl?.value || "").trim();

      if (submitBtnEl) submitBtnEl.disabled = true;

      try {
        const endpoint = mode === "signup" ? "/api/v1/auth/signup" : "/api/v1/auth/login";
        const payload = mode === "signup"
          ? { email, password, restaurant_name: restaurantName }
          : { email, password };

        const res = await api.post(endpoint, payload);
        api.setSession({
          access_token: res.access_token,
          user: res.user,
          restaurant: res.restaurant
        });

        updateAuthHeaderUI();
        form.reset();
        if (authModal) authModal.close();

        showToast(
          mode === "signup"
            ? `Workspace '${res.restaurant?.name}' created!`
            : `Signed in to '${res.restaurant?.name}'!`,
          "success"
        );

        await reloadAllModules();
      } catch (err) {
        showToast(err.message || "Authentication failed", "error");
      } finally {
        if (submitBtnEl) submitBtnEl.disabled = false;
      }
    });
  }

  if (clearBtn) {
    clearBtn.addEventListener("click", () => {
      api.clearSession();
      updateAuthHeaderUI();
      resetAllViews();
      showToast("Signed out of restaurant workspace.", "info");
    });
  }
}
