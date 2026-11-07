/**
 * Restaurant Money Engine - Unified API Client & Toast Manager
 */

// Dynamic API Base URL resolution:
// 1. Injected environment config: window.__ENV__?.API_BASE_URL
// 2. Local developer override: localStorage.getItem("rme_api_base_url")
// 3. Local development loop: http://127.0.0.1:5000
// 4. Production Vercel deployment: points to Render backend service
const getApiBaseUrl = () => {
  if (window.__ENV__?.API_BASE_URL) {
    return window.__ENV__.API_BASE_URL.replace(/\/$/, "");
  }
  const customOverride = localStorage.getItem("rme_api_base_url");
  if (customOverride) {
    return customOverride.replace(/\/$/, "");
  }
  const isLocal = window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1";
  if (isLocal) {
    return window.location.port === "5000" ? "" : "http://127.0.0.1:5000";
  }
  return "https://restaurant-money-engine-api.onrender.com";
};

const API_BASE_URL = getApiBaseUrl();

// Default mock demonstration dataset when offline or unauthenticated
const DEMO_STORE = {
  restaurant_id: "rest_demo_777",
  financials: {
    gross_sales: 64500.00,
    cogs: 18705.00,
    labor_cost: 19350.00,
    prime_cost: 38055.00,
    prime_cost_pct: 59.0,
    target_prime_cost_pct: 60.0,
    status: "HEALTHY"
  },
  menu_matrix: {
    benchmarks: {
      average_contribution_margin: 16.80,
      popularity_threshold: 140.0,
      average_volume: 200.0,
      total_volume: 1200
    },
    summary: { stars: 2, plowhorses: 2, puzzles: 1, dogs: 1 },
    quadrants: {
      stars: [
        { id: "1", name: "Truffle Tagliatelle", category: "Mains", price: 28.00, cost: 6.20, contribution_margin: 21.80, food_cost_pct: 22.1, volume: 340, quadrant: "Stars", action_recommendation: "Star item. Protect portion consistency and keep prominent." },
        { id: "2", name: "Old Fashioned Cocktail", category: "Beverages", price: 16.00, cost: 2.80, contribution_margin: 13.20, food_cost_pct: 17.5, volume: 380, quadrant: "Stars", action_recommendation: "High margin driver. Feature in pairings." }
      ],
      plowhorses: [
        { id: "3", name: "Prime Ribeye Steak 12oz", category: "Mains", price: 38.00, cost: 17.50, contribution_margin: 20.50, food_cost_pct: 46.1, volume: 310, quadrant: "Plowhorses", action_recommendation: "Popular but high food cost. Test +3% price increase or trim portion." },
        { id: "4", name: "Crispy Calamari", category: "Appetizers", price: 15.00, cost: 7.20, contribution_margin: 7.80, food_cost_pct: 48.0, volume: 290, quadrant: "Plowhorses", action_recommendation: "High sales volume. Negotiate seafood supplier rates." }
      ],
      puzzles: [
        { id: "5", name: "Pan-Seared Chilean Sea Bass", category: "Mains", price: 42.00, cost: 11.00, contribution_margin: 31.00, food_cost_pct: 26.2, volume: 95, quadrant: "Puzzles", action_recommendation: "High profit margin. Train servers to recommend as chef special." }
      ],
      dogs: [
        { id: "6", name: "House Caesar Salad", category: "Appetizers", price: 13.00, cost: 6.50, contribution_margin: 6.50, food_cost_pct: 50.0, volume: 85, quadrant: "Dogs", action_recommendation: "Low volume and poor margin. Re-engineer ingredients or replace." }
      ]
    }
  },
  menu_items: [
    { id: "1", name: "Truffle Tagliatelle", category: "Mains", selling_price: 28.00, cost_price: 6.20, unit_margin: 21.80, food_cost_pct: 22.1, is_active: true },
    { id: "2", name: "Old Fashioned Cocktail", category: "Beverages", selling_price: 16.00, cost_price: 2.80, unit_margin: 13.20, food_cost_pct: 17.5, is_active: true },
    { id: "3", name: "Prime Ribeye Steak 12oz", category: "Mains", selling_price: 38.00, cost_price: 17.50, unit_margin: 20.50, food_cost_pct: 46.1, is_active: true },
    { id: "4", name: "Crispy Calamari", category: "Appetizers", selling_price: 15.00, cost_price: 7.20, unit_margin: 7.80, food_cost_pct: 48.0, is_active: true },
    { id: "5", name: "Pan-Seared Chilean Sea Bass", category: "Mains", selling_price: 42.00, cost_price: 11.00, unit_margin: 31.00, food_cost_pct: 26.2, is_active: true },
    { id: "6", name: "House Caesar Salad", category: "Appetizers", selling_price: 13.00, cost_price: 6.50, unit_margin: 6.50, food_cost_pct: 50.0, is_active: true }
  ],
  recipes: {
    "1": [
      { ingredient_name: "Fresh Tagliatelle", quantity: 0.180, unit: "kg", unit_cost: 6.00 },
      { ingredient_name: "Black Truffle Butter", quantity: 0.030, unit: "kg", unit_cost: 45.00 },
      { ingredient_name: "Parmigiano-Reggiano", quantity: 0.040, unit: "kg", unit_cost: 22.00 },
      { ingredient_name: "Heavy Cream", quantity: 0.060, unit: "l", unit_cost: 5.00 }
    ],
    "3": [
      { ingredient_name: "USDA Prime Ribeye", quantity: 0.350, unit: "kg", unit_cost: 42.00 },
      { ingredient_name: "Herb Garlic Compound Butter", quantity: 0.030, unit: "kg", unit_cost: 18.00 },
      { ingredient_name: "Rosemary & Thyme Garnish", quantity: 1.000, unit: "portion", unit_cost: 0.50 }
    ]
  }
};

class ApiService {
  constructor() {
    this.token = localStorage.getItem("rme_auth_token") || "";
  }

  setToken(token) {
    this.token = token.trim();
    if (this.token) {
      localStorage.setItem("rme_auth_token", this.token);
    } else {
      localStorage.removeItem("rme_auth_token");
    }
  }

  getToken() {
    return this.token;
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
    try {
      const response = await fetch(url, {
        ...options,
        headers: {
          ...this.getHeaders(),
          ...(options.headers || {})
        }
      });

      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        if (response.status === 401) {
          console.warn(`[API] 401 Unauthorized at ${endpoint}. Using fallback mock data.`);
          return { __isFallback: true, error: data.error || "Unauthorized", status: 401 };
        }
        throw new Error(data.error || `HTTP ${response.status}`);
      }

      return data;
    } catch (err) {
      console.warn(`[API] Request to ${endpoint} failed (${err.message}). Using client-side mock fallback.`);
      return { __isFallback: true, error: err.message };
    }
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
export { DEMO_STORE };

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
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(num || 0);
}

