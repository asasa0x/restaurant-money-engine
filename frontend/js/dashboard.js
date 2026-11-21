/**
 * Restaurant Money Engine - Dashboard & Prime Cost Health
 */

import { api, EMPTY_STATE, showToast, formatCurrency } from "./api.js";

export const dashboard = {
  state: {
    financials: { ...EMPTY_STATE.financials },
    history: []
  },

  async init() {
    this.bindEvents();
    await this.loadFinancials();
  },

  reset() {
    this.state.financials = { ...EMPTY_STATE.financials };
    this.state.history = [];
    this.render();
  },

  bindEvents() {
    const dateEl = document.getElementById("entry-date");
    if (dateEl && !dateEl.value) {
      dateEl.value = new Date().toISOString().split("T")[0];
    }
    const form = document.getElementById("daily-financials-form");
    if (form) {
      form.addEventListener("submit", (e) => this.handleLogFinancials(e));
    }
  },

  async loadFinancials() {
    if (!api.isAuthenticated()) {
      this.reset();
      return;
    }

    try {
      const res = await api.get("/api/v1/daily-financials");
      if (res && res.data) {
        this.state.financials = res.data;
        this.state.history = Array.isArray(res.history) ? res.history : [];
      } else {
        this.state.financials = { ...EMPTY_STATE.financials };
        this.state.history = [];
      }
    } catch (err) {
      this.state.financials = { ...EMPTY_STATE.financials };
      this.state.history = [];
      if (err.status !== 401) {
        showToast(`Failed to load daily financials: ${err.message}`, "error");
      }
    }
    this.render();
  },

  render() {
    const f = this.state.financials;

    // 1. KPI cards & currency labels
    const isPkr = (api.getRestaurant()?.currency || "USD").toUpperCase() === "PKR";
    const sym = isPkr ? "Rs." : "$";
    const salesLbl = document.querySelector('label[for="entry-sales"]');
    const cogsLbl = document.querySelector('label[for="entry-cogs"]');
    const laborLbl = document.querySelector('label[for="entry-labor"]');
    if (salesLbl) salesLbl.textContent = `Gross Sales (${sym})`;
    if (cogsLbl) cogsLbl.textContent = `Food & Beverage Cost (COGS) (${sym})`;
    if (laborLbl) laborLbl.textContent = `Total Labor Cost (${sym})`;

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
    // Honor the server-computed status (zero-sales days must never display as HEALTHY)
    const status = f.status || (f.gross_sales > 0 && primePct <= targetPct ? "HEALTHY" : "ALERT");
    const isHealthy = status === "HEALTHY";

    if (pctEl) {
      pctEl.textContent = `${primePct.toFixed(1)}%`;
    }

    if (statusBadge) {
      statusBadge.textContent = status.replace("_", " ");
      statusBadge.className = `status-pill ${isHealthy ? "status-healthy" : "status-alert"}`;
    }

    // 3. Visual Gauge Bar (0% to 100%, with benchmark pin at 60%)
    if (gaugeFill) {
      gaugeFill.style.width = `${Math.min(100, Math.max(0, primePct))}%`;
      gaugeFill.className = `gauge-fill ${isHealthy ? "gauge-healthy" : "gauge-alert"}`;
    }

    if (gaugePointer) {
      gaugePointer.style.left = `${Math.min(100, Math.max(0, primePct))}%`;
    }

    // Subtext summaries
    const cogsPctEl = document.getElementById("cogs-pct-sub");
    const laborPctEl = document.getElementById("labor-pct-sub");
    if (cogsPctEl) {
      cogsPctEl.textContent = f.gross_sales > 0
        ? `${((f.cogs / f.gross_sales) * 100).toFixed(1)}% of sales`
        : "0% of gross sales";
    }
    if (laborPctEl) {
      laborPctEl.textContent = f.gross_sales > 0
        ? `${((f.labor_cost / f.gross_sales) * 100).toFixed(1)}% of sales`
        : "0% of gross sales";
    }

    // 4. Render Gross Sales Trend Chart
    this.renderSalesChart(this.state.history);
  },

  renderSalesChart(history) {
    const container = document.getElementById("sales-chart-container");
    const totalEl = document.getElementById("chart-total-7d");
    const avgEl = document.getElementById("chart-7d-avg");
    if (!container) return;

    if (!Array.isArray(history) || history.length === 0) {
      if (totalEl) totalEl.style.display = "none";
      if (avgEl) avgEl.style.display = "none";
      container.innerHTML = `
        <div class="chart-empty-state">
          <div class="chart-empty-icon">📊</div>
          <div class="chart-empty-title">No Daily Sales History Yet</div>
          <div class="chart-empty-desc">
            Log your daily financial reconciliation below to start visualizing your 7-day Gross Sales revenue and cost trends.
          </div>
        </div>
      `;
      return;
    }

    // Sort ascending by date for chronological trend
    const data = [...history].sort((a, b) => new Date(a.date) - new Date(b.date));

    // Summary calculations
    const totalSales = data.reduce((sum, r) => sum + (Number(r.gross_sales) || 0), 0);
    const avgSales = data.length > 0 ? (totalSales / data.length) : 0;

    if (totalEl) {
      totalEl.textContent = `7-Day Total: ${formatCurrency(totalSales)}`;
      totalEl.style.display = "inline-flex";
    }
    if (avgEl) {
      avgEl.textContent = `Avg: ${formatCurrency(avgSales)}/day`;
      avgEl.style.display = "inline-flex";
    }

    // Chart dimensions
    const svgW = 760;
    const svgH = 260;
    const pad = { top: 35, right: 35, bottom: 45, left: 75 };
    const plotW = svgW - pad.left - pad.right;
    const plotH = svgH - pad.top - pad.bottom;

    const rawMax = Math.max(...data.map(d => Number(d.gross_sales) || 0), 100);
    const maxSales = Math.ceil(rawMax * 1.15);

    // Format compact scale value
    const formatScale = (val) => {
      if (val === 0) return "0";
      const isPkr = (api.getRestaurant()?.currency || "USD").toUpperCase() === "PKR";
      const sym = isPkr ? "Rs." : "$";
      if (val >= 1000000) return `${sym}${(val / 1000000).toFixed(1)}M`;
      if (val >= 1000) return `${sym}${(val / 1000).toFixed(val % 1000 === 0 ? 0 : 1)}k`;
      return `${sym}${Math.round(val)}`;
    };

    // Generate horizontal grid lines
    const gridTicks = [0, 0.33, 0.66, 1.0];
    let gridLinesSvg = "";
    gridTicks.forEach(tick => {
      const y = pad.top + plotH - (tick * plotH);
      const val = tick * maxSales;
      gridLinesSvg += `
        <line x1="${pad.left}" y1="${y}" x2="${svgW - pad.right}" y2="${y}" class="chart-grid-line" />
        <text x="${pad.left - 10}" y="${y + 4}" text-anchor="end" class="chart-axis-text">${formatScale(val)}</text>
      `;
    });

    const n = data.length;
    const barW = n > 1 ? Math.min(46, Math.max(22, (plotW / n) * 0.52)) : 48;

    // Calculate points and bar positions
    const points = data.map((item, i) => {
      const sales = Number(item.gross_sales) || 0;
      const x = n === 1 ? pad.left + plotW / 2 : pad.left + (i / (n - 1)) * plotW;
      const barH = (sales / maxSales) * plotH;
      const y = pad.top + plotH - barH;

      // Format date label
      let dateLabel = item.date;
      let dayLabel = "";
      try {
        const d = new Date(item.date + "T00:00:00");
        dateLabel = d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
        dayLabel = d.toLocaleDateString("en-US", { weekday: "short" });
      } catch (_) {}

      return {
        x,
        y,
        barX: x - barW / 2,
        barH,
        sales,
        cogs: Number(item.cogs) || 0,
        labor: Number(item.labor_cost) || 0,
        date: item.date,
        dateLabel,
        dayLabel
      };
    });

    // Area & Line paths
    let areaPath = "";
    let linePath = "";
    if (points.length > 1) {
      linePath = `M ${points[0].x} ${points[0].y}`;
      for (let i = 1; i < points.length; i++) {
        // Smooth cubic bezier curve
        const prev = points[i - 1];
        const curr = points[i];
        const cpX = (prev.x + curr.x) / 2;
        linePath += ` C ${cpX} ${prev.y}, ${cpX} ${curr.y}, ${curr.x} ${curr.y}`;
      }
      areaPath = `${linePath} L ${points[points.length - 1].x} ${pad.top + plotH} L ${points[0].x} ${pad.top + plotH} Z`;
    }

    // Build bars and interactive point groups
    let barsSvg = "";
    let pointsSvg = "";
    let labelsSvg = "";

    points.forEach((p, idx) => {
      // Bar
      barsSvg += `
        <rect class="chart-bar" x="${p.barX}" y="${p.y}" width="${barW}" height="${p.barH}" rx="5" ry="5" data-index="${idx}" />
      `;

      // Value label on top of point
      const formattedShort = formatScale(p.sales);
      labelsSvg += `
        <text x="${p.x}" y="${Math.max(16, p.y - 12)}" class="chart-val-label">${formattedShort}</text>
        <text x="${p.x}" y="${pad.top + plotH + 18}" text-anchor="middle" class="chart-axis-text" style="font-weight: 700;">${p.dateLabel}</text>
        <text x="${p.x}" y="${pad.top + plotH + 32}" text-anchor="middle" class="chart-axis-text" style="fill: var(--text-dim);">${p.dayLabel}</text>
      `;

      // Point circle
      pointsSvg += `
        <circle class="chart-point" cx="${p.x}" cy="${p.y}" data-index="${idx}" />
      `;
    });

    container.innerHTML = `
      <svg class="chart-svg" viewBox="0 0 ${svgW} ${svgH}" preserveAspectRatio="xMidYMid meet">
        <defs>
          <linearGradient id="salesGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="#D3131A" stop-opacity="0.32" />
            <stop offset="100%" stop-color="#D3131A" stop-opacity="0.02" />
          </linearGradient>
        </defs>

        <!-- Grid Lines -->
        ${gridLinesSvg}

        <!-- Gradient Area Fill -->
        ${areaPath ? `<path d="${areaPath}" class="chart-trend-area" />` : ""}

        <!-- Daily Bars -->
        ${barsSvg}

        <!-- Trend Line -->
        ${linePath ? `<path d="${linePath}" class="chart-trend-line" />` : ""}

        <!-- Data Point Nodes -->
        ${pointsSvg}

        <!-- Labels -->
        ${labelsSvg}
      </svg>
      <div id="sales-chart-tooltip" class="chart-tooltip-box"></div>
    `;

    // Interactive Tooltip binding
    const tooltip = document.getElementById("sales-chart-tooltip");
    const svgEl = container.querySelector(".chart-svg");
    if (!tooltip || !svgEl) return;

    const showTooltipForIndex = (index, targetEl) => {
      const p = points[index];
      if (!p) return;

      const primeTotal = p.cogs + p.labor;
      const primePct = p.sales > 0 ? ((primeTotal / p.sales) * 100).toFixed(1) : "0.0";
      const cogsPct = p.sales > 0 ? ((p.cogs / p.sales) * 100).toFixed(1) : "0.0";
      const laborPct = p.sales > 0 ? ((p.labor / p.sales) * 100).toFixed(1) : "0.0";

      tooltip.innerHTML = `
        <div style="font-weight: 700; margin-bottom: 4px; color: var(--brand-gold); font-size: 0.85rem;">
          📅 ${p.dateLabel} (${p.dayLabel || "Record"})
        </div>
        <div style="margin-bottom: 3px;">💰 <strong>Gross Sales:</strong> ${formatCurrency(p.sales)}</div>
        <div style="margin-bottom: 2px; color: #E8DFD1;">🥩 Food (COGS): ${formatCurrency(p.cogs)} <span style="opacity: 0.8;">(${cogsPct}%)</span></div>
        <div style="margin-bottom: 2px; color: #E8DFD1;">👨‍🍳 Labor: ${formatCurrency(p.labor)} <span style="opacity: 0.8;">(${laborPct}%)</span></div>
        <div style="border-top: 1px solid rgba(255,255,255,0.15); margin-top: 4px; padding-top: 4px; font-weight: 600;">
          ⚡ Prime Cost: ${formatCurrency(primeTotal)} <span class="status-pill ${Number(primePct) <= 60 ? "status-healthy" : "status-alert"}" style="padding: 1px 6px; font-size: 0.72rem; margin-left: 4px;">${primePct}%</span>
        </div>
      `;

      // Position tooltip relative to container
      const rect = container.getBoundingClientRect();
      const targetRect = targetEl.getBoundingClientRect();
      const posX = targetRect.left - rect.left + targetRect.width / 2;
      const posY = targetRect.top - rect.top;

      tooltip.style.left = `${posX}px`;
      tooltip.style.top = `${posY}px`;
      tooltip.style.display = "block";
      tooltip.style.opacity = "1";
    };

    const hideTooltip = () => {
      tooltip.style.display = "none";
      tooltip.style.opacity = "0";
    };

    container.querySelectorAll(".chart-bar, .chart-point").forEach(el => {
      el.addEventListener("mouseenter", (e) => {
        const idx = parseInt(e.target.getAttribute("data-index"), 10);
        showTooltipForIndex(idx, e.target);
      });
      el.addEventListener("mouseleave", hideTooltip);
      el.addEventListener("touchstart", (e) => {
        const idx = parseInt(e.target.getAttribute("data-index"), 10);
        showTooltipForIndex(idx, e.target);
      }, { passive: true });
    });
  },

  async handleLogFinancials(e) {
    e.preventDefault();
    if (!api.isAuthenticated()) {
      showToast("Please sign in to record daily financials.", "error");
      return;
    }

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
      if (res && res.metrics) {
        showToast("Daily financials recorded in Supabase database!", "success");
      }

      // Reload financials so that the 7-day trend chart and metrics refresh immediately
      await this.loadFinancials();

      form.reset();
      const dateEl = document.getElementById("entry-date");
      if (dateEl) dateEl.value = new Date().toISOString().split("T")[0];
    } catch (err) {
      showToast(`Error saving financials: ${err.message}`, "error");
    } finally {
      if (btn) btn.disabled = false;
    }
  }
};
