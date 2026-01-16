const API_BASE = "";

function qs(name) {
  const url = new URL(window.location.href);
  return url.searchParams.get(name);
}

function getCustomer() {
  try {
    const raw = localStorage.getItem("globalcart_customer");
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function getAdminKey() {
  try {
    return localStorage.getItem("globalcart_admin_key") || "";
  } catch {
    return "";
  }
}

function saveAdminKey(k) {
  const key = String(k || "").trim();
  if (!key) {
    localStorage.removeItem("globalcart_admin_key");
    return;
  }
  localStorage.setItem("globalcart_admin_key", key);
}

function isAdmin() {
  return Boolean(getAdminKey());
}

function redirectToAdmin() {
  if (window.location.pathname !== "/static/admin.html") {
    window.location.href = "/static/admin.html";
  }
}

function hideEl(id) {
  const el = document.getElementById(id);
  if (el) el.classList.add("d-none");
}

function showEl(id) {
  const el = document.getElementById(id);
  if (el) el.classList.remove("d-none");
}

function applyRoleUi() {
  if (isAdmin()) {
    hideEl("loginEmail");
    hideEl("loginEmailBtn");
    hideEl("loginHint");
  }
}

function saveCustomer(c) {
  if (!c) {
    localStorage.removeItem("globalcart_customer");
    updateCustomerLabel();
    return;
  }
  localStorage.setItem("globalcart_customer", JSON.stringify(c));
  updateCustomerLabel();
}

function updateCustomerLabel() {
  const el = document.getElementById("customerLabel");
  if (!el) return;
  const c = getCustomer();
  el.textContent = c && c.email ? `Hi, ${c.email}` : "";
}

async function resolveCustomerByEmail(email) {
  const res = await apiPost("/customers/resolve", { email });
  saveCustomer(res);
  return res;
}

function wireLoginBtnPrompt() {
  const loginBtn = document.getElementById("loginBtn");
  if (!loginBtn) return;
  loginBtn.addEventListener("click", async () => {
    const email = String(prompt("Enter email") || "").trim();
    if (!email) return;
    try {
      await resolveCustomerByEmail(email);
      showToast("Customer set");
    } catch (e) {
      showToast("Login failed");
    }
  });
}

function kpiHtml(kpis) {
  if (!kpis || !kpis.metrics) return "(no KPI data)";
  const m = kpis.metrics;
  const money = (x) => `₹${Number(x || 0).toFixed(2)}`;
  const num = (x) => `${Number(x || 0).toFixed(0)}`;
  return `
    <div class="d-flex justify-content-between"><span>Net revenue</span><strong>${money(m.net_revenue_total)}</strong></div>
    <div class="d-flex justify-content-between"><span>Orders</span><strong>${num(m.orders_total)}</strong></div>
    <div class="d-flex justify-content-between"><span>Refunds</span><strong>${money(m.refund_amount_total)}</strong></div>
    <div class="d-flex justify-content-between"><span>Shipping</span><strong>${money(m.shipping_cost_total)}</strong></div>
    <div class="text-muted mt-2">Snapshot: ${kpis.snapshot_ts} (${kpis.label})</div>
  `;
}

async function refreshKpis() {
  const panel = document.getElementById("kpiPanel");
  if (!panel) return;
  const adminKey = getAdminKey();
  if (!adminKey) {
    panel.textContent = "Admin key required to view KPIs.";
    return;
  }
  panel.textContent = "Loading KPIs...";
  try {
    const kpis = await apiGet("/kpis/latest");
    panel.innerHTML = kpiHtml(kpis);
  } catch (e) {
    panel.textContent = e.message || String(e);
  }
}

function formatMoney(x) {
  return `₹${Number(x).toFixed(2)}`;
}

function getCart() {
  try {
    const raw = localStorage.getItem("globalcart_cart");
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function saveCart(cart) {
  localStorage.setItem("globalcart_cart", JSON.stringify(cart));
  updateCartBadge();
}

function cartCount() {
  return getCart().reduce((a, x) => a + (x.qty || 0), 0);
}

function updateCartBadge() {
  const el = document.getElementById("cartCount");
  if (!el) return;
  el.textContent = String(cartCount());
}

function addToCart(productId, qty) {
  const cart = getCart();
  const pid = Number(productId);
  const q = Number(qty);

  const found = cart.find((x) => Number(x.product_id) === pid);
  if (found) {
    found.qty = Math.min(20, (Number(found.qty) || 0) + q);
  } else {
    cart.push({ product_id: pid, qty: q });
  }
  saveCart(cart);
}

function removeFromCart(productId) {
  const pid = Number(productId);
  const cart = getCart().filter((x) => Number(x.product_id) !== pid);
  saveCart(cart);
}

function setQty(productId, qty) {
  const pid = Number(productId);
  const q = Math.max(1, Math.min(20, Number(qty)));
  const cart = getCart();
  const found = cart.find((x) => Number(x.product_id) === pid);
  if (!found) return;
  found.qty = q;
  saveCart(cart);
}

async function apiGet(path, opts) {
  let res;
  try {
    const headers = Object.assign({}, (opts && opts.headers) || {});
    const adminKey = getAdminKey();
    if (adminKey) headers["X-Admin-Key"] = adminKey;
    res = await fetch(`${API_BASE}${path}`, { headers });
  } catch (e) {
    throw new Error("Backend not reachable. Start server with: make dev");
  }
  if (!res.ok) {
    let msg = "";
    try {
      const j = await res.json();
      msg = j && j.detail ? String(j.detail) : JSON.stringify(j);
    } catch {
      msg = await res.text();
    }
    throw new Error(msg || `Request failed: ${res.status}`);
  }
  return res.json();
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
  } catch (e) {
    throw new Error("Backend not reachable. Start server with: make dev");
  }

  if (!res.ok) {
    let msg = "";
    try {
      const j = await res.json();
      msg = j && j.detail ? String(j.detail) : JSON.stringify(j);
    } catch {
      msg = await res.text();
    }
    throw new Error(msg || `Request failed: ${res.status}`);
  }
  return res.json();
}

function productCardHtml(p) {
  return `
    <div class="col">
      <div class="card h-100 shadow-sm">
        <img src="${p.image_url}" class="card-img-top product-card-img" alt="${p.product_name}" />
        <div class="card-body d-flex flex-column">
          <div class="fw-semibold mb-1">${p.product_name}</div>
          <div class="text-muted small mb-2">${p.brand} • ${p.category_l1}</div>

          <div class="mb-3">
            <div class="d-flex align-items-baseline gap-2">
              <div class="fs-5 fw-bold">${formatMoney(p.sell_price)}</div>
              <div class="price-original">${formatMoney(p.list_price)}</div>
              <span class="badge text-bg-success">${p.discount_pct}% off</span>
            </div>
          </div>

          <div class="mt-auto d-flex gap-2">
            <a class="btn btn-outline-primary w-50" href="/static/product.html?id=${p.product_id}">View</a>
            <button class="btn btn-accent w-50" data-add="${p.product_id}">Add</button>
          </div>
        </div>
      </div>
    </div>
  `;
}

function wireAddButtons(container) {
  container.querySelectorAll("button[data-add]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const pid = Number(btn.getAttribute("data-add"));
      addToCart(pid, 1);
      showToast("Added to cart");
    });
  });
}

function showToast(message) {
  const el = document.getElementById("toast");
  if (!el) return;
  el.querySelector(".toast-body").textContent = message;
  const toast = bootstrap.Toast.getOrCreateInstance(el);
  toast.show();
}

async function initHome() {
  if (isAdmin()) {
    redirectToAdmin();
    return;
  }
  updateCartBadge();
  updateCustomerLabel();
  applyRoleUi();

  hideEl("kpiPanel");
  hideEl("refreshKpisBtn");

  const kBtn = document.getElementById("refreshKpisBtn");
  if (kBtn) kBtn.addEventListener("click", refreshKpis);

  const loginBtn = document.getElementById("loginBtn");
  if (loginBtn) {
    loginBtn.addEventListener("click", async () => {
      const emailInput = document.getElementById("loginEmail");
      const email = emailInput ? String(emailInput.value || "").trim() : String(prompt("Enter email") || "").trim();
      if (!email) return;
      try {
        const c = await resolveCustomerByEmail(email);
        const hint = document.getElementById("loginHint");
        if (hint) hint.textContent = `Using customer_id=${c.customer_id}`;
        showToast("Customer set");
      } catch (e) {
        showToast("Login failed");
      }
    });
  }

  const loginEmailBtn = document.getElementById("loginEmailBtn");
  if (loginEmailBtn) {
    loginEmailBtn.addEventListener("click", async () => {
      const email = String(document.getElementById("loginEmail").value || "").trim();
      if (!email) return;
      try {
        const c = await resolveCustomerByEmail(email);
        const hint = document.getElementById("loginHint");
        if (hint) hint.textContent = `Using customer_id=${c.customer_id}`;
        showToast("Customer set");
      } catch (e) {
        showToast("Login failed");
      }
    });
  }

  const grid = document.getElementById("featuredGrid");
  const products = await apiGet("/products?limit=8&offset=0");
  grid.innerHTML = products.map(productCardHtml).join("");
  wireAddButtons(grid);
}

async function initProducts() {
  if (isAdmin()) {
    redirectToAdmin();
    return;
  }
  updateCartBadge();
  updateCustomerLabel();
  wireLoginBtnPrompt();

  const grid = document.getElementById("productsGrid");
  const input = document.getElementById("searchInput");

  const all = await apiGet("/products?limit=120&offset=0");

  function render(list) {
    grid.innerHTML = list.map(productCardHtml).join("");
    wireAddButtons(grid);
  }

  render(all);

  input.addEventListener("input", () => {
    const q = input.value.trim().toLowerCase();
    if (!q) {
      render(all);
      return;
    }
    const filtered = all.filter((p) =>
      (p.product_name || "").toLowerCase().includes(q) ||
      (p.brand || "").toLowerCase().includes(q) ||
      (p.category_l1 || "").toLowerCase().includes(q)
    );
    render(filtered);
  });
}

async function initProduct() {
  if (isAdmin()) {
    redirectToAdmin();
    return;
  }
  updateCartBadge();
  updateCustomerLabel();
  wireLoginBtnPrompt();

  const pid = Number(qs("id"));
  if (!pid) {
    document.getElementById("productContainer").innerHTML = "<div class='alert alert-danger'>Missing product id</div>";
    return;
  }

  const p = await apiGet(`/products/${pid}`);

  document.getElementById("pImg").src = p.image_url;
  document.getElementById("pName").textContent = p.product_name;
  document.getElementById("pBrand").textContent = `${p.brand} • ${p.category_l1} / ${p.category_l2}`;
  document.getElementById("pDesc").textContent = p.description;

  document.getElementById("pSell").textContent = formatMoney(p.sell_price);
  document.getElementById("pList").textContent = formatMoney(p.list_price);
  document.getElementById("pDisc").textContent = `${p.discount_pct}% off`;

  const qtyEl = document.getElementById("qty");
  document.getElementById("addBtn").addEventListener("click", () => {
    addToCart(pid, Number(qtyEl.value || 1));
    showToast("Added to cart");
  });
}

async function initCart() {
  if (isAdmin()) {
    redirectToAdmin();
    return;
  }
  updateCartBadge();
  updateCustomerLabel();

  const itemsWrap = document.getElementById("cartItems");
  const totalEl = document.getElementById("cartTotal");
  const placeBtn = document.getElementById("placeOrderBtn");

  const kBtn = document.getElementById("refreshKpisBtn");
  if (kBtn) kBtn.addEventListener("click", refreshKpis);

  wireLoginBtnPrompt();

  async function render() {
    const cart = getCart();
    if (!cart.length) {
      itemsWrap.innerHTML = "<div class='alert alert-info'>Your cart is empty. Add products first.</div>";
      totalEl.textContent = formatMoney(0);
      placeBtn.disabled = true;
      return;
    }

    placeBtn.disabled = false;

    const details = await Promise.all(cart.map((c) => apiGet(`/products/${c.product_id}`)));
    const map = new Map(details.map((d) => [Number(d.product_id), d]));

    let total = 0;

    itemsWrap.innerHTML = cart
      .map((c) => {
        const p = map.get(Number(c.product_id));
        const qty = Number(c.qty);
        const line = (p ? Number(p.sell_price) : 0) * qty;
        total += line;

        return `
          <div class="card mb-3 shadow-sm">
            <div class="card-body d-flex gap-3 align-items-center">
              <img src="${p.image_url}" alt="${p.product_name}" style="width: 80px; height: 80px; object-fit: cover;" class="rounded" />
              <div class="flex-grow-1">
                <div class="fw-semibold">${p.product_name}</div>
                <div class="text-muted small">${p.brand}</div>
                <div class="mt-1">
                  <span class="fw-bold">${formatMoney(p.sell_price)}</span>
                  <span class="price-original ms-2">${formatMoney(p.list_price)}</span>
                  <span class="badge text-bg-success ms-2">${p.discount_pct}% off</span>
                </div>
              </div>
              <div style="width: 120px;">
                <label class="form-label small mb-1">Qty</label>
                <input class="form-control" type="number" min="1" max="20" value="${qty}" data-qty="${p.product_id}" />
              </div>
              <div class="text-end" style="width: 140px;">
                <div class="small text-muted">Line total</div>
                <div class="fw-bold">${formatMoney(line)}</div>
                <button class="btn btn-sm btn-outline-danger mt-2" data-remove="${p.product_id}">Remove</button>
              </div>
            </div>
          </div>
        `;
      })
      .join("");

    totalEl.textContent = formatMoney(total);

    itemsWrap.querySelectorAll("button[data-remove]").forEach((b) => {
      b.addEventListener("click", () => {
        removeFromCart(Number(b.getAttribute("data-remove")));
        render();
      });
    });

    itemsWrap.querySelectorAll("input[data-qty]").forEach((inp) => {
      inp.addEventListener("change", () => {
        setQty(Number(inp.getAttribute("data-qty")), Number(inp.value));
        render();
      });
    });
  }

  placeBtn.addEventListener("click", async () => {
    try {
      placeBtn.disabled = true;
      const cart = getCart();
      const c = getCustomer();
      const payload = {
        items: cart.map((c) => ({ product_id: c.product_id, qty: c.qty })),
        channel: "WEB",
        customer_id: c && c.customer_id ? Number(c.customer_id) : null,
      };
      const res = await apiPost("/orders", payload);
      saveCart([]);
      showToast(`Order placed! Order ID: ${res.order_id}`);
      await render();
    } catch (e) {
      showToast("Order failed. Check backend logs.");
      placeBtn.disabled = false;
    }
  });

  await render();
}

async function initOrders() {
  if (isAdmin()) {
    redirectToAdmin();
    return;
  }

  updateCartBadge();
  updateCustomerLabel();
  wireLoginBtnPrompt();

  const hint = document.getElementById("ordersHint");
  const list = document.getElementById("ordersList");
  const refreshBtn = document.getElementById("refreshOrdersBtn");

  async function render() {
    const c = getCustomer();
    if (!c || !c.customer_id) {
      if (hint) hint.textContent = "Login as a customer to see your orders.";
      if (list) list.innerHTML = "";
      return;
    }

    if (hint) hint.textContent = `Showing orders for customer_id=${c.customer_id}`;
    const out = await apiGet(`/orders/by-customer/${Number(c.customer_id)}?limit=25`);
    const orders = (out && out.orders) || [];

    if (!orders.length) {
      list.innerHTML = "<div class='alert alert-info'>No orders found yet. Place an order first.</div>";
      return;
    }

    list.innerHTML = orders
      .map((o) => {
        const canCancel = String(o.order_status || "").toUpperCase() === "PLACED";
        const items = Array.isArray(o.items) ? o.items : [];
        const itemsHtml = items.length
          ? `
              <div class="mt-2">
                <div class="small text-muted">Items</div>
                <ul class="mb-0">
                  ${items
                    .map(
                      (it) =>
                        `<li><span class="fw-semibold">${it.product_name}</span> <span class="text-muted">× ${it.qty}</span></li>`
                    )
                    .join("")}
                </ul>
              </div>
            `
          : "";
        return `
          <div class="card mb-3 shadow-sm">
            <div class="card-body">
              <div class="d-flex justify-content-between align-items-center">
                <div>
                  <div class="fw-semibold">Order #${o.order_id}</div>
                  <div class="text-muted small">Placed: ${o.order_ts}</div>
                </div>
                <div class="text-end">
                  <div class="small text-muted">Status</div>
                  <div class="fw-bold">${o.order_status}</div>
                </div>
              </div>
              ${itemsHtml}
              <hr />
              <div class="d-flex justify-content-between align-items-center">
                <div>
                  <div class="small text-muted">Total</div>
                  <div class="fw-bold">${formatMoney(o.net_amount)}</div>
                </div>
                ${canCancel ? `<button class="btn btn-outline-danger" data-cancel="${o.order_id}">Cancel</button>` : ''}
              </div>
            </div>
          </div>
        `;
      })
      .join("");

    list.querySelectorAll("button[data-cancel]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const c = getCustomer();
        const orderId = Number(btn.getAttribute("data-cancel"));
        if (!c || !c.customer_id) return;
        try {
          const reason = String(prompt("Why are you cancelling this order? (Required)") || "").trim();
          if (!reason) {
            showToast("Cancellation reason required");
            return;
          }
          btn.disabled = true;
          await apiPost(`/orders/${orderId}/cancel`, { customer_id: Number(c.customer_id), reason });
          showToast("Order cancelled");
          await render();
        } catch (e) {
          showToast(e.message || String(e));
          btn.disabled = false;
        }
      });
    });

  if (refreshBtn) refreshBtn.addEventListener("click", render);
  await render();
}

async function initAdmin() {
  const loginCard = document.getElementById("adminLoginCard");
  const content = document.getElementById("adminContent");

  const userEl = document.getElementById("adminUser");
  const passEl = document.getElementById("adminPass");
  const loginBtn = document.getElementById("adminLoginBtn");
  const statusEl = document.getElementById("adminLoginStatus");
  const logoutBtn = document.getElementById("adminLogoutBtn");

  const refreshKpisBtn = document.getElementById("refreshKpisBtn");

  function showDashboard() {
    if (loginCard) loginCard.classList.add("d-none");
    if (content) content.classList.remove("d-none");
  }

  function showLogin() {
    if (loginCard) loginCard.classList.remove("d-none");
    if (content) content.classList.add("d-none");
  }

  if (getAdminKey()) {
    showDashboard();
    await refreshKpis();
  } else {
    showLogin();
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
        const res = await apiPost("/admin/login", { username, password });
        saveAdminKey(res.admin_key);
        showDashboard();
        if (statusEl) statusEl.textContent = "";
        await refreshKpis();
        showToast("Admin login success");
      } catch (e) {
        if (statusEl) statusEl.textContent = e.message || String(e);
      }
    });
  }

  if (logoutBtn) {
    logoutBtn.addEventListener("click", () => {
      saveAdminKey("");
      showLogin();
      if (statusEl) statusEl.textContent = "Logged out";
      showToast("Logged out");
    });
  }

  if (refreshKpisBtn) refreshKpisBtn.addEventListener("click", refreshKpis);
}

document.addEventListener("DOMContentLoaded", async () => {
  const page = document.body.getAttribute("data-page") || "";
  try {
    if (page === "home") await initHome();
    else if (page === "products") await initProducts();
    else if (page === "product") await initProduct();
    else if (page === "cart") await initCart();
    else if (page === "orders") await initOrders();
    else if (page === "admin") await initAdmin();
  } catch (e) {
    const el = document.getElementById("pageError");
    if (el) el.textContent = e.message || String(e);
  }
});
