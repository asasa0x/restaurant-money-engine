/**
 * Restaurant Money Engine - Unified Live API Client & Session Manager
 */

const getApiBaseUrl = () => {
  if (window.__ENV__?.API_BASE_URL) {
    return window.__ENV__.API_BASE_URL.replace(/\/$/, "");
  }
  const customOverride = localStorage.getItem("rme_api_base_url");
  if (customOverride && !customOverride.includes("onrender.com")) {
    return customOverride.replace(/\/$/, "");
  }
  const isLocal = window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1";
  if (isLocal) {
    return window.location.port === "5000" ? "" : "http://127.0.0.1:5000";
  }
  return "";
};

const API_BASE_URL = getApiBaseUrl();

// Clean zeroed baseline state when a restaurant has no recorded data yet
export const EMPTY_STATE = {
  financials: {
    gross_sales: 0.0,
    cogs: 0.0,
    labor_cost: 0.0,
    prime_cost: 0.0,
    prime_cost_pct: null,
    target_prime_cost_pct: 60.0,
    status: "NO_DATA"
  },
  menu_matrix: {
    benchmarks: {
      average_contribution_margin: 0.0,
      popularity_threshold: 0.0,
      average_volume: 0.0,
      total_volume: 0
    },
    summary: { stars: 0, plowhorses: 0, puzzles: 0, dogs: 0 },
    quadrants: {
      stars: [],
      plowhorses: [],
      puzzles: [],
      dogs: []
    }
  }
};

class ApiService {
  constructor() {
    this.token = localStorage.getItem("rme_auth_token") || "";
    this.user = this._readJson("rme_auth_user");
    this.restaurant = this._readJson("rme_auth_restaurant");
  }

  _readJson(key) {
    try {
      const raw = localStorage.getItem(key);
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  }

  setToken(token) {
    this.token = (token || "").trim();
    if (this.token) {
      localStorage.setItem("rme_auth_token", this.token);
    } else {
      localStorage.removeItem("rme_auth_token");
    }
  }

  setSession({ access_token, user, restaurant }) {
    this.setToken(access_token || "");
    this.user = user || null;
    this.restaurant = restaurant || null;

    if (this.user) {
      localStorage.setItem("rme_auth_user", JSON.stringify(this.user));
    } else {
      localStorage.removeItem("rme_auth_user");
    }

    if (this.restaurant) {
      localStorage.setItem("rme_auth_restaurant", JSON.stringify(this.restaurant));
    } else {
      localStorage.removeItem("rme_auth_restaurant");
    }
  }

  clearSession() {
    this.setToken("");
    this.user = null;
    this.restaurant = null;
    localStorage.removeItem("rme_auth_user");
    localStorage.removeItem("rme_auth_restaurant");
  }

  getToken() {
    return this.token;
  }

  getUser() {
    return this.user;
  }

  getRestaurant() {
    return this.restaurant;
  }

  isAuthenticated() {
    return Boolean(this.token);
  }

  getHeaders() {
    const headers = {
      "Content-Type": "application/json",
      "Accept": "application/json"
    };
    if (this.token) {
      headers["Authorization"] = `Bearer ${this.token}`;
    }
    return headers;
  }

  async request(endpoint, options = {}) {
    const url = `${API_BASE_URL}${endpoint}`;
    const response = await fetch(url, {
      ...options,
      headers: {
        ...this.getHeaders(),
        ...(options.headers || {})
      }
    });

    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
      if (response.status === 401 && !endpoint.startsWith("/api/v1/auth/")) {
        window.dispatchEvent(
          new CustomEvent("rme:unauthorized", { detail: { endpoint, error: data.error } })
        );
      }
      const err = new Error(data.error || `HTTP ${response.status}`);
      err.status = response.status;
      err.code = data.code;
      throw err;
    }

    return data;
  }

  get(endpoint) {
    return this.request(endpoint, { method: "GET" });
  }

  post(endpoint, body) {
    return this.request(endpoint, {
      method: "POST",
      body: JSON.stringify(body)
    });
  }

  put(endpoint, body) {
    return this.request(endpoint, {
      method: "PUT",
      body: JSON.stringify(body)
    });
  }

  delete(endpoint) {
    return this.request(endpoint, { method: "DELETE" });
  }
}

export const api = new ApiService();

// Toast Notification Manager
export function showToast(message, type = "info") {
  let container = document.getElementById("toast-container");
  if (!container) {
    container = document.createElement("div");
    container.id = "toast-container";
    container.className = "toast-container";
    document.body.appendChild(container);
  }

  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;

  const icon = type === "success" ? "✓" : type === "error" ? "✕" : "ℹ";
  toast.innerHTML = `
    <span class="toast-icon">${icon}</span>
    <span class="toast-message">${message}</span>
  `;

  container.appendChild(toast);

  setTimeout(() => {
    toast.classList.add("toast-fadeout");
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}

export function formatCurrency(num) {
  const val = Number(num || 0);
  const currency = (api.getRestaurant()?.currency || "USD").toUpperCase();
  if (currency === "PKR" || currency === "RS") {
    return `Rs. ${val.toLocaleString("en-PK", { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`;
  }
  return new Intl.NumberFormat("en-US", { style: "currency", currency }).format(val);
}
