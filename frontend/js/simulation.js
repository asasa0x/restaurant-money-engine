/**
 * Restaurant Money Engine - What-If Profit Simulation Engine
 */

import { api, EMPTY_STATE, showToast, formatCurrency } from "./api.js";
import { dashboard } from "./dashboard.js";

export const simulation = {
  state: {
    inflationPct: 0.0,
    pricePct: 0.0,
    laborPct: 0.0,
    debounceTimer: null,
    currentResult: null
  },

  init() {
    this.bindEvents();
    this.runSimulation();
  },

  reset() {
    this.state.currentResult = null;
    this.computeLocalPreview(EMPTY_STATE.financials);
  },

  bindEvents() {
    const sliders = [
      { id: "slider-inflation", prop: "inflationPct", labelId: "val-inflation" },
      { id: "slider-price", prop: "pricePct", labelId: "val-price" },
      { id: "slider-labor", prop: "laborPct", labelId: "val-labor" }
    ];

    sliders.forEach(({ id, prop, labelId }) => {
      const slider = document.getElementById(id);
      const label = document.getElementById(labelId);

      if (slider) {
        slider.addEventListener("input", (e) => {
          const val = parseFloat(e.target.value || 0);
          this.state[prop] = val;
          if (label) {
            label.textContent = `${val >= 0 ? "+" : ""}${val}%`;
          }

          // Instant visual preview from active restaurant's baseline
          this.computeLocalPreview();

          // Debounced backend API call
          clearTimeout(this.state.debounceTimer);
          this.state.debounceTimer = setTimeout(() => {
            this.runSimulation();
          }, 300);
        });
      }
    });

    const resetBtn = document.getElementById("btn-reset-simulation");
    if (resetBtn) {
      resetBtn.addEventListener("click", () => this.resetSliders());
    }
  },

  resetSliders() {
    this.state.inflationPct = 0.0;
    this.state.pricePct = 0.0;
    this.state.laborPct = 0.0;

    const ids = ["slider-inflation", "slider-price", "slider-labor"];
    ids.forEach(id => {
      const el = document.getElementById(id);
      if (el) el.value = "0";
    });

    const labels = ["val-inflation", "val-price", "val-labor"];
    labels.forEach(id => {
      const el = document.getElementById(id);
      if (el) el.textContent = "+0%";
    });

    this.runSimulation();
  },

  computeLocalPreview(explicitBaseline = null) {
    const base = explicitBaseline || dashboard.state.financials || EMPTY_STATE.financials;
    const baseSales = parseFloat(base.gross_sales || 0);
    const baseCogs = parseFloat(base.cogs || 0);
    const baseLabor = parseFloat(base.labor_cost || 0);
    const basePrime = baseCogs + baseLabor;
    const basePrimePct = baseSales > 0 ? (basePrime / baseSales) * 100 : 0;
    const baseMargin = baseSales - basePrime;

    const pMult = 1.0 + (this.state.pricePct / 100.0);
    const cMult = 1.0 + (this.state.inflationPct / 100.0);
    const lMult = 1.0 + (this.state.laborPct / 100.0);

    const projSales = baseSales * pMult;
    const projCogs = baseCogs * cMult;
    const projLabor = baseLabor * lMult;
    const projPrime = projCogs + projLabor;
    const projPrimePct = projSales > 0 ? (projPrime / projSales) * 100 : 0;
    const projMargin = projSales - projPrime;
    const marginDelta = projMargin - baseMargin;

    this.renderMetrics({
      baseline: {
        gross_sales: baseSales,
        cogs: baseCogs,
        labor_cost: baseLabor,
        prime_cost: basePrime,
        prime_cost_pct: basePrimePct,
        prime_margin: baseMargin
      },
      projected: {
        gross_sales: projSales,
        cogs: projCogs,
        labor_cost: projLabor,
        prime_cost: projPrime,
        prime_cost_pct: projPrimePct,
        prime_margin: projMargin
      },
      impact: {
        margin_delta: marginDelta,
        prime_cost_delta: projPrime - basePrime,
        is_gain: marginDelta >= 0
      }
    });
  },

  async runSimulation() {
    if (!api.isAuthenticated()) {
      this.reset();
      return;
    }

    const payload = {
      ingredient_inflation_pct: this.state.inflationPct,
      price_change_pct: this.state.pricePct,
      labor_change_pct: this.state.laborPct
    };

    try {
      const res = await api.post("/api/v1/simulation/run", payload);
      if (res && res.simulation) {
        this.state.currentResult = res.simulation;
        this.renderMetrics(res.simulation);
      }
    } catch (err) {
      this.computeLocalPreview();
      if (err.status !== 401) {
        showToast(`Simulation error: ${err.message}`, "error");
      }
    }
  },

  renderMetrics(data) {
    if (!data) return;

    const b = data.baseline || {};
    const p = data.projected || {};
    const imp = data.impact || {};

    // 1. Forecast Impact Hero Callout
    const heroDelta = document.getElementById("sim-hero-delta");
    const heroTitle = document.getElementById("sim-hero-sub");

    if (heroDelta) {
      const isGain = imp.is_gain !== false;
      heroDelta.textContent = `${isGain ? "+" : ""}${formatCurrency(imp.margin_delta || 0)}`;
      heroDelta.className = `hero-delta-val ${isGain ? "text-emerald" : "text-rose"}`;
    }

    if (heroTitle) {
      heroTitle.textContent = imp.is_gain
        ? "Projected Monthly Prime Margin Expansion"
        : "Projected Monthly Prime Margin Contraction";
    }

    // 2. Comparison Metrics Grid
    setText("sim-base-sales", formatCurrency(b.gross_sales));
    setText("sim-proj-sales", formatCurrency(p.gross_sales));

    setText("sim-base-cogs", formatCurrency(b.cogs));
    setText("sim-proj-cogs", formatCurrency(p.cogs));

    setText("sim-base-labor", formatCurrency(b.labor_cost));
    setText("sim-proj-labor", formatCurrency(p.labor_cost));

    setText("sim-base-prime-pct", `${(b.prime_cost_pct || 0).toFixed(1)}%`);
    setText("sim-proj-prime-pct", `${(p.prime_cost_pct || 0).toFixed(1)}%`);

    setText("sim-base-margin", formatCurrency(b.prime_margin));
    setText("sim-proj-margin", formatCurrency(p.prime_margin));
  }
};

function setText(id, text) {
  const el = document.getElementById(id);
  if (el) el.textContent = text;
}
