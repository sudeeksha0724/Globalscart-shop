const API_BASE = "";
const API_CUSTOMER = "/api/customer";
const PRODUCT_PLACEHOLDER = "/assets/images/products/placeholder.svg";

function normalizeProductImageUrl(url) {
  const s = url ? String(url).trim() : "";
  return s ? s : PRODUCT_PLACEHOLDER;
}

function wireProductImageEl(img) {
  if (!img || img.dataset.gcWired) return;
  img.dataset.gcWired = "1";
  img.addEventListener("error", () => {
    if (img.dataset.gcFallbackApplied) return;
    img.dataset.gcFallbackApplied = "1";
    img.src = PRODUCT_PLACEHOLDER;
  });
}

function wireProductImages(container) {
  if (!container) return;
  container.querySelectorAll("img[data-gc-img]").forEach((img) => wireProductImageEl(img));
}

function qs(name) {
  const url = new URL(window.location.href);
  return url.searchParams.get(name);
}

// ... (rest of the code remains the same)

function productCardHtml(p) {
  return `
    <div class="col">
      <div class="card h-100 shadow-sm">
        <img src="${normalizeProductImageUrl(p.image_url)}" class="card-img-top product-card-img" alt="${p.product_name}" loading="lazy" decoding="async" data-gc-img="1" />
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
            <a class="btn btn-outline-primary w-50" href="/shop/product.html?id=${p.product_id}">View</a>
            <button class="btn btn-accent w-50" data-add="${p.product_id}">Add</button>
          </div>
        </div>
      </div>
    </div>
  `;
}

async function initHome() {
  updateCartBadge();
  updateCustomerLabel();

  wireCustomerSetButtons();

  const grid = document.getElementById("featuredGrid");
  const products = await apiGet(`${API_CUSTOMER}/products?limit=8&offset=0`);
  grid.innerHTML = products.map(productCardHtml).join("");
  wireAddButtons(grid);
  wireProductImages(grid);
}

async function initProducts() {
  updateCartBadge();
  updateCustomerLabel();

  const grid = document.getElementById("productsGrid");
  const input = document.getElementById("searchInput");
  const voiceBtn = document.getElementById("voiceSearchBtn");
  const voiceStatus = document.getElementById("voiceStatus");

  const all = await apiGet(`${API_CUSTOMER}/products?limit=120&offset=0`);

  function render(list) {
    grid.innerHTML = list.map(productCardHtml).join("");
    wireAddButtons(grid);
    wireProductImages(grid);
  }

  render(all);

  function runSearchFromInput() {
    if (!input) return;
    const q = input.value.trim().toLowerCase();
    if (!q) {
      render(all);
      return;
    }
    const filtered = all.filter(
      (p) =>
        (p.product_name || "").toLowerCase().includes(q) ||
        (p.brand || "").toLowerCase().includes(q) ||
        (p.category_l1 || "").toLowerCase().includes(q)
    );
    render(filtered);
  }

  if (input) input.addEventListener("input", runSearchFromInput);

  // ... (rest of the code remains the same)

  async function initProduct() {
    updateCartBadge();
    updateCustomerLabel();

    const pid = Number(qs("id"));
    if (!pid) {
      document.getElementById("productContainer").innerHTML = "<div class='alert alert-danger'>Missing product id</div>";
      return;
    }

    const p = await apiGet(`${API_CUSTOMER}/products/${pid}`);

    const img = document.getElementById("pImg");
    if (img) {
      img.setAttribute("data-gc-img", "1");
      img.decoding = "async";
      wireProductImageEl(img);
      img.src = normalizeProductImageUrl(p.image_url);
      img.alt = p.product_name || "Product";
    }

    const itemsWrap = document.getElementById("itemsWrap");
    if (itemsWrap) {
      itemsWrap.querySelectorAll("input[data-qty]").forEach((inp) => {
        inp.addEventListener("change", () => {
          setQty(Number(inp.getAttribute("data-qty")), Number(inp.value));
          render();
        });
      });
    }
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
      const res = await apiPost(`${API_CUSTOMER}/orders`, payload);
      saveCart([]);
      showToast(`Order placed! Order ID: ${res.order_id}`);
      await render();
    } catch (e) {
      showToast(e.message || "Order failed");
      placeBtn.disabled = false;
    }
  });

  await render();
}

async function initOrders() {
  updateCartBadge();
  updateCustomerLabel();

  const hint = document.getElementById("ordersHint");
  const list = document.getElementById("ordersList");
  const refreshBtn = document.getElementById("refreshOrdersBtn");

  async function render() {
    const c = getCustomer();
    if (!c || !c.customer_id) {
      if (hint) hint.textContent = "Set a demo customer on Home to see your orders.";
      if (list) list.innerHTML = "";
      return;
    }

    if (hint) hint.textContent = `Showing orders for customer_id=${c.customer_id}`;
    const out = await apiGet(`${API_CUSTOMER}/orders/by-customer/${Number(c.customer_id)}?limit=25`);
    const orders = (out && out.orders) || [];

    if (!orders.length) {
      list.innerHTML = "<div class='alert alert-info'>No orders found yet. Place an order first.</div>";
      return;
    }

    const timelines = await Promise.all(
      orders.map((o) =>
        apiGet(`${API_CUSTOMER}/orders/${Number(o.order_id)}/timeline?customer_id=${Number(c.customer_id)}`).catch(() => null)
      )
    );
    const tMap = new Map(timelines.filter(Boolean).map((t) => [Number(t.order_id), t]));

    list.innerHTML = orders
      .map((o) => {
        const canCancel = String(o.order_status || "").toUpperCase() === "PLACED";
        const items = Array.isArray(o.items) ? o.items : [];
        const t = tMap.get(Number(o.order_id));
        const tl = timelineHtml(t);
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
              ${tl}
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
        const reason = String(prompt("Why are you cancelling this order? (Required)") || "").trim();
        if (!reason) {
          showToast("Cancellation reason required");
          return;
        }
        try {
          await apiPost(`${API_CUSTOMER}/orders/${orderId}/cancel`, { customer_id: Number(c.customer_id), reason });
          showToast("Order cancelled");
          await loadOrders();
        } catch (err) {
          showToast(err.message || "Failed to cancel", "error");
        }
      });
    });

    if (refreshBtn) refreshBtn.addEventListener("click", render);
    await render();
  }

  async function render() {
    const c = getCustomer();
    if (!c || !c.customer_id) {
      if (hint) hint.textContent = "Set a demo customer on Home to see your orders.";
      if (list) list.innerHTML = "";
      return;
    }

    if (hint) hint.textContent = `Showing orders for customer_id=${c.customer_id}`;
    const out = await apiGet(`${API_CUSTOMER}/orders/by-customer/${Number(c.customer_id)}?limit=25`);
    const orders = (out && out.orders) || [];
    // ...render orders logic here...
  }

  wireLogout();

  const page = document.body.getAttribute("data-page") || "";
  try {
    if (page === "home") await initHome();
    else if (page === "products") await initProducts();
    else if (page === "product") await initProduct();
    else if (page === "cart") await initCart();
    else if (page === "orders") await initOrders();
  } catch (e) {
    const el = document.getElementById("pageError");
    if (el) el.textContent = e.message || String(e);
  }
});
