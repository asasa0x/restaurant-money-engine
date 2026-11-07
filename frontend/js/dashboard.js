/**
 * Restaurant Money Engine - Dashboard & Prime Cost Health
 */

import { api, DEMO_STORE, showToast, formatCurrency } from "./api.js";

export const dashboard = {
  state: {
    financials: { ...DEMO_STORE.financials }
  },

  async init() {
    this.bindEvents();
    await this.loadFinancials();
  },

  bindEvents() {
    const form = document.getElementById("daily-financials-form");
    if (form) {
      form.addEventListener("submit", (e) => this.handleLogFinancials(e));
    }
  },

  async loadFinancials() {
    // If user has a token, we query the latest financial stats or compute from daily entries
    const res = await api.get("/api/v1/daily-financials");
    if (res && !res.__isFallback && res.data) {
      this.state.financials = res.data;
    } else {
      this.state.financials = { ...DEMO_STORE.financials };
    }
    this.render();
  },

  render() {
    const f = this.state.financials;

    // 1. KPI cards
    const salesEl = document.getElementById("kpi-sales");
    const cogsEl = document.getElementById("kpi-cogs");
    const laborEl = document.getElementById("kpi-labor");
    const primeEl = document.getElementById("kpi-prime");

    if (salesEl) salesEl.textContent = formatCurrency(f.gross_sales);
    if (cogsEl) cogsEl.textContent = formatCurrency(f.cogs);
    if (laborEl) laborEl.textContent = formatCurrency(f.labor_cost);
    if (primeEl) primeEl.textContent = formatCurrency(f.prime_cost);

    // 2. Percentages & Status Badge
    const pctEl = document.getElementById("kpi-prime-pct");
    const statusBadge = document.getElementById("prime-status-badge");
    const gaugeFill = document.getElementById("prime-gauge-fill");
    const gaugePointer = document.getElementById("prime-gauge-pointer");

    const primePct = parseFloat(f.prime_cost_pct || 0);
    const targetPct = parseFloat(f.target_prime_cost_pct || 60.0);
    const isHealthy = primePct <= targetPct;

    if (pctEl) {
      pctEl.textContent = `${primePct.toFixed(1)}%`;
    }

    if (statusBadge) {
      statusBadge.textContent = isHealthy ? "HEALTHY" : "ALERT";
      statusBadge.className = `status-pill ${isHealthy ? 'status-healthy' : 'status-alert'}`;
    }

    // 3. Visual Gauge Bar (0% to 100%, with benchmark pin at 60%)
    if (gaugeFill) {
      gaugeFill.style.width = `${Math.min(100, Math.max(0, primePct))}%`;
      gaugeFill.className = `gauge-fill ${isHealthy ? 'gauge-healthy' : 'gauge-alert'}`;
    }

    if (gaugePointer) {
      gaugePointer.style.left = `${Math.min(100, Math.max(0, primePct))}%`;
    }

    // Subtext summaries
    const cogsPctEl = document.getElementById("cogs-pct-sub");
    const laborPctEl = document.getElementById("labor-pct-sub");
    if (cogsPctEl && f.gross_sales > 0) {
      cogsPctEl.textContent = `${((f.cogs / f.gross_sales) * 100).toFixed(1)}% of sales`;
    }
    if (laborPctEl && f.gross_sales > 0) {
      laborPctEl.textContent = `${((f.labor_cost / f.gross_sales) * 100).toFixed(1)}% of sales`;
    }
  },

  async handleLogFinancials(e) {
    e.preventDefault();
    const form = e.target;
    const btn = form.querySelector('button[type="submit"]');

    const sales = parseFloat(document.getElementById("entry-sales")?.value || 0);
    const cogs = parseFloat(document.getElementById("entry-cogs")?.value || 0);
    const labor = parseFloat(document.getElementById("entry-labor")?.value || 0);
    const entryDate = document.getElementById("entry-date")?.value || new Date().toISOString().split("T")[0];

    if (sales <= 0) {
      showToast("Gross sales must be greater than $0", "error");
      return;
    }

    if (btn) btn.disabled = true;

    try {
      const payload = {
        gross_sales: sales,
        cogs: cogs,
        labor_cost: labor,
        date: entryDate,
        target_prime_cost_pct: 60.0
      };

      const res = await api.post("/api/v1/daily-financials", payload);

      if (res && !res.__isFallback && res.metrics) {
        this.state.financials = {
          ...res.metrics,
          gross_sales: sales,
          cogs: cogs,
          labor_cost: labor
        };
        showToast("Daily financials recorded in Supabase database!", "success");
      } else {
        // Fallback local calculation
        const prime = cogs + labor;
        const pct = (prime / sales) * 100;
        this.state.financials = {
          gross_sales: sales,
          cogs: cogs,
          labor_cost: labor,
          prime_cost: prime,
          prime_cost_pct: Math.round(pct * 10) / 10,
          target_prime_cost_pct: 60.0,
          status: pct <= 60.0 ? "HEALTHY" : "ALERT"
        };
        showToast("Daily financials calculated (Local Session)!", "info");
      }

      this.render();
      form.reset();
      // Reset default date to today
      const dateEl = document.getElementById("entry-date");
      if (dateEl) dateEl.value = new Date().toISOString().split("T")[0];

    } catch (err) {
      showToast(`Error saving financials: ${err.message}`, "error");
    } finally {
      if (btn) btn.disabled = false;
    }
  }
};

