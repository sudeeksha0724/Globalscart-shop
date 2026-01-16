const API_BASE = "";
const API_CUSTOMER = "/api/customer";
const PRODUCT_PLACEHOLDER = "/assets/images/products/placeholder.svg";

function qs(name) {
  const url = new URL(window.location.href);
  return url.searchParams.get(name);
}

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

function formatMoney(x) {
  return `₹${Number(x || 0).toFixed(2)}`;
}

function getCustomer() {
  try {
    const raw = localStorage.getItem("globalcart_customer");
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
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

function logoutCustomer() {
  localStorage.removeItem("globalcart_customer");
  updateCustomerLabel();
}

function updateCustomerLabel() {
  const el = document.getElementById("customerLabel");
  if (!el) return;
  const c = getCustomer();
  el.textContent = c && c.email ? `Hi, ${c.email}` : "";
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
  return getCart().reduce((a, x) => a + (Number(x.qty) || 0), 0);
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
    res = await fetch(`${API_BASE}${path}`, { headers });
  } catch {
    throw new Error("Backend not reachable. Start server with: uvicorn backend.main:app --reload");
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
    res = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers,
      body: JSON.stringify(body || {}),
    });
  } catch {
    throw new Error("Backend not reachable. Start server with: uvicorn backend.main:app --reload");
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

function showToast(message) {
  const el = document.getElementById("toast");
  if (!el) return;
  el.querySelector(".toast-body").textContent = message;
  const toast = bootstrap.Toast.getOrCreateInstance(el);
  toast.show();
}

function wireLogout() {
  const btn = document.getElementById("logoutBtn");
  if (!btn) return;
  btn.addEventListener("click", (e) => {
    e.preventDefault();
    logoutCustomer();
    showToast("Logged out");
    window.location.href = "/shop/";
  });
}

async function resolveCustomerByEmail(email) {
  const res = await apiPost(`${API_CUSTOMER}/customers/resolve`, { email });
  saveCustomer(res);
  return res;
}

function wireCustomerSetButtons() {
  const loginBtn = document.getElementById("loginBtn");
  if (loginBtn) {
    loginBtn.addEventListener("click", async () => {
      const email = String(prompt("Enter email") || "").trim();
      if (!email) return;
      try {
        const c = await resolveCustomerByEmail(email);
        const hint = document.getElementById("loginHint");
        if (hint) hint.textContent = `Using customer_id=${c.customer_id}`;
        showToast("Customer set");
      } catch {
        showToast("Customer set failed");
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
      } catch {
        showToast("Customer set failed");
      }
    });
  }
}

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

function wireAddButtons(container) {
  container.querySelectorAll("button[data-add]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const pid = Number(btn.getAttribute("data-add"));
      addToCart(pid, 1);
      showToast("Added to cart");
    });
  });
}

function timelineStepClass(stage, currentStatus) {
  const cur = String(currentStatus || "").toUpperCase();
  const s = String(stage || "").toUpperCase();

  if (cur === "CANCELLED") {
    if (s === "CANCELLED") return "gc-step cancelled";
    if (s === "PLACED") return "gc-step completed";
    return "gc-step";
  }

  const order = ["PLACED", "SHIPPED", "DELIVERED"];
  const curIdx = order.indexOf(cur);
  const idx = order.indexOf(s);
  if (idx < 0) return "gc-step";
  if (idx < curIdx) return "gc-step completed";
  if (idx === curIdx) return "gc-step active";
  return "gc-step";
}

function timelineHtml(t) {
  if (!t || !Array.isArray(t.stages)) return "";
  const cur = String(t.current_status || "").toUpperCase();
  const stages = [
    { stage: "PLACED" },
    { stage: "SHIPPED" },
    { stage: "DELIVERED" },
    { stage: "CANCELLED" },
  ].map((s) => {
    const found = t.stages.find((x) => String(x.stage || "").toUpperCase() === s.stage);
    return { stage: s.stage, timestamp: found ? found.timestamp : null };
  });

  const visible = cur === "CANCELLED" ? [stages[0], stages[3]] : stages.slice(0, 3);
  const steps = visible
    .map(
      (s) => `
        <div class="${timelineStepClass(s.stage, cur)}">
          <div class="gc-dot"></div>
          <div class="gc-label">${s.stage}</div>
          <div class="gc-ts">${s.timestamp || ""}</div>
        </div>
      `
    )
    .join("");

  const cancelReason =
    cur === "CANCELLED" && t.cancellation_reason
      ? `<div class="alert alert-danger py-2 px-3 mt-2 mb-0 small">Cancelled: ${t.cancellation_reason}</div>`
      : "";

  return `
    <div class="gc-timeline">${steps}</div>
    ${cancelReason}
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

function isSpeechAvailable() {
  return Boolean(window.SpeechRecognition || window.webkitSpeechRecognition);
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

  function applySearchText(q) {
    const s = String(q || "").trim().toLowerCase();
    if (input) input.value = q;
    if (!s) {
      render(all);
      return;
    }
    const filtered = all.filter(
      (p) =>
        (p.product_name || "").toLowerCase().includes(s) ||
        (p.brand || "").toLowerCase().includes(s) ||
        (p.category_l1 || "").toLowerCase().includes(s) ||
        (p.category_l2 || "").toLowerCase().includes(s)
    );
    render(filtered);
  }

  render(all);

  if (input) input.addEventListener("input", () => applySearchText(input.value));

  function setVoiceUi(listening, text) {
    if (voiceBtn) voiceBtn.classList.toggle("listening", Boolean(listening));
    if (voiceStatus) {
      voiceStatus.style.display = text ? "block" : "none";
      voiceStatus.textContent = text || "";
    }
  }

  if (voiceBtn) {
    if (!isSpeechAvailable()) {
      voiceBtn.disabled = true;
      voiceBtn.title = "Voice search not supported in this browser";
    } else {
      const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
      const recognition = new SpeechRecognition();
      recognition.lang = "en-IN";
      recognition.interimResults = false;
      recognition.maxAlternatives = 1;

      let running = false;

      recognition.onstart = () => {
        running = true;
        setVoiceUi(true, "Listening...");
      };
      recognition.onend = () => {
        running = false;
        setVoiceUi(false, "");
      };
      recognition.onerror = () => {
        running = false;
        setVoiceUi(false, "");
        showToast("Voice search failed");
      };
      recognition.onresult = (event) => {
        const text =
          event && event.results && event.results[0] && event.results[0][0] ? String(event.results[0][0].transcript || "") : "";
        applySearchText(text);
      };

      voiceBtn.addEventListener("click", () => {
        if (running) {
          try {
            recognition.stop();
          } catch {
            setVoiceUi(false, "");
          }
          return;
        }
        try {
          recognition.start();
        } catch {
          setVoiceUi(false, "");
          showToast("Voice search could not start. Please try again.");
        }
      });
    }
  }
}

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
    img.loading = "eager";
    img.decoding = "async";
    img.src = normalizeProductImageUrl(p.image_url);
    img.alt = p.product_name || "Product";
    wireProductImageEl(img);
  }

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
  updateCartBadge();
  updateCustomerLabel();

  const itemsWrap = document.getElementById("cartItems");
  const totalEl = document.getElementById("cartTotal");
  const placeBtn = document.getElementById("placeOrderBtn");

  async function render() {
    const cart = getCart();
    if (!cart.length) {
      itemsWrap.innerHTML = "<div class='alert alert-info'>Your cart is empty. Add products first.</div>";
      totalEl.textContent = formatMoney(0);
      placeBtn.disabled = true;
      return;
    }

    placeBtn.disabled = false;

    const details = await Promise.all(cart.map((c) => apiGet(`${API_CUSTOMER}/products/${c.product_id}`)));
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
              <img src="${normalizeProductImageUrl(p && p.image_url)}" alt="${p ? p.product_name : "Product"}" style="width: 80px; height: 80px; object-fit: cover;" class="rounded" loading="lazy" decoding="async" data-gc-img="1" />
              <div class="flex-grow-1">
                <div class="fw-semibold">${p ? p.product_name : "Product"}</div>
                <div class="text-muted small">${p ? p.brand : ""}</div>
                <div class="mt-1">
                  <span class="fw-bold">${formatMoney(p ? p.sell_price : 0)}</span>
                  <span class="price-original ms-2">${formatMoney(p ? p.list_price : 0)}</span>
                  <span class="badge text-bg-success ms-2">${p ? p.discount_pct : 0}% off</span>
                </div>
              </div>
              <div style="width: 120px;">
                <label class="form-label small mb-1">Qty</label>
                <input class="form-control" type="number" min="1" max="20" value="${qty}" data-qty="${p ? p.product_id : c.product_id}" />
              </div>
              <div class="text-end" style="width: 140px;">
                <div class="small text-muted">Line total</div>
                <div class="fw-bold">${formatMoney(line)}</div>
                <button class="btn btn-sm btn-outline-danger mt-2" data-remove="${p ? p.product_id : c.product_id}">Remove</button>
              </div>
            </div>
          </div>
        `;
      })
      .join("");

    wireProductImages(itemsWrap);

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

  document.addEventListener("DOMContentLoaded", async () => {
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
