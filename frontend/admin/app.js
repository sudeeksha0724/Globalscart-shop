const API_BASE = "";
const API_ADMIN = "/api/admin";

let _adminKeyMem = "";

function getAdminKey() {
  try {
    return localStorage.getItem("globalcart_admin_key") || "";
  } catch {
    return _adminKeyMem;
  }
}

function saveAdminKey(k) {
  const key = String(k || "").trim();
  _adminKeyMem = key;
  try {
    if (!key) {
      localStorage.removeItem("globalcart_admin_key");
      return;
    }
    localStorage.setItem("globalcart_admin_key", key);
  } catch {}
}

function showBrandIntro() {
  let force = false;
  try {
    const q = new URL(window.location.href).searchParams;
    force = q.get('intro') === '1';
  } catch {
  }

  try {
    if (!force && sessionStorage.getItem("gc_brand_intro_admin") === "1") return;
    sessionStorage.setItem("gc_brand_intro_admin", "1");
  } catch {
  }

  const overlay = document.createElement("div");
  overlay.className = "gc-brand-intro";
  overlay.innerHTML = '<div class="gc-brand-word">G<span class="gc-brand-expand">lobal</span>SCART</div>';
  overlay.addEventListener("animationend", (e) => {
    if (e && e.animationName === "gc-brand-out") {
      overlay.remove();
    }
  });
  document.body.appendChild(overlay);
}

function isAdmin() {
  return Boolean(getAdminKey());
}

async function apiGet(path, opts) {
  let res;
  try {
    const headers = Object.assign({}, (opts && opts.headers) || {});
    const adminKey = getAdminKey();
    if (adminKey) headers["X-Admin-Key"] = adminKey;
    res = await fetch(`${API_BASE}${path}`, { headers });
  } catch {
    throw new Error("Backend not reachable. Start server with: make dev");
  }
  if (!res.ok) {
    let msg = "";
    try {
      const txt = await res.text();
      try {
        const j = JSON.parse(txt);
        msg = j && j.detail ? String(j.detail) : JSON.stringify(j);
      } catch {
        msg = txt;
      }
    } catch {
      msg = `Request failed: ${res.status}`;
    }
    throw new Error(msg || `Request failed: ${res.status}`);
  }
  return res.json();
}

async function apiGetPng(path, opts) {
  let res;
  try {
    const headers = Object.assign({}, (opts && opts.headers) || {});
    const adminKey = getAdminKey();
    if (adminKey) headers["X-Admin-Key"] = adminKey;
    res = await fetch(`${API_BASE}${path}`, { headers, cache: "no-store" });
  } catch {
    throw new Error("Backend not reachable. Start server with: make dev");
  }
  if (!res.ok) {
    let msg = "";
    try {
      const txt = await res.text();
      // Try to parse as JSON for nicer error messages
      try {
        const j = JSON.parse(txt);
        msg = j && j.detail ? String(j.detail) : JSON.stringify(j);
      } catch {
        msg = txt;
      }
    } catch {
      msg = `Request failed: ${res.status}`;
    }
    throw new Error(msg);
  }
  return true;
}

async function apiPost(path, body, opts) {
  let res;
  try {
    const headers = Object.assign({ "Content-Type": "application/json" }, (opts && opts.headers) || {});
    const adminKey = getAdminKey();
    if (adminKey) headers["X-Admin-Key"] = adminKey;
    res = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers,
      body: JSON.stringify(body || {}),
    });
  } catch {
    throw new Error("Backend not reachable. Start server with: make dev");
  }

  if (!res.ok) {
    let msg = "";
    try {
      const txt = await res.text();
      try {
        const j = JSON.parse(txt);
        msg = j && j.detail ? String(j.detail) : JSON.stringify(j);
      } catch {
        msg = txt;
      }
    } catch {
      msg = `Request failed: ${res.status}`;
    }
    throw new Error(msg || `Request failed: ${res.status}`);
  }
  return res.json();
}

function showToast(message) {
  const el = document.getElementById("toast");
  if (!el) return;
  el.querySelector(".toast-body").textContent = message;
  const toast = bootstrap.Toast.getOrCreateInstance(el);
  toast.show();
}

function fmtCompactNumber(n) {
  const x = Number(n || 0);
  try {
    return new Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 1 }).format(x);
  } catch {
    return String(x.toFixed(0));
  }
}

function fmtMoney(n) {
  const x = Number(n || 0);
  try {
    return new Intl.NumberFormat(undefined, {
      style: "currency",
      currency: "INR",
      maximumFractionDigits: 2,
    }).format(x);
  } catch {
    return `₹${x.toFixed(2)}`;
  }
}

function fmtPct(n) {
  return `${(Number(n || 0) * 100).toFixed(2)}%`;
}

function renderKpiCards(kpis) {
  const cardsEl = document.getElementById("kpiCards");
  if (!cardsEl) return;
  if (!kpis || !kpis.metrics) {
    cardsEl.innerHTML = "";
    return;
  }

  const m = kpis.metrics;
  const net = Number(m.net_revenue_total || 0);
  const orders = Number(m.orders_total || 0);
  const aov = orders > 0 ? net / orders : 0;

  const items = [
    {
      label: "Net revenue",
      value: fmtMoney(net),
      meta: `Refunds: ${fmtMoney(m.refund_amount_total || 0)}`,
    },
    {
      label: "Orders",
      value: fmtCompactNumber(orders),
      meta: `Shipping: ${fmtMoney(m.shipping_cost_total || 0)}`,
    },
    {
      label: "AOV",
      value: fmtMoney(aov),
      meta: "Avg order value",
    },
    {
      label: "Conversion",
      value: fmtPct(m.conversion_rate || 0),
      meta: `Abandon: ${fmtPct(m.cart_abandonment_rate || 0)}`,
    },
  ];

  cardsEl.innerHTML = items
    .map(
      (c) => `
        <div class="col">
          <div class="card gc-kpi-card h-100">
            <div class="card-body">
              <div class="gc-kpi-card-label">${c.label}</div>
              <div class="gc-kpi-card-value">${c.value}</div>
              <div class="gc-kpi-card-meta">${c.meta}</div>
            </div>
          </div>
        </div>
      `
    )
    .join("");
}

function kpiHtml(kpis) {
  if (!kpis || !kpis.metrics) return "(no KPI data)";
  const m = kpis.metrics;
  const money = (x) => `₹${Number(x || 0).toFixed(2)}`;
  const num = (x) => `${Number(x || 0).toFixed(0)}`;
  const pct = (x) => `${(Number(x || 0) * 100).toFixed(2)}%`;
  return `
    <div class="gc-kpi">
      <div class="gc-kpi-main">
        <div class="gc-kpi-label">Net revenue</div>
        <div class="gc-kpi-value">${money(m.net_revenue_total)}</div>
      </div>
      <div class="gc-kpi-row"><span class="gc-kpi-label">Orders</span><span class="gc-kpi-value">${num(m.orders_total)}</span></div>
      <div class="gc-kpi-row"><span class="gc-kpi-label">Refunds</span><span class="gc-kpi-value">${money(m.refund_amount_total)}</span></div>
      <div class="gc-kpi-row"><span class="gc-kpi-label">Shipping</span><span class="gc-kpi-value">${money(m.shipping_cost_total)}</span></div>
      <div class="gc-kpi-row"><span class="gc-kpi-label">Conversion rate</span><span class="gc-kpi-value">${pct(m.conversion_rate)}</span></div>
      <div class="gc-kpi-row"><span class="gc-kpi-label">Cart abandonment</span><span class="gc-kpi-value">${pct(m.cart_abandonment_rate)}</span></div>
      <div class="gc-kpi-row"><span class="gc-kpi-label">Payment failure</span><span class="gc-kpi-value">${pct(m.payment_failure_rate)}</span></div>
      <div class="gc-kpi-row"><span class="gc-kpi-label">Rev lost (abandon)</span><span class="gc-kpi-value">${money(m.revenue_lost_due_to_abandonment)}</span></div>
      <div class="gc-kpi-row"><span class="gc-kpi-label">Rev lost (failures)</span><span class="gc-kpi-value">${money(m.revenue_lost_due_to_failures)}</span></div>
    </div>
  `;
}

function funnelSummaryHtml(s) {
  if (!s) return "(no funnel data)";
  const money = (x) => `₹${Number(x || 0).toFixed(2)}`;
  const pct = (x) => `${(Number(x || 0) * 100).toFixed(2)}%`;
  const num = (x) => `${Number(x || 0).toFixed(0)}`;

  const base = Number(s.product_views || 0);
  const bar = (label, v) => {
    const val = Number(v || 0);
    const p = base > 0 ? Math.max(0, Math.min(100, (val / base) * 100)) : 0;
    return `
      <div class="mb-2">
        <div class="d-flex justify-content-between"><span>${label}</span><strong>${num(val)}</strong></div>
        <div class="progress" style="height: 8px;">
          <div class="progress-bar" role="progressbar" style="width: ${p.toFixed(1)}%"></div>
        </div>
      </div>
    `;
  };

  return `
    <div class="text-muted small mb-2">Window: last ${num(s.window_days)} days</div>
    ${bar("Product views (sessions)", s.product_views)}
    ${bar("Add to cart (sessions)", s.add_to_cart)}
    ${bar("Checkout started (sessions)", s.checkout_started)}
    ${bar("Payment attempts (sessions)", s.payment_attempts)}
    ${bar("Orders placed (sessions)", s.orders_placed)}
    <div class="mt-3">
      <div class="d-flex justify-content-between"><span>Conversion rate</span><strong>${pct(s.conversion_rate)}</strong></div>
      <div class="d-flex justify-content-between"><span>Cart abandonment rate</span><strong>${pct(s.cart_abandonment_rate)}</strong></div>
      <div class="d-flex justify-content-between"><span>Payment failure rate</span><strong>${pct(s.payment_failure_rate)}</strong></div>
    </div>
    <hr />
    <div class="d-flex justify-content-between"><span>Net revenue (ex tax)</span><strong>${money(s.net_revenue_ex_tax)}</strong></div>
    <div class="d-flex justify-content-between"><span>Revenue lost (cart abandonment)</span><strong>${money(s.revenue_lost_cart_abandonment)}</strong></div>
    <div class="d-flex justify-content-between"><span>Revenue lost (payment failures)</span><strong>${money(s.revenue_lost_payment_failures)}</strong></div>
    <div class="d-flex justify-content-between"><span>Refund leakage</span><strong>${money(s.refunds_leakage)}</strong></div>
    <div class="d-flex justify-content-between"><span>Net revenue after leakage</span><strong>${money(s.net_revenue_after_leakage)}</strong></div>
  `;
}

async function refreshFunnel() {
  const statusEl = document.getElementById("funnelStatus");
  const panel = document.getElementById("funnelSummaryPanel");
  const prodTbody = document.getElementById("productLeakageTbody");
  const failTbody = document.getElementById("paymentFailuresTbody");
  if (statusEl) statusEl.textContent = "";
  if (panel) panel.textContent = "Loading funnel...";
  if (prodTbody) prodTbody.innerHTML = "<tr><td colspan='6' class='text-muted'>Loading...</td></tr>";
  if (failTbody) failTbody.innerHTML = "<tr><td colspan='6' class='text-muted'>Loading...</td></tr>";

  try {
    const [summary, products, failures] = await Promise.all([
      apiGet(`${API_ADMIN}/funnel/summary?window_days=30`),
      apiGet(`${API_ADMIN}/funnel/product-leakage?limit=10&offset=0`),
      apiGet(`${API_ADMIN}/funnel/payment-failures?window_days=30&limit=10&offset=0`),
    ]);

    if (panel) panel.innerHTML = funnelSummaryHtml(summary);

    if (prodTbody) {
      if (!products || !products.length) {
        prodTbody.innerHTML = "<tr><td colspan='6' class='text-muted'>No leakage data</td></tr>";
      } else {
        prodTbody.innerHTML = products
          .map(
            (p) => `
              <tr>
                <td>${p.product_name}</td>
                <td class="text-end">${Number(p.product_views || 0).toFixed(0)}</td>
                <td class="text-end">${Number(p.add_to_cart || 0).toFixed(0)}</td>
                <td class="text-end">${Number(p.abandoned_adds || 0).toFixed(0)}</td>
                <td class="text-end">₹${Number(p.revenue_lost_cart_abandonment || 0).toFixed(2)}</td>
                <td class="text-end">₹${Number(p.revenue_lost_payment_failures || 0).toFixed(2)}</td>
              </tr>
            `
          )
          .join("");
      }
    }

    if (failTbody) {
      if (!failures || !failures.length) {
        failTbody.innerHTML = "<tr><td colspan='6' class='text-muted'>No failures in window</td></tr>";
      } else {
        failTbody.innerHTML = failures
          .map(
            (f) => `
              <tr>
                <td>${f.event_dt}</td>
                <td>${f.payment_method}</td>
                <td>${f.payment_provider}</td>
                <td>${f.failure_reason || ""}</td>
                <td class="text-end">${Number(f.failed_payments || 0).toFixed(0)}</td>
                <td class="text-end">₹${Number(f.amount_attempted || 0).toFixed(2)}</td>
              </tr>
            `
          )
          .join("");
      }
    }

    if (statusEl) statusEl.textContent = "";
  } catch (e) {
    if (panel) panel.textContent = e.message || String(e);
    if (statusEl) statusEl.textContent = e.message || String(e);
    if (prodTbody) prodTbody.innerHTML = `<tr><td colspan='6' class='text-danger'>${e.message || String(e)}</td></tr>`;
    if (failTbody) failTbody.innerHTML = `<tr><td colspan='6' class='text-danger'>${e.message || String(e)}</td></tr>`;
  }
}

function requireAdminUi() {
  const loginCard = document.getElementById("adminLoginCard");
  const content = document.getElementById("adminContent");
  if (!isAdmin()) {
    if (loginCard) loginCard.classList.remove("d-none");
    if (content) content.classList.add("d-none");
    return false;
  }
  if (loginCard) loginCard.classList.add("d-none");
  if (content) content.classList.remove("d-none");
  return true;
}

async function refreshKpis() {
  const panel = document.getElementById("kpiPanel");
  const lastUpdated = document.getElementById("kpiLastUpdated");
  const cardsEl = document.getElementById("kpiCards");
  if (!panel) return;
  panel.textContent = "Loading KPIs...";
  if (cardsEl) cardsEl.innerHTML = "";
  if (lastUpdated) lastUpdated.textContent = "";
  try {
    const kpis = await apiGet(`${API_ADMIN}/kpis/latest`);
    const ts = (kpis && (kpis.kpi_last_updated_at || kpis.snapshot_ts)) || "";
    if (lastUpdated && ts) lastUpdated.textContent = `KPIs last updated at: ${ts}`;
    renderKpiCards(kpis);
    panel.innerHTML = kpiHtml(kpis);
  } catch (e) {
    if (cardsEl) cardsEl.innerHTML = "";
    panel.textContent = e.message || String(e);
  }
}

async function refreshAudit() {
  const tbody = document.getElementById("auditTbody");
  if (!tbody) return;
  tbody.innerHTML = "<tr><td colspan='5' class='text-muted'>Loading...</td></tr>";
  try {
    const rows = await apiGet(`${API_ADMIN}/audit-log?limit=200&offset=0`);
    if (!rows || !rows.length) {
      tbody.innerHTML = "<tr><td colspan='5' class='text-muted'>No events found</td></tr>";
      return;
    }
    tbody.innerHTML = rows
      .map(
        (r) => `
          <tr>
            <td>${r.event_ts}</td>
            <td>${r.order_id}</td>
            <td>${r.action}</td>
            <td>${r.reason || ""}</td>
            <td>${r.actor_type}</td>
          </tr>
        `
      )
      .join("");
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan='5' class='text-danger'>${e.message || String(e)}</td></tr>`;
  }
}

async function refreshOrders() {
  const tbody = document.getElementById("ordersTbody");
  if (!tbody) return;
  tbody.innerHTML = "<tr><td colspan='7' class='text-muted'>Loading...</td></tr>";
  try {
    const rows = await apiGet(`${API_ADMIN}/orders?limit=50&offset=0`);
    if (!rows || !rows.length) {
      tbody.innerHTML = "<tr><td colspan='7' class='text-muted'>No orders found</td></tr>";
      return;
    }
    tbody.innerHTML = rows
      .map(
        (o) => `
          <tr>
            <td>${o.order_id}</td>
            <td>${o.customer_id}</td>
            <td>${escapeHtml(o.customer_email || "")}</td>
            <td>${o.order_ts}</td>
            <td>${o.order_status}</td>
            <td>₹${Number(o.net_amount || 0).toFixed(2)}</td>
            <td>${o.channel || ""}</td>
          </tr>
        `
      )
      .join("");
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan='7' class='text-danger'>${escapeHtml(e.message || String(e))}</td></tr>`;
  }
}

async function initAdmin() {
  const userEl = document.getElementById("adminUser");
  const passEl = document.getElementById("adminPass");
  const loginBtn = document.getElementById("adminLoginBtn");
  const statusEl = document.getElementById("adminLoginStatus");
  const logoutBtn = document.getElementById("adminLogoutBtn");

  const refreshOrdersBtn = document.getElementById("refreshOrdersBtn");
  const refreshFunnelBtn = document.getElementById("refreshFunnelBtn");

  requireAdminUi();

  if (isAdmin()) {
    await refreshKpis();
    await refreshFunnel();
    await refreshOrders();
  }

  if (loginBtn) {
    loginBtn.addEventListener("click", async () => {
      const username = String((userEl && userEl.value) || "").trim();
      const password = String((passEl && passEl.value) || "").trim();
      if (!username || !password) {
        if (statusEl) statusEl.textContent = "Enter Admin ID and password";
        return;
      }
      if (statusEl) statusEl.textContent = "Logging in...";
      try {
        const res = await apiPost(`${API_ADMIN}/login`, { username, password });
        saveAdminKey(res.admin_key);
        requireAdminUi();
        if (statusEl) statusEl.textContent = "";
        await refreshKpis();
        await refreshFunnel();
        await refreshOrders();
        showToast("Admin login success");
      } catch (e) {
        if (statusEl) statusEl.textContent = e.message || String(e);
      }
    });
  }

  if (logoutBtn) {
    logoutBtn.addEventListener("click", () => {
      saveAdminKey("");
      requireAdminUi();
      if (statusEl) statusEl.textContent = "Logged out";
      showToast("Logged out");
    });
  }

  if (refreshOrdersBtn) refreshOrdersBtn.addEventListener("click", refreshOrders);
  if (refreshFunnelBtn) refreshFunnelBtn.addEventListener("click", refreshFunnel);
}

async function initAudit() {
  const userEl = document.getElementById("adminUser");
  const passEl = document.getElementById("adminPass");
  const loginBtn = document.getElementById("adminLoginBtn");
  const statusEl = document.getElementById("adminLoginStatus");
  const logoutBtn = document.getElementById("adminLogoutBtn");
  const refreshAuditBtn = document.getElementById("refreshAuditBtn");

  requireAdminUi();

  if (isAdmin()) {
    await refreshAudit();
  }

  if (loginBtn) {
    loginBtn.addEventListener("click", async () => {
      const username = String((userEl && userEl.value) || "").trim();
      const password = String((passEl && passEl.value) || "").trim();
      if (!username || !password) {
        if (statusEl) statusEl.textContent = "Enter Admin ID and password";
        return;
      }
      if (statusEl) statusEl.textContent = "Logging in...";
      try {
        const res = await apiPost(`${API_ADMIN}/login`, { username, password });
        saveAdminKey(res.admin_key);
        requireAdminUi();
        if (statusEl) statusEl.textContent = "";
        await refreshAudit();
        showToast("Admin login success");
      } catch (e) {
        if (statusEl) statusEl.textContent = e.message || String(e);
      }
    });
  }

  if (logoutBtn) {
    logoutBtn.addEventListener("click", () => {
      saveAdminKey("");
      requireAdminUi();
      if (statusEl) statusEl.textContent = "Logged out";
      showToast("Logged out");
    });
  }

  if (refreshAuditBtn) refreshAuditBtn.addEventListener("click", refreshAudit);
}

async function refreshAnalyticsCharts() {
  const statusEl = document.getElementById("analyticsStatus");
  if (statusEl) statusEl.textContent = "Generating charts...";

  const intVal = (id, fallback) => {
    const el = document.getElementById(id);
    const v = el ? parseInt(String(el.value || ""), 10) : NaN;
    return Number.isFinite(v) ? v : fallback;
  };
  const strVal = (id, fallback) => {
    const el = document.getElementById(id);
    const v = el ? String(el.value || "").trim() : "";
    return v || fallback;
  };

  const trendDays = intVal("trendWindowDays", 90);
  const perfDays = intVal("perfWindowDays", 30);
  const topN = intVal("topN", 10);
  const categoryLevel = encodeURIComponent(strVal("categoryLevel", "category_l1"));

  const endpoints = [
    ["sales_trend", `${API_ADMIN}/analytics/sales_trend?window_days=${trendDays}`],
    ["orders_vs_revenue", `${API_ADMIN}/analytics/orders_vs_revenue?window_days=${trendDays}`],
    ["funnel_conversion", `${API_ADMIN}/analytics/funnel_conversion?window_days=${perfDays}`],
    ["top_products", `${API_ADMIN}/analytics/top_products?window_days=${perfDays}&top_n=${topN}`],
    ["category_contribution", `${API_ADMIN}/analytics/category_contribution?window_days=${perfDays}&level=${categoryLevel}&top_n=${topN}`],
    ["refund_leakage", `${API_ADMIN}/analytics/refund_leakage?window_days=${trendDays}`],
  ];

  const results = await Promise.allSettled(
    endpoints.map(([name, url]) =>
      apiGetPng(url).then(
        () => ({ name, ok: true }),
        (e) => {
          console.error(`Error generating ${name}:`, e);
          return { name, ok: false, error: e.message || String(e) };
        }
      )
    )
  );

  const failed = results.filter((r) => r.value && !r.value.ok);
  const updatedEl = document.getElementById("analyticsLastUpdated");
  if (failed.length && statusEl) {
    const categoryError = failed.find(f => f.value.name === "category_contribution");
    if (categoryError) {
      statusEl.textContent = `Category Contribution failed: ${categoryError.value.error}`;
    } else {
      statusEl.textContent = `Some charts failed: ${failed.map((f) => f.value.name).join(", ")}`;
    }
    if (updatedEl) updatedEl.textContent = `Partial update • ${new Date().toLocaleString()}`;
  } else if (statusEl) {
    statusEl.textContent = "Charts updated.";
    if (updatedEl) updatedEl.textContent = `Updated • ${new Date().toLocaleString()}`;
  }

  const bust = `t=${Date.now()}`;
  const setImg = (id, src) => {
    const el = document.getElementById(id);
    if (el) el.src = `${src}?${bust}`;
  };

  setImg("imgSalesTrend", "/static/analytics/sales_trend.png");
  setImg("imgOrdersVsRevenue", "/static/analytics/orders_vs_revenue.png");
  setImg("imgFunnelConversion", "/static/analytics/funnel_conversion.png");
  setImg("imgTopProducts", "/static/analytics/top_products.png");
  setImg("imgCategoryContribution", "/static/analytics/category_contribution.png");
  setImg("imgRefundLeakage", "/static/analytics/refund_leakage.png");
}

async function initAnalytics() {
  const userEl = document.getElementById("adminUser");
  const passEl = document.getElementById("adminPass");
  const loginBtn = document.getElementById("adminLoginBtn");
  const statusEl = document.getElementById("adminLoginStatus");
  const logoutBtn = document.getElementById("adminLogoutBtn");
  const refreshChartsBtn = document.getElementById("refreshChartsBtn");

  requireAdminUi();

  if (isAdmin()) {
    await refreshAnalyticsCharts();
  }

  if (loginBtn) {
    loginBtn.addEventListener("click", async () => {
      const username = String((userEl && userEl.value) || "").trim();
      const password = String((passEl && passEl.value) || "").trim();
      if (!username || !password) {
        if (statusEl) statusEl.textContent = "Enter Admin ID and password";
        return;
      }
      if (statusEl) statusEl.textContent = "Logging in...";
      try {
        const res = await apiPost(`${API_ADMIN}/login`, { username, password });
        saveAdminKey(res.admin_key);
        requireAdminUi();
        if (statusEl) statusEl.textContent = "";
        await refreshAnalyticsCharts();
        showToast("Admin login success");
      } catch (e) {
        if (statusEl) statusEl.textContent = e.message || String(e);
      }
    });
  }

  if (logoutBtn) {
    logoutBtn.addEventListener("click", () => {
      saveAdminKey("");
      requireAdminUi();
      if (statusEl) statusEl.textContent = "Logged out";
      showToast("Logged out");
    });
  }

  if (refreshChartsBtn) {
    refreshChartsBtn.addEventListener("click", async () => {
      try {
        refreshChartsBtn.disabled = true;
        await refreshAnalyticsCharts();
      } catch (e) {
        const el = document.getElementById("analyticsStatus");
        if (el) el.textContent = e.message || String(e);
      } finally {
        refreshChartsBtn.disabled = false;
      }
    });
  }
}

function escapeHtml(s) {
  const v = String(s == null ? "" : s);
  return v
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function stageBadge(stage) {
  const s = String(stage || "").toUpperCase();
  const map = {
    VIEW_PRODUCT: "text-bg-secondary",
    ADD_TO_CART: "text-bg-info",
    VIEW_CART: "text-bg-info",
    CHECKOUT_STARTED: "text-bg-warning",
    PAYMENT_ATTEMPTED: "text-bg-warning",
    PAYMENT_FAILED: "text-bg-danger",
    ORDER_PLACED: "text-bg-success",
  };
  const cls = map[s] || "text-bg-light";
  return `<span class="badge ${cls} border">${escapeHtml(s || stage || "")}</span>`;
}

async function openJourneyProduct(productId) {
  const pid = Number(productId);
  if (!Number.isFinite(pid) || pid <= 0) return;
  const modalEl = document.getElementById("journeyProductModal");
  if (!modalEl) return;

  const statusEl = document.getElementById("journeyProductStatus");
  const imgEl = document.getElementById("journeyProductImg");
  const nameEl = document.getElementById("journeyProductName");
  const metaEl = document.getElementById("journeyProductMeta");
  const sellEl = document.getElementById("journeyProductSell");
  const listEl = document.getElementById("journeyProductList");
  const discEl = document.getElementById("journeyProductDisc");
  const descEl = document.getElementById("journeyProductDesc");
  const stockEl = document.getElementById("journeyProductStock");

  if (statusEl) statusEl.textContent = "Loading product...";
  if (imgEl) imgEl.src = "";
  if (nameEl) nameEl.textContent = "";
  if (metaEl) metaEl.textContent = "";
  if (sellEl) sellEl.textContent = "";
  if (listEl) listEl.textContent = "";
  if (discEl) discEl.textContent = "";
  if (descEl) descEl.textContent = "";
  if (stockEl) stockEl.textContent = "";

  const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
  modal.show();

  try {
    const p = await apiGet(`${API_ADMIN}/products/${encodeURIComponent(pid)}`);
    if (statusEl) statusEl.textContent = "";
    if (imgEl) {
      imgEl.decoding = "async";
      imgEl.src = p.image_url || "";
      imgEl.alt = p.product_name || "Product";
    }
    if (nameEl) nameEl.textContent = p.product_name || `Product ${pid}`;
    if (metaEl) metaEl.textContent = `${p.brand || ""}${p.category_l1 ? " • " + p.category_l1 : ""}${p.category_l2 ? " / " + p.category_l2 : ""}`;
    if (sellEl) sellEl.textContent = fmtMoney(p.sell_price);
    if (listEl) listEl.textContent = fmtMoney(p.list_price);
    if (discEl) discEl.textContent = `${Number(p.discount_pct || 0).toFixed(0)}% OFF`;
    if (descEl) descEl.textContent = p.description || "";
    if (stockEl) stockEl.textContent = p.in_stock ? `In stock • Qty ${Number(p.stock_qty || 0).toFixed(0)}` : "Out of stock";
  } catch (e) {
    if (statusEl) statusEl.textContent = e.message || String(e);
  }
}

async function refreshJourneySessions() {
  const statusEl = document.getElementById("journeyStatus");
  const tbody = document.getElementById("journeySessionsTbody");
  const eventsTbody = document.getElementById("journeyEventsTbody");
  const selectedEl = document.getElementById("journeySelectedSession");
  if (statusEl) statusEl.textContent = "";
  if (tbody) tbody.innerHTML = "<tr><td colspan='6' class='text-muted'>Loading...</td></tr>";
  if (eventsTbody) eventsTbody.innerHTML = "<tr><td colspan='5' class='text-muted'>Select a session</td></tr>";
  if (selectedEl) selectedEl.textContent = "";

  const intVal = (id, fallback) => {
    const el = document.getElementById(id);
    const v = el ? parseInt(String(el.value || ""), 10) : NaN;
    return Number.isFinite(v) ? v : fallback;
  };

  const windowHours = intVal("journeyWindowHours", 72);
  const cust = intVal("journeyCustomerId", NaN);
  const qs = new URLSearchParams();
  qs.set("limit", "100");
  qs.set("offset", "0");
  qs.set("window_hours", String(windowHours));
  if (Number.isFinite(cust) && cust > 0) qs.set("customer_id", String(cust));

  try {
    const rows = await apiGet(`${API_ADMIN}/journey/sessions?${qs.toString()}`);
    if (!tbody) return;
    if (!rows || !rows.length) {
      tbody.innerHTML = "<tr><td colspan='6' class='text-muted'>No sessions found</td></tr>";
      return;
    }
    tbody.innerHTML = rows
      .map(
        (s) => `
          <tr>
            <td>${escapeHtml(s.last_event_ts || "")}</td>
            <td><button class="btn btn-sm btn-outline-secondary" data-journey-session="${escapeHtml(s.session_id)}" type="button">${escapeHtml(s.session_id)}</button></td>
            <td>${escapeHtml(s.customer_id == null ? "" : s.customer_id)}</td>
            <td class="text-end">${Number(s.event_count || 0).toFixed(0)}</td>
            <td>${escapeHtml(s.channel || "")}</td>
            <td>${escapeHtml(s.device || "")}</td>
          </tr>
        `
      )
      .join("");

    tbody.querySelectorAll("[data-journey-session]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const sid = btn.getAttribute("data-journey-session") || "";
        await refreshJourneyEvents(sid);
      });
    });
  } catch (e) {
    if (statusEl) statusEl.textContent = e.message || String(e);
    if (tbody) tbody.innerHTML = `<tr><td colspan='6' class='text-danger'>${escapeHtml(e.message || String(e))}</td></tr>`;
  }
}

async function refreshJourneyEvents(sessionId) {
  const statusEl = document.getElementById("journeyStatus");
  const tbody = document.getElementById("journeyEventsTbody");
  const selectedEl = document.getElementById("journeySelectedSession");
  const sid = String(sessionId || "").trim();
  if (!sid) return;
  if (statusEl) statusEl.textContent = "";
  if (selectedEl) selectedEl.textContent = `Session: ${sid}`;
  if (tbody) tbody.innerHTML = "<tr><td colspan='5' class='text-muted'>Loading...</td></tr>";
  try {
    const rows = await apiGet(`${API_ADMIN}/journey/session/${encodeURIComponent(sid)}/events`);
    if (!tbody) return;
    if (!rows || !rows.length) {
      tbody.innerHTML = "<tr><td colspan='5' class='text-muted'>No events for this session</td></tr>";
      return;
    }
    tbody.innerHTML = rows
      .map(
        (ev) => `
          <tr>
            <td>${escapeHtml(ev.event_ts || "")}</td>
            <td>${
              ev.stage && String(ev.stage).toUpperCase() === "VIEW_PRODUCT" && ev.product_id != null
                ? `<button class="btn btn-sm p-0 border-0 bg-transparent" data-journey-product="${escapeHtml(ev.product_id)}" type="button">${stageBadge(ev.stage)}</button>`
                : stageBadge(ev.stage)
            }</td>
            <td>${
              ev.product_id == null
                ? ""
                : `<button class="btn btn-sm btn-outline-secondary" data-journey-product="${escapeHtml(ev.product_id)}" type="button">${escapeHtml(ev.product_id)}</button>`
            }</td>
            <td>${escapeHtml(ev.order_id == null ? "" : ev.order_id)}</td>
            <td>${escapeHtml(ev.failure_reason || "")}</td>
          </tr>
        `
      )
      .join("");

    tbody.querySelectorAll("[data-journey-product]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const pid = btn.getAttribute("data-journey-product") || "";
        await openJourneyProduct(pid);
      });
    });
  } catch (e) {
    if (statusEl) statusEl.textContent = e.message || String(e);
    if (tbody) tbody.innerHTML = `<tr><td colspan='5' class='text-danger'>${escapeHtml(e.message || String(e))}</td></tr>`;
  }
}

async function initJourney() {
  const userEl = document.getElementById("adminUser");
  const passEl = document.getElementById("adminPass");
  const loginBtn = document.getElementById("adminLoginBtn");
  const statusEl = document.getElementById("adminLoginStatus");
  const logoutBtn = document.getElementById("adminLogoutBtn");
  const refreshBtn = document.getElementById("refreshJourneyBtn");
  const clearBtn = document.getElementById("clearJourneyBtn");

  requireAdminUi();

  if (isAdmin()) {
    await refreshJourneySessions();
  }

  if (loginBtn) {
    loginBtn.addEventListener("click", async () => {
      const username = String((userEl && userEl.value) || "").trim();
      const password = String((passEl && passEl.value) || "").trim();
      if (!username || !password) {
        if (statusEl) statusEl.textContent = "Enter Admin ID and password";
        return;
      }
      if (statusEl) statusEl.textContent = "Logging in...";
      try {
        const res = await apiPost(`${API_ADMIN}/login`, { username, password });
        saveAdminKey(res.admin_key);
        requireAdminUi();
        if (statusEl) statusEl.textContent = "";
        await refreshJourneySessions();
        showToast("Admin login success");
      } catch (e) {
        if (statusEl) statusEl.textContent = e.message || String(e);
      }
    });
  }

  if (logoutBtn) {
    logoutBtn.addEventListener("click", () => {
      saveAdminKey("");
      requireAdminUi();
      if (statusEl) statusEl.textContent = "Logged out";
      showToast("Logged out");
    });
  }

  if (refreshBtn) refreshBtn.addEventListener("click", refreshJourneySessions);
  if (clearBtn) {
    clearBtn.addEventListener("click", () => {
      const tbody = document.getElementById("journeySessionsTbody");
      const et = document.getElementById("journeyEventsTbody");
      const sel = document.getElementById("journeySelectedSession");
      const status = document.getElementById("journeyStatus");
      if (tbody) tbody.innerHTML = "<tr><td colspan='6' class='text-muted'>Cleared</td></tr>";
      if (et) et.innerHTML = "<tr><td colspan='5' class='text-muted'>Select a session</td></tr>";
      if (sel) sel.textContent = "";
      if (status) status.textContent = "";
    });
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  showBrandIntro();
  document.querySelectorAll(".navbar-globalcart a.nav-link").forEach((a) => {
    a.addEventListener("click", (e) => {
      const href = a.getAttribute("href") || "";
      if (!href || href.startsWith("#")) return;
      if (a.getAttribute("target") === "_blank") return;
      if (e.defaultPrevented) return;
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
      try {
        const u = new URL(href, window.location.origin);
        if (u.origin !== window.location.origin) return;
        if (u.pathname === window.location.pathname && u.search === window.location.search) return;
      } catch {
        return;
      }
      e.preventDefault();
      document.body.classList.add("gc-page-exit");
      window.setTimeout(() => {
        window.location.href = href;
      }, 160);
    });
  });

  const page = document.body.getAttribute("data-page") || "";
  try {
    if (page === "admin") await initAdmin();
    else if (page === "audit") await initAudit();
    else if (page === "analytics") await initAnalytics();
    else if (page === "journey") await initJourney();
  } catch (e) {
    const el = document.getElementById("pageError");
    if (el) el.textContent = e.message || String(e);
  }
});
