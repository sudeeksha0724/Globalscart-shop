const GC = {
  storage: {
    sessionId: 'gc_session_id',
    customer: 'gc_customer',
    cart: 'gc_cart',
  },
  api: {
    products: '/api/customer/products',
    product: (id) => `/api/customer/products/${encodeURIComponent(id)}`,
    productRating: (id) => `/api/customer/products/${encodeURIComponent(id)}/rating`,
    productReviews: (id) => `/api/customer/products/${encodeURIComponent(id)}/reviews`,
    resolveCustomer: '/api/customer/customers/resolve',
    requestOtp: '/api/auth/request-otp',
    verifyOtp: '/api/auth/verify-otp',
    signupRequestOtp: '/api/auth/signup/request-otp',
    signupVerifyOtp: '/api/auth/signup/verify-otp',
    emailExists: '/api/auth/email-exists',
    login: '/api/auth/login',
    createOrder: '/api/customer/orders',
    cancelOrder: (id) => `/api/customer/orders/${encodeURIComponent(id)}/cancel`,
    promoValidate: '/api/customer/promos/validate',
    ordersByCustomer: (id) => `/api/customer/orders/by-customer/${encodeURIComponent(id)}`,
    orderDetail: (id) => `/api/customer/orders/${encodeURIComponent(id)}`,
    orderTimeline: (id) => `/api/customer/orders/${encodeURIComponent(id)}/timeline`,
    wishlist: '/api/customer/wishlist',
    wishlistItem: (id) => `/api/customer/wishlist/${encodeURIComponent(id)}`,
    emails: '/api/customer/emails',
    funnelEvent: '/api/events/funnel',
  },
};

const GC_CANCEL_REASON_OPTIONS = [
  'Order created by mistake',
  'Item(s) would not arrive on time',
  'Delivery cost too high',
  'Item price too high',
  'Found cheaper somewhere else',
  'Need to change shipping address',
  'Need to change shipping speed',
  'Need to change billing address',
  'Need to change payment method',
  'Other',
];

function qs(sel, root = document) {
  return root.querySelector(sel);
}

async function initWishlist() {
  bindGlobalNav();

  const listEl = qs('#wishlistList');
  const cust = getCustomer();
  if (!listEl) return;

  if (!cust) {
    listEl.innerHTML = '<div class="alert alert-warning">Sign in to use your wishlist.</div>';
    return;
  }

  listEl.innerHTML = '<div class="text-secondary">Loading…</div>';
  try {
    const items = await apiFetch(`${GC.api.wishlist}?customer_id=${encodeURIComponent(cust.customer_id)}`);
    const arr = Array.isArray(items) ? items : [];
    if (!arr.length) {
      listEl.innerHTML = '<div class="alert alert-info">Your wishlist is empty.</div>';
      return;
    }

    listEl.innerHTML = '';
    for (const p of arr) {
      const card = document.createElement('div');
      card.className = 'card shadow-sm mb-3';
      card.innerHTML = `
        <div class="card-body d-flex gap-3 align-items-start">
          <img loading="lazy" src="${escapeHtml(p.image_url)}" class="rounded" style="width:96px;height:96px;object-fit:cover;" alt="${escapeHtml(p.product_name)}" />
          <div class="flex-grow-1">
            <div class="d-flex justify-content-between gap-2">
              <div>
                <div class="fw-semibold">${escapeHtml(p.product_name)}</div>
                <div class="small text-secondary">${escapeHtml(p.brand)} · ${escapeHtml(p.category_l2)}</div>
                <div class="mt-2 fw-semibold">${escapeHtml(fmtMoney(p.sell_price, 'INR'))}</div>
              </div>
              <div class="d-flex flex-column gap-2">
                <a class="btn btn-sm btn-outline-primary" href="product.html?product_id=${encodeURIComponent(p.product_id)}">View</a>
                <button class="btn btn-sm btn-primary" data-add="${escapeHtml(p.product_id)}" type="button">Add to cart</button>
                <button class="btn btn-sm btn-outline-danger" data-rm="${escapeHtml(p.product_id)}" type="button">Remove</button>
              </div>
            </div>
          </div>
        </div>
      `;
      listEl.appendChild(card);
    }

    qsa('[data-add]', listEl).forEach((btn) => {
      btn.addEventListener('click', async () => {
        const pid = btn.getAttribute('data-add');
        addToCart(pid, 1);
        toast('Added to cart', '1 item added.', 'success');
        updateNavCartCount();
      });
    });

    qsa('[data-rm]', listEl).forEach((btn) => {
      btn.addEventListener('click', async () => {
        const pid = btn.getAttribute('data-rm');
        try {
          await toggleWishlist(pid, false);
          btn.closest('.card')?.remove();
          toast('Removed', 'Removed from wishlist.', 'secondary');
        } catch (err) {
          toast('Remove failed', err.message || 'Unable to remove', 'danger');
        }
      });
    });
  } catch (err) {
    listEl.innerHTML = '<div class="text-danger">Failed to load wishlist.</div>';
  }
}

function initHomeScrollFx() {
  const hero = qs('.gc-hero');
  if (!hero) return;

  let raf = 0;
  function clamp01(x) {
    const n = Number(x);
    if (!Number.isFinite(n)) return 0;
    return Math.max(0, Math.min(1, n));
  }

  function update() {
    raf = 0;
    const y = window.scrollY || window.pageYOffset || 0;
    const h = Math.max(1, hero.offsetHeight || 1);
    const t = clamp01(y / (h * 0.9));
    document.body.style.setProperty('--gc-hero-fade', String(t));
  }

  function onScroll() {
    if (raf) return;
    raf = window.requestAnimationFrame(update);
  }

  window.addEventListener('scroll', onScroll, { passive: true });
  window.addEventListener('resize', onScroll);
  update();
}

function initHomeProductReveal(grid) {
  if (!grid) return;
  const reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (reduce) return;

  const io = new IntersectionObserver(
    (entries) => {
      for (const e of entries) {
        if (e.isIntersecting) {
          e.target.classList.add('is-in');
          io.unobserve(e.target);
        }
      }
    },
    { root: null, rootMargin: '0px 0px -10% 0px', threshold: 0.12 }
  );

  function observeNew() {
    qsa('.gc-reveal', grid).forEach((el) => {
      if (el.classList.contains('is-in')) return;
      io.observe(el);
    });
  }

  const mo = new MutationObserver(() => observeNew());
  mo.observe(grid, { childList: true, subtree: true });
  observeNew();
}

async function initOrder() {
  bindGlobalNav();

  const q = readQuery();
  const orderId = q.get('order_id');
  const detailEl = qs('#orderDetail');
  const timelineEl = qs('#orderTimeline');

  const cust = getCustomer();
  if (!cust) {
    if (detailEl) detailEl.innerHTML = '<div class="alert alert-warning">Sign in to view order details.</div>';
    return;
  }
  if (!orderId) {
    if (detailEl) detailEl.innerHTML = '<div class="alert alert-danger">Missing order_id.</div>';
    return;
  }

  if (detailEl) detailEl.innerHTML = '<div class="text-secondary">Loading…</div>';
  try {
    const detail = await apiFetch(`${GC.api.orderDetail(orderId)}?customer_id=${encodeURIComponent(cust.customer_id)}`);
    if (detailEl && detail) {
      const canCancel = String(detail.order_status || '').toUpperCase() === 'PLACED';
      const promoLine = detail.promo_code ? `<div class="small text-secondary">Promo: ${escapeHtml(detail.promo_code)} (-${escapeHtml(fmtMoney(detail.promo_discount_amount || 0, 'INR'))})</div>` : '';
      const items = (detail.items || []).map((it) => `<div class="d-flex justify-content-between"><div>${escapeHtml(it.product_name)}</div><div class="text-secondary">× ${escapeHtml(it.qty)}</div></div>`).join('');
      const cancelBtn = canCancel ? '<button class="btn btn-sm btn-outline-danger mt-3" id="cancelOrderBtn" type="button">Cancel order</button>' : '';
      const reorderBtn = (detail.items || []).length ? '<button class="btn btn-sm btn-primary mt-3" id="reorderBtn" type="button">Reorder</button>' : '';
      detailEl.innerHTML = `
        <div class="card shadow-sm">
          <div class="card-body">
            <div class="d-flex justify-content-between">
              <div>
                <div class="fw-semibold">Order #${escapeHtml(detail.order_id)}</div>
                <div class="small text-secondary">${escapeHtml(detail.order_ts)}</div>
              </div>
              <span class="badge text-bg-secondary">${escapeHtml(detail.order_status)}</span>
            </div>
            <div class="mt-3">
              <div class="small text-secondary">Payment: ${escapeHtml(detail.payment_status || 'N/A')}</div>
              ${promoLine}
            </div>
            <hr />
            <div class="fw-semibold mb-2">Items</div>
            <div class="small">${items}</div>
            <hr />
            <div class="d-flex justify-content-between"><div>Gross</div><div>${escapeHtml(fmtMoney(detail.gross_amount, 'INR'))}</div></div>
            <div class="d-flex justify-content-between"><div>Discounts</div><div>-${escapeHtml(fmtMoney(detail.discount_amount, 'INR'))}</div></div>
            <div class="d-flex justify-content-between"><div>Tax</div><div>${escapeHtml(fmtMoney(detail.tax_amount, 'INR'))}</div></div>
            <div class="d-flex justify-content-between fw-semibold mt-2"><div>Total</div><div>${escapeHtml(fmtMoney(detail.net_amount, 'INR'))}</div></div>
            <div class="d-flex gap-2 flex-wrap">
              ${reorderBtn}
              <a class="btn btn-sm btn-outline-primary mt-3" href="cart.html">View cart</a>
            </div>
            ${cancelBtn}
          </div>
        </div>
      `;

      const reorderEl = qs('#reorderBtn', detailEl);
      if (reorderEl) {
        reorderEl.addEventListener('click', async () => {
          reorderEl.disabled = true;
          try {
            const arr = Array.isArray(detail.items) ? detail.items : [];
            if (!arr.length) return;
            for (const it of arr) {
              const pid = Number(it.product_id);
              const qty = Number(it.qty || 1);
              if (!pid) continue;
              addToCart(pid, Number.isFinite(qty) && qty > 0 ? qty : 1);
            }
            updateNavCartCount();
            toast('Reordered', 'Items were added to your cart.', 'success');
          } catch (err) {
            toast('Reorder failed', err.message || 'Unable to reorder', 'danger');
          } finally {
            reorderEl.disabled = false;
          }
        });
      }

      const cancelEl = qs('#cancelOrderBtn', detailEl);
      if (cancelEl) {
        cancelEl.addEventListener('click', async () => {
          const reason = await pickCancellationReason();
          if (!reason) return;
          cancelEl.disabled = true;
          try {
            await apiFetch(GC.api.cancelOrder(orderId), {
              method: 'POST',
              body: JSON.stringify({ customer_id: Number(cust.customer_id), reason }),
            });
            toast('Order cancelled', `Order #${detail.order_id} cancelled.`, 'secondary');
            await sleep(500);
            window.location.reload();
          } catch (err) {
            toast('Cancel failed', err.message || 'Unable to cancel order', 'danger');
            cancelEl.disabled = false;
          }
        });
      }
    }

    if (timelineEl) timelineEl.innerHTML = '<div class="text-secondary">Loading timeline…</div>';
    try {
      const tl = await apiFetch(`${GC.api.orderTimeline(orderId)}?customer_id=${encodeURIComponent(cust.customer_id)}`);
      if (timelineEl && tl) {
        const stages = (tl.stages || []).map((s) => {
          const done = !!s.timestamp;
          return `
            <div class="d-flex justify-content-between align-items-center border-top pt-2 mt-2">
              <div class="d-flex align-items-center gap-2">
                <span class="badge ${done ? 'text-bg-success' : 'text-bg-secondary'}">${done ? '✓' : '•'}</span>
                <div>${escapeHtml(s.stage)}</div>
              </div>
              <div class="small ${done ? 'text-success' : 'text-secondary'}">${escapeHtml(s.timestamp || 'Pending')}</div>
            </div>
          `;
        }).join('');
        timelineEl.innerHTML = `
          <div class="card shadow-sm">
            <div class="card-body">
              <div class="fw-semibold">Tracking</div>
              <div class="small text-secondary">Current: ${escapeHtml(tl.current_status)}</div>
              <div class="mt-2">${stages}</div>
            </div>
          </div>
        `;
      }
    } catch {
      if (timelineEl) timelineEl.innerHTML = '<div class="text-secondary">Timeline unavailable.</div>';
    }
  } catch (err) {
    if (detailEl) detailEl.innerHTML = '<div class="text-danger">Failed to load order.</div>';
  }
}

async function initEmails() {
  bindGlobalNav();

  const listEl = qs('#emailsList');
  const cust = getCustomer();
  if (!listEl) return;

  if (!cust) {
    listEl.innerHTML = '<div class="alert alert-warning">Sign in to view your email inbox.</div>';
    return;
  }

  listEl.innerHTML = '<div class="text-secondary">Loading…</div>';
  try {
    const rows = await apiFetch(`${GC.api.emails}?customer_id=${encodeURIComponent(cust.customer_id)}&limit=100`);
    const arr = Array.isArray(rows) ? rows : [];
    if (!arr.length) {
      listEl.innerHTML = '<div class="alert alert-info">No emails yet.</div>';
      return;
    }
    listEl.innerHTML = '';
    for (const m of arr) {
      const card = document.createElement('div');
      card.className = 'card shadow-sm mb-3';
      card.innerHTML = `
        <div class="card-body">
          <div class="d-flex justify-content-between">
            <div class="fw-semibold">${escapeHtml(m.subject)}</div>
            <span class="badge text-bg-secondary">${escapeHtml(m.status)}</span>
          </div>
          <div class="small text-secondary">${escapeHtml(m.kind)} · ${escapeHtml(m.created_at)}</div>
          <div class="mt-2 small" style="white-space:pre-wrap;">${escapeHtml(m.body)}</div>
        </div>
      `;
      listEl.appendChild(card);
    }
  } catch (err) {
    listEl.innerHTML = '<div class="text-danger">Failed to load emails.</div>';
  }
}

async function checkEmailExists(email) {
  const e = String(email || '').trim().toLowerCase();
  if (!e) return { email: e, exists: false };
  const url = `${GC.api.emailExists}?email=${encodeURIComponent(e)}`;
  return apiFetch(url);
}

function qsa(sel, root = document) {
  return Array.from(root.querySelectorAll(sel));
}

function escapeHtml(s) {
  return String(s ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function withIntroParam(nextUrl) {
  try {
    sessionStorage.setItem('gc_force_brand_intro_shop', '1');
  } catch {
  }
  try {
    const u = new URL(nextUrl || 'index.html', window.location.href);
    u.searchParams.set('intro', '1');
    return u.toString();
  } catch {
    return String(nextUrl || 'index.html');
  }
}

function normalizeNext(nextUrl) {
  const raw = String(nextUrl || '').trim();
  if (!raw) return 'index.html';

  // Handle common bad values that would become /shop/shop.
  if (raw === 'shop' || raw === '/shop' || raw === '/shop/') return 'index.html';

  // If someone passes a full /shop/... path, strip the /shop/ prefix.
  if (raw.startsWith('/shop/')) {
    const rest = raw.slice('/shop/'.length);
    return rest || 'index.html';
  }
  if (raw === '/shop') return 'index.html';

  // If it looks like an absolute URL, keep it.
  if (/^https?:\/\//i.test(raw)) return raw;

  // Otherwise it's a relative path within the shop frontend.
  return raw;
}

function showBrandIntro() {
  let force = false;
  try {
    const q = new URL(window.location.href).searchParams;
    force = q.get('intro') === '1';
  } catch {
  }

  try {
    if (sessionStorage.getItem('gc_force_brand_intro_shop') === '1') {
      force = true;
      sessionStorage.removeItem('gc_force_brand_intro_shop');
    }
  } catch {
  }

  try {
    if (!force && sessionStorage.getItem('gc_brand_intro_shop') === '1') return;
    sessionStorage.setItem('gc_brand_intro_shop', '1');
  } catch {
  }

  let welcome = 'Welcome';
  try {
    const cust = getCustomer();
    if (cust && (cust.display_name || cust.email)) {
      welcome = `Welcome, ${cust.display_name || cust.email}`;
    }
  } catch {
  }

  const existing = document.querySelector('.gc-brand-intro');
  if (existing) {
    const sub = existing.querySelector('.gc-brand-sub');
    if (sub) sub.textContent = welcome;
    return;
  }

  const overlay = document.createElement('div');
  overlay.className = 'gc-brand-intro';

  overlay.innerHTML = `<div class="gc-brand-stack"><div class="gc-brand-word">G<span class="gc-brand-expand">lobal</span>SCART</div><div class="gc-brand-sub">${escapeHtml(welcome)}</div></div>`;
  overlay.addEventListener('animationend', (e) => {
    if (e && e.animationName === 'gc-brand-out') {
      overlay.remove();
    }
  });
  document.body.appendChild(overlay);
}

function renderConfetti(container, count = 26) {
  if (!container) return;
  container.innerHTML = '';
  const colors = ['#22c55e', '#3b82f6', '#a855f7', '#f59e0b', '#ef4444'];
  for (let i = 0; i < count; i += 1) {
    const s = document.createElement('span');
    const left = Math.random() * 100;
    const x = (Math.random() - 0.5) * 220;
    const r = 360 + Math.random() * 720;
    const d = 1100 + Math.random() * 900;
    const delay = Math.random() * 220;
    s.style.left = `${left}%`;
    s.style.background = colors[i % colors.length];
    s.style.setProperty('--x', `${x}px`);
    s.style.setProperty('--r', `${r}deg`);
    s.style.setProperty('--d', `${Math.round(d)}ms`);
    s.style.setProperty('--delay', `${Math.round(delay)}ms`);
    s.style.opacity = '0';
    container.appendChild(s);
  }
}

function fmtMoney(amount, currency = 'INR') {
  const v = Number(amount || 0);
  try {
    return new Intl.NumberFormat(undefined, { style: 'currency', currency }).format(v);
  } catch {
    return `${currency} ${v.toFixed(2)}`;
  }
}

function randId(len = 16) {
  const chars = 'abcdefghijklmnopqrstuvwxyz0123456789';
  let out = '';
  for (let i = 0; i < len; i++) out += chars[Math.floor(Math.random() * chars.length)];
  return out;
}

function setActiveNavLink() {
  const nav = document.querySelector('.navbar');
  if (!nav) return;

  let currentPath = '';
  try {
    const u = new URL(window.location.href);
    currentPath = u.pathname;
  } catch {
    return;
  }

  const links = Array.from(nav.querySelectorAll('a.nav-link'));
  if (!links.length) return;

  links.forEach((a) => a.classList.remove('active'));

  let best = null;
  for (const a of links) {
    const href = a.getAttribute('href') || '';
    if (!href || href.startsWith('#')) continue;
    try {
      const u = new URL(href, window.location.href);
      if (u.origin !== window.location.origin) continue;
      const p = u.pathname;
      if (!p) continue;
      if (p === currentPath) {
        best = a;
        break;
      }
      if (!best && currentPath.endsWith('/') && p.endsWith('/index.html') && currentPath === p.replace(/\/index\.html$/, '/')) {
        best = a;
      }
    } catch {
    }
  }

  if (best) best.classList.add('active');
}

function getSessionId() {
  let sid = localStorage.getItem(GC.storage.sessionId);
  if (!sid) {
    sid = `s_${randId(20)}`;
    localStorage.setItem(GC.storage.sessionId, sid);
  }
  return sid;
}

function getCustomer() {
  const raw = localStorage.getItem(GC.storage.customer);
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function setCustomer(customer) {
  if (!customer) {
    localStorage.removeItem(GC.storage.customer);
    return;
  }
  localStorage.setItem(GC.storage.customer, JSON.stringify(customer));
}

function loadCart() {
  const raw = localStorage.getItem(GC.storage.cart);
  if (!raw) return { items: [] };
  try {
    const c = JSON.parse(raw);
    if (!c || !Array.isArray(c.items)) return { items: [] };
    return c;
  } catch {
    return { items: [] };
  }
}

function saveCart(cart) {
  localStorage.setItem(GC.storage.cart, JSON.stringify(cart));
  updateNavCartCount();
}

function cartCount(cart = null) {
  const c = cart || loadCart();
  return (c.items || []).reduce((sum, it) => sum + Number(it.qty || 0), 0);
}

function addToCart(productId, qty) {
  const pid = Number(productId);
  const q = Math.max(1, Math.min(20, Number(qty || 1)));
  const cart = loadCart();
  const existing = cart.items.find((x) => Number(x.product_id) === pid);
  if (existing) existing.qty = Math.min(20, Number(existing.qty || 0) + q);
  else cart.items.push({ product_id: pid, qty: q });
  saveCart(cart);
  return cart;
}

function updateCartQty(productId, qty) {
  const pid = Number(productId);
  const q = Math.max(1, Math.min(20, Number(qty || 1)));
  const cart = loadCart();
  const existing = cart.items.find((x) => Number(x.product_id) === pid);
  if (existing) existing.qty = q;
  saveCart(cart);
  return cart;
}

function removeFromCart(productId) {
  const pid = Number(productId);
  const cart = loadCart();
  cart.items = cart.items.filter((x) => Number(x.product_id) !== pid);
  saveCart(cart);
  return cart;
}

class ApiError extends Error {
  constructor(message, status, data) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.data = data;
  }
}

async function apiFetch(url, options = {}) {
  let finalUrl = url;
  try {
    const isAbsolute = /^https?:\/\//i.test(String(url));
    if (!isAbsolute && String(url || '').startsWith('/') && window.location && window.location.port === '3000') {
      finalUrl = `${window.location.protocol}//${window.location.hostname}:8000${url}`;
    }
  } catch {
    // ignore
  }

  const resp = await fetch(finalUrl, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
  });
  const text = await resp.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }
  if (!resp.ok) {
    const msg = data && data.detail ? data.detail : `Request failed (${resp.status})`;
    throw new ApiError(msg, resp.status, data);
  }
  return data;
}

function _currentPagePathWithQuery() {
  let name = '';
  try {
    const p = window.location.pathname || '';
    // When served under /shop/, the pathname may be "/shop" or "/shop/".
    // In that case, ensure redirects use index.html instead of a non-existent "shop" path.
    if (p === '/shop' || p === '/shop/') {
      name = 'index.html';
    } else {
      name = p.split('/').filter(Boolean).pop() || '';
      if (name === 'shop') name = 'index.html';
    }
  } catch {
    name = '';
  }
  if (!name) name = 'index.html';
  return name + (window.location.search || '');
}

function requireCustomerOrRedirect() {
  const cust = getCustomer();
  if (cust) return true;
  const next = normalizeNext(_currentPagePathWithQuery());
  window.location.href = `login.html?reason=login_required&next=${encodeURIComponent(next)}`;
  return false;
}

async function track(stage, extra = {}) {
  const sid = getSessionId();
  const cust = getCustomer();
  const payload = {
    session_id: sid,
    stage,
    channel: 'WEB',
    device: /Mobi/i.test(navigator.userAgent) ? 'MOBILE' : 'DESKTOP',
    customer_id: cust ? cust.customer_id : null,
    product_id: null,
    order_id: null,
    failure_reason: null,
    ...extra,
  };

  try {
    await apiFetch(GC.api.funnelEvent, { method: 'POST', body: JSON.stringify(payload) });
  } catch {
    // swallow analytics failures
  }
}

function ensureToastHost() {
  let host = qs('#gcToastHost');
  if (!host) {
    host = document.createElement('div');
    host.id = 'gcToastHost';
    host.className = 'toast-container position-fixed bottom-0 end-0 p-3 gc-toast';
    document.body.appendChild(host);
  }
  return host;
}

function toast(title, message, variant = 'primary') {
  const host = ensureToastHost();
  const el = document.createElement('div');
  el.className = 'toast align-items-center text-bg-' + variant + ' border-0';
  el.setAttribute('role', 'alert');
  el.setAttribute('aria-live', 'assertive');
  el.setAttribute('aria-atomic', 'true');
  el.innerHTML = `
    <div class="d-flex">
      <div class="toast-body">
        <div class="fw-semibold">${escapeHtml(title)}</div>
        <div class="small opacity-75">${escapeHtml(message)}</div>
      </div>
      <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
    </div>
  `;
  host.appendChild(el);
  const t = bootstrap.Toast.getOrCreateInstance(el, { delay: 2600 });
  t.show();
  el.addEventListener('hidden.bs.toast', () => el.remove());
}

function ensureCancelReasonModal() {
  let modalEl = qs('#gcCancelReasonModal');
  if (!modalEl) {
    modalEl = document.createElement('div');
    modalEl.className = 'modal fade';
    modalEl.id = 'gcCancelReasonModal';
    modalEl.tabIndex = -1;
    modalEl.setAttribute('aria-hidden', 'true');
    const opts = GC_CANCEL_REASON_OPTIONS
      .map((t) => `<option value="${escapeHtml(t)}">${escapeHtml(t)}</option>`)
      .join('');
    modalEl.innerHTML = `
      <div class="modal-dialog modal-dialog-centered">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">Cancel order</h5>
            <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
          </div>
          <div class="modal-body">
            <div class="mb-2 fw-semibold">Reason for cancellation</div>
            <select class="form-select" id="gcCancelReasonSelect" aria-label="Select cancellation reason">
              <option value="">Select cancellation reason</option>
              ${opts}
            </select>
            <div class="mt-3 d-none" id="gcCancelOtherWrap">
              <div class="mb-1">Other reason</div>
              <input class="form-control" id="gcCancelOtherInput" type="text" placeholder="Type your reason" />
            </div>
            <div class="small text-secondary mt-2">A reason is required to cancel.</div>
          </div>
          <div class="modal-footer">
            <button type="button" class="btn btn-outline-secondary" data-bs-dismiss="modal">Back</button>
            <button type="button" class="btn btn-danger" id="gcCancelReasonConfirm">Confirm cancellation</button>
          </div>
        </div>
      </div>
    `;
    document.body.appendChild(modalEl);
  }
  return modalEl;
}

async function pickCancellationReason() {
  const modalEl = ensureCancelReasonModal();
  const selectEl = qs('#gcCancelReasonSelect', modalEl);
  const otherWrap = qs('#gcCancelOtherWrap', modalEl);
  const otherInput = qs('#gcCancelOtherInput', modalEl);
  const confirmBtn = qs('#gcCancelReasonConfirm', modalEl);

  if (!selectEl || !otherWrap || !otherInput || !confirmBtn || !window.bootstrap) {
    const fallback = String(prompt('Why are you cancelling this order? (Required)') || '').trim();
    return fallback || null;
  }

  selectEl.classList.remove('is-invalid');
  selectEl.value = '';
  otherInput.value = '';
  otherWrap.classList.add('d-none');

  const modal = bootstrap.Modal.getOrCreateInstance(modalEl);

  return new Promise((resolve) => {
    let settled = false;

    const cleanup = () => {
      selectEl.removeEventListener('change', onChange);
      confirmBtn.removeEventListener('click', onConfirm);
      modalEl.removeEventListener('hidden.bs.modal', onHidden);
    };

    const onHidden = () => {
      if (settled) return;
      settled = true;
      cleanup();
      resolve(null);
    };

    const onChange = () => {
      selectEl.classList.remove('is-invalid');
      const val = String(selectEl.value || '');
      if (val === 'Other') otherWrap.classList.remove('d-none');
      else otherWrap.classList.add('d-none');
    };

    const onConfirm = () => {
      const selected = String(selectEl.value || '').trim();
      if (!selected) {
        selectEl.classList.add('is-invalid');
        return;
      }
      let reason = selected;
      if (selected === 'Other') {
        const extra = String(otherInput.value || '').trim();
        if (!extra) {
          otherInput.focus();
          return;
        }
        reason = `Other: ${extra}`;
      }
      if (settled) return;
      settled = true;
      cleanup();
      modal.hide();
      resolve(reason);
    };

    modalEl.addEventListener('hidden.bs.modal', onHidden);
    selectEl.addEventListener('change', onChange);
    confirmBtn.addEventListener('click', onConfirm);
    modal.show();
  });
}

function updateNavCustomer() {
  const cust = getCustomer();
  const label = qs('#navCustomerLabel');
  const signOut = qs('#navSignOut');
  const signInLink = qs('#navSignInLink');
  const email = cust && cust.email ? String(cust.email) : '';
  const name = cust && cust.display_name ? String(cust.display_name) : '';
  const masked = email && email.includes('@') ? `${email.slice(0, 3)}***@${email.split('@')[1]}` : email;
  if (label) label.textContent = cust ? `${name || masked || 'Customer'} (#${cust.customer_id})` : 'Guest';
  if (signOut) signOut.classList.toggle('d-none', !cust);
  if (signInLink) signInLink.classList.toggle('d-none', !!cust);
}

function updateNavCartCount() {
  const n = cartCount();
  qsa('[data-cart-count]').forEach((el) => {
    el.textContent = String(n);
  });
}

function updateNavWishlistCount(n) {
  const count = Number.isFinite(Number(n)) ? Number(n) : 0;
  qsa('[data-wishlist-count]').forEach((el) => {
    el.textContent = String(count);
  });
}

function gotoLoginWithEmail(email) {
  const u = new URL('login.html', window.location.href);
  const e = String(email || '').trim();
  if (e) u.searchParams.set('email', e);
  u.searchParams.set('next', normalizeNext(window.location.pathname.split('/').pop() || 'index.html'));
  window.location.href = u.toString();
}

async function fetchWishlistIds() {
  const cust = getCustomer();
  if (!cust) return new Set();
  try {
    const items = await apiFetch(`${GC.api.wishlist}?customer_id=${encodeURIComponent(cust.customer_id)}`);
    const set = new Set();
    (Array.isArray(items) ? items : []).forEach((p) => set.add(Number(p.product_id)));
    return set;
  } catch {
    return new Set();
  }
}

async function toggleWishlist(productId, shouldAdd) {
  const cust = getCustomer();
  if (!cust) {
    toast('Sign in required', 'Please sign in to use wishlist.', 'warning');
    goToLogin();
    return false;
  }
  const pid = Number(productId);
  const url = `${GC.api.wishlistItem(pid)}?customer_id=${encodeURIComponent(cust.customer_id)}`;
  await apiFetch(url, { method: shouldAdd ? 'POST' : 'DELETE' });
  return true;
}

async function requestOtp(email) {
  const e = String(email || '').trim().toLowerCase();
  if (!e) throw new Error('Email is required');
  return apiFetch(GC.api.requestOtp, { method: 'POST', body: JSON.stringify({ email: e }) });
}

async function verifyOtp(email, otp) {
  const e = String(email || '').trim().toLowerCase();
  const o = String(otp || '').trim();
  if (!e) throw new Error('Email is required');
  if (!o) throw new Error('OTP is required');
  return apiFetch(GC.api.verifyOtp, { method: 'POST', body: JSON.stringify({ email: e, otp: o }) });
}

async function signupRequestOtp(displayName, email, password) {
  const n = String(displayName || '').trim();
  const e = String(email || '').trim().toLowerCase();
  const p = String(password || '');
  if (!n) throw new Error('Name is required');
  if (!e) throw new Error('Email is required');
  if (!p) throw new Error('Password is required');
  return apiFetch(GC.api.signupRequestOtp, {
    method: 'POST',
    body: JSON.stringify({ display_name: n, email: e, password: p }),
  });
}

async function signupVerifyOtp(email, otp) {
  const e = String(email || '').trim().toLowerCase();
  const o = String(otp || '').trim();
  if (!e) throw new Error('Email is required');
  if (!o) throw new Error('OTP is required');
  return apiFetch(GC.api.signupVerifyOtp, { method: 'POST', body: JSON.stringify({ email: e, otp: o }) });
}

async function loginWithPassword(email, password) {
  const e = String(email || '').trim().toLowerCase();
  const p = String(password || '');
  if (!e) throw new Error('Email is required');
  if (!p) throw new Error('Password is required');
  return apiFetch(GC.api.login, { method: 'POST', body: JSON.stringify({ email: e, password: p }) });
}

function bindGlobalNav() {
  getSessionId();
  updateNavCustomer();
  updateNavCartCount();
  fetchWishlistIds().then((set) => updateNavWishlistCount(set.size)).catch(() => updateNavWishlistCount(0));

  const legacyBtn = qs('#navSignIn');
  const legacyEmail = qs('#navEmail');
  if (legacyBtn && legacyEmail) {
    legacyBtn.addEventListener('click', () => goToLogin(legacyEmail.value));
  }

  const out = qs('#navSignOut');
  if (out) {
    out.addEventListener('click', () => {
      setCustomer(null);
      updateNavCustomer();
      toast('Signed out', 'Browsing as guest.', 'secondary');
    });
  }
}

async function initLogin() {
  const signupTab = qs('#signupTab');
  const loginTab = qs('#loginTab');
  const signupBox = qs('#signupBox');
  const loginBox = qs('#loginBox');
  const loginStage = qs('#gcLoginStage');

  const loginMascot = qs('#gcLoginMascot');

  const nameInput = qs('#nameInput');
  const signupEmailInput = qs('#signupEmailInput');
  const signupPasswordInput = qs('#signupPasswordInput');
  const signupConfirmPasswordInput = qs('#signupConfirmPasswordInput');
  const signupSendOtpBtn = qs('#signupSendOtpBtn');
  const signupOtpSection = qs('#signupOtpSection');
  const signupOtpInput = qs('#signupOtpInput');
  const signupOtpHint = qs('#signupOtpHint');
  const signupVerifyOtpBtn = qs('#signupVerifyOtpBtn');
  const signupResendOtpBtn = qs('#signupResendOtpBtn');
  const signupError = qs('#signupError');
  const signupEmailExistsWarn = qs('#signupEmailExistsWarn');

  let emailTaken = false;

  const pwdRuleLen = qs('#pwdRuleLen');
  const pwdRuleUpper = qs('#pwdRuleUpper');
  const pwdRuleNum = qs('#pwdRuleNum');
  const pwdRuleSpecial = qs('#pwdRuleSpecial');
  const pwdStrengthBar = qs('#pwdStrengthBar');
  const pwdMatchHint = qs('#pwdMatchHint');

  // Login OTP functionality
  const loginEmailInput = qs('#loginEmailInput');
  const loginPasswordInput = qs('#loginPasswordInput');
  const loginShowPasswordBtn = qs('#loginShowPasswordBtn');
  const loginRequestOtpBtn = qs('#loginRequestOtpBtn');
  const loginBackToPasswordBtn = qs('#loginBackToPasswordBtn');
  const loginUseOtpBtn = qs('#loginUseOtpBtn');
  const loginOtpSection = qs('#loginOtpSection');
  const loginOtpInput = qs('#loginOtpInput');
  const loginOtpHint = qs('#loginOtpHint');
  const loginResendOtpBtn = qs('#loginResendOtpBtn');
  const loginError = qs('#loginError');
  const loginBtn = qs('#loginBtn');
  const loginVerifyOtpBtn = qs('#loginVerifyOtpBtn');

  const q = new URL(window.location.href).searchParams;
  const next = normalizeNext(q.get('next') || 'index.html');
  const presetEmail = q.get('email') || '';
  if (signupEmailInput && presetEmail) signupEmailInput.value = presetEmail;
  if (loginEmailInput && presetEmail) loginEmailInput.value = presetEmail;

  if (q.get('reason') === 'login_required') {
    showErr(loginError, 'Sign in required to continue');
  }

  let mascotTargetEl = null;
  let mascotPrivacy = false;
  let mascotMouseX = window.innerWidth / 2;
  let mascotMouseY = window.innerHeight / 2;
  let mascotRaf = null;
  let mascotShakeTimer = null;

  function applyPrivacyEyes() {
    if (!loginMascot) return;
    const eyes = loginMascot.querySelectorAll('.gc-mascot-eye');
    eyes.forEach((eye) => {
      const pupil = eye.querySelector('.gc-mascot-pupil');
      if (!pupil) return;
      const eyeW = eye.clientWidth;
      const pupilW = pupil.offsetWidth;
      const maxX = Math.max(0, (eyeW - pupilW) / 2);
      pupil.style.transform = `translate3d(${-maxX}px, 0px, 0)`;
    });
  }

  function setMascotMode(mode) {
    if (!loginMascot) return;
    loginMascot.classList.toggle('gc-mascot-focus-email', mode === 'email');
    loginMascot.classList.toggle('gc-mascot-focus-password', mode === 'password');
  }

  function shakeMascot() {
    if (!loginMascot) return;
    loginMascot.classList.remove('gc-mascot-shake');
    // Force reflow so repeated shakes always play
    void loginMascot.offsetWidth;
    loginMascot.classList.add('gc-mascot-shake');
    if (mascotShakeTimer) clearTimeout(mascotShakeTimer);
    mascotShakeTimer = setTimeout(() => {
      loginMascot.classList.remove('gc-mascot-shake');
    }, 650);
  }

  function setMascotPrivacy(on) {
    mascotPrivacy = !!on;
    if (!loginMascot) return;
    loginMascot.classList.toggle('gc-mascot-privacy', mascotPrivacy);
    if (mascotPrivacy) {
      applyPrivacyEyes();
      if (mascotRaf) cancelAnimationFrame(mascotRaf);
      mascotRaf = null;
      loginMascot.classList.remove('gc-mascot-privacy-anim');
      void loginMascot.offsetWidth;
      loginMascot.classList.add('gc-mascot-privacy-anim');
      window.setTimeout(() => {
        if (loginMascot) loginMascot.classList.remove('gc-mascot-privacy-anim');
      }, 780);
    } else {
      loginMascot.classList.remove('gc-mascot-privacy-anim');
      if (!mascotRaf) mascotRaf = requestAnimationFrame(mascotTick);
    }
  }

  function setMascotTarget(el, mode) {
    mascotTargetEl = el || null;
    setMascotMode(mode || '');
  }

  function mascotTargetPoint() {
    if (mascotPrivacy) return null;
    if (mascotTargetEl && typeof mascotTargetEl.getBoundingClientRect === 'function') {
      const r = mascotTargetEl.getBoundingClientRect();
      return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
    }
    return { x: mascotMouseX, y: mascotMouseY };
  }

  function mascotTick() {
    if (!loginMascot) return;
    const pt = mascotTargetPoint();
    const eyes = loginMascot.querySelectorAll('.gc-mascot-eye');
    eyes.forEach((eye) => {
      const pupil = eye.querySelector('.gc-mascot-pupil');
      if (!pupil) return;
      const r = eye.getBoundingClientRect();
      const cx = r.left + r.width / 2;
      const cy = r.top + r.height / 2;
      let dx = 0;
      let dy = 0;
      if (!pt) {
        // Privacy mode: intentionally look away from the password field.
        // (Login form is on the right, mascot is on the left → look left.)
        const eyeW = eye.clientWidth || r.width;
        const pupilW = pupil.offsetWidth || pupil.getBoundingClientRect().width;
        const maxX = Math.max(0, (eyeW - pupilW) / 2);
        dx = -maxX;
        dy = 0;
      } else {
        dx = pt.x - cx;
        dy = pt.y - cy;
        const dist = Math.hypot(dx, dy) || 1;
        const max = r.width * 0.26;
        const amt = Math.min(max, dist * 0.06);
        dx = (dx / dist) * amt;
        dy = (dy / dist) * amt;
      }
      pupil.style.transform = `translate3d(${dx}px, ${dy}px, 0)`;
    });
    if (!mascotPrivacy) mascotRaf = requestAnimationFrame(mascotTick);
  }

  if (loginMascot) {
    window.addEventListener('mousemove', (ev) => {
      mascotMouseX = ev.clientX;
      mascotMouseY = ev.clientY;
    });
    mascotRaf = requestAnimationFrame(mascotTick);
  }

  function setMode(mode) {
    if (signupBox) signupBox.classList.toggle('d-none', mode !== 'signup');
    if (loginBox) loginBox.classList.toggle('d-none', mode !== 'login');
    if (signupTab) signupTab.setAttribute('aria-pressed', String(mode === 'signup'));
    if (loginTab) loginTab.setAttribute('aria-pressed', String(mode === 'login'));

    if (loginMascot) loginMascot.classList.toggle('d-none', mode !== 'login');
    if (loginStage) loginStage.classList.toggle('gc-login-stage--solo', mode !== 'login');
    if (mode !== 'login') {
      setMascotPrivacy(false);
      setMascotTarget(null, '');
    }
  }

  setMode(q.get('mode') === 'login' ? 'login' : 'signup');

  if (loginRequestOtpBtn) {
    loginRequestOtpBtn.addEventListener('click', async () => {
      const email = loginEmailInput ? loginEmailInput.value : '';
      if (!email) {
        showErr(loginError, 'Email is required');
        return;
      }

      if (loginRequestOtpBtn) loginRequestOtpBtn.disabled = true;
      try {
        const res = await requestOtp(email);
        showOtpUi(loginOtpSection, loginOtpHint, res && res.demo_otp ? String(res.demo_otp) : '');
        if (loginPasswordInput) loginPasswordInput.closest('.mt-3').classList.add('d-none');
        if (loginBtn) loginBtn.classList.add('d-none');
        if (loginRequestOtpBtn) loginRequestOtpBtn.classList.add('d-none');
        if (loginBackToPasswordBtn) loginBackToPasswordBtn.classList.remove('d-none');
        if (loginUseOtpBtn) loginUseOtpBtn.classList.add('d-none');
        toast('OTP sent', 'Enter the code to sign in.', 'primary');
        if (loginOtpInput) loginOtpInput.focus();
      } catch (e) {
        showErr(loginError, e.message || 'Failed to send OTP');
      } finally {
        if (loginRequestOtpBtn) loginRequestOtpBtn.disabled = false;
      }
    });
  }

  if (loginBackToPasswordBtn) {
    loginBackToPasswordBtn.addEventListener('click', () => {
      if (loginPasswordInput) loginPasswordInput.closest('.mt-3').classList.remove('d-none');
      if (loginOtpSection) loginOtpSection.classList.add('d-none');
      if (loginRequestOtpBtn) loginRequestOtpBtn.classList.add('d-none');
      if (loginBtn) loginBtn.classList.remove('d-none');
      if (loginBackToPasswordBtn) loginBackToPasswordBtn.classList.add('d-none');
      if (loginUseOtpBtn) loginUseOtpBtn.classList.remove('d-none');
      setMascotPrivacy(false);
      clearErr(loginError);
    });
  }

  if (loginUseOtpBtn) {
    loginUseOtpBtn.addEventListener('click', () => {
      if (loginPasswordInput) loginPasswordInput.closest('.mt-3').classList.add('d-none');
      if (loginBtn) loginBtn.classList.add('d-none');
      if (loginOtpSection) loginOtpSection.classList.add('d-none');
      if (loginRequestOtpBtn) loginRequestOtpBtn.classList.remove('d-none');
      if (loginBackToPasswordBtn) loginBackToPasswordBtn.classList.remove('d-none');
      if (loginUseOtpBtn) loginUseOtpBtn.classList.add('d-none');
      setMascotPrivacy(false);
      setMascotTarget(null, '');
      clearErr(loginError);
    });
  }

  if (loginEmailInput) {
    loginEmailInput.addEventListener('focus', () => setMascotTarget(loginEmailInput, 'email'));
    loginEmailInput.addEventListener('blur', () => setMascotTarget(null, ''));
    loginEmailInput.addEventListener('input', () => setMascotTarget(loginEmailInput, 'email'));
  }

  if (loginPasswordInput) {
    loginPasswordInput.addEventListener('focus', () => setMascotTarget(loginPasswordInput, 'password'));
    loginPasswordInput.addEventListener('blur', () => setMascotTarget(null, ''));
    loginPasswordInput.addEventListener('input', () => setMascotTarget(loginPasswordInput, 'password'));
  }

  if (loginShowPasswordBtn && loginPasswordInput) {
    loginShowPasswordBtn.addEventListener('click', () => {
      const showing = loginPasswordInput.type === 'text';
      loginPasswordInput.type = showing ? 'password' : 'text';
      loginShowPasswordBtn.textContent = showing ? 'Show' : 'Hide';
      loginShowPasswordBtn.setAttribute('aria-pressed', String(!showing));
      setMascotPrivacy(!showing);
    });
  }

  if (loginVerifyOtpBtn) {
    loginVerifyOtpBtn.addEventListener('click', async () => {
      const email = loginEmailInput ? loginEmailInput.value : '';
      const otp = loginOtpInput ? loginOtpInput.value : '';
      if (!email || !otp) {
        showErr(loginError, 'Email and OTP are required');
        return;
      }

      if (loginVerifyOtpBtn) loginVerifyOtpBtn.disabled = true;
      try {
        const customer = await verifyOtp(email, otp);
        setCustomer(customer);
        toast('Signed in', `Welcome back!`, 'success');
        window.location.href = withIntroParam(next);
      } catch (e) {
        showErr(loginError, e.message || 'Invalid OTP');
      } finally {
        if (loginVerifyOtpBtn) loginVerifyOtpBtn.disabled = false;
      }
    });
  }

  if (loginResendOtpBtn) {
    loginResendOtpBtn.addEventListener('click', async () => {
      const email = loginEmailInput ? loginEmailInput.value : '';
      if (!email) {
        showErr(loginError, 'Email is required');
        return;
      }

      if (loginResendOtpBtn) loginResendOtpBtn.disabled = true;
      try {
        const res = await requestOtp(email);
        showOtpUi(loginOtpSection, loginOtpHint, res && res.demo_otp ? String(res.demo_otp) : '');
        toast('OTP resent', 'Check your email for the new code.', 'primary');
        if (loginOtpInput) {
          loginOtpInput.value = '';
          loginOtpInput.focus();
        }
      } catch (e) {
        showErr(loginError, e.message || 'Failed to resend OTP');
      } finally {
        if (loginResendOtpBtn) loginResendOtpBtn.disabled = false;
      }
    });
  }

  // Original password login (if needed)
  if (loginBtn) {
    loginBtn.addEventListener('click', async () => {
      const email = loginEmailInput ? loginEmailInput.value : '';
      const password = loginPasswordInput ? loginPasswordInput.value : '';
      if (!email || !password) {
        showErr(loginError, 'Email and password are required');
        return;
      }

      if (loginBtn) loginBtn.disabled = true;
      try {
        const customer = await loginWithPassword(email, password);
        setCustomer(customer);
        toast('Signed in', `Welcome back!`, 'success');
        window.location.href = withIntroParam(next);
      } catch (e) {
        showErr(loginError, e.message || 'Invalid credentials');
        shakeMascot();
      } finally {
        if (loginBtn) loginBtn.disabled = false;
      }
    });
  }

  function showErr(box, msg) {
    if (!box) return;
    box.textContent = msg;
    box.classList.remove('d-none');
  }
  function clearErr(box) {
    if (!box) return;
    box.classList.add('d-none');
    box.textContent = '';
  }
  function showOtpUi(section, hintEl, demoOtp) {
    if (section) section.classList.remove('d-none');
    if (hintEl) hintEl.textContent = demoOtp ? `Demo OTP: ${demoOtp}` : '';
  }

  getSessionId();

  function passwordRules(password) {
    const p = String(password || '');
    return {
      len: p.length >= 7,
      upper: /[A-Z]/.test(p),
      num: /[0-9]/.test(p),
      special: /[^A-Za-z0-9]/.test(p),
    };
  }

  function updatePasswordUi() {
    const p1 = signupPasswordInput ? signupPasswordInput.value : '';
    const p2 = signupConfirmPasswordInput ? signupConfirmPasswordInput.value : '';
    const r = passwordRules(p1);
    const okCount = [r.len, r.upper, r.num, r.special].filter(Boolean).length;
    const pct = Math.round((okCount / 4) * 100);

    function setRule(el, ok) {
      if (!el) return;
      el.classList.toggle('text-success', !!ok);
      el.classList.toggle('text-secondary', !ok);
    }

    setRule(pwdRuleLen, r.len);
    setRule(pwdRuleUpper, r.upper);
    setRule(pwdRuleNum, r.num);
    setRule(pwdRuleSpecial, r.special);

    if (pwdStrengthBar) {
      pwdStrengthBar.style.width = `${pct}%`;
      pwdStrengthBar.classList.remove('bg-danger', 'bg-warning', 'bg-success');
      if (pct <= 25) pwdStrengthBar.classList.add('bg-danger');
      else if (pct <= 75) pwdStrengthBar.classList.add('bg-warning');
      else pwdStrengthBar.classList.add('bg-success');
    }

    const matches = p1 && p2 ? p1 === p2 : true;
    if (pwdMatchHint) pwdMatchHint.textContent = !matches ? 'Passwords do not match' : '';
    if (signupConfirmPasswordInput) {
      signupConfirmPasswordInput.classList.toggle('is-invalid', !matches);
      signupConfirmPasswordInput.classList.toggle('is-valid', matches && !!p2);
    }

    const allOk = r.len && r.upper && r.num && r.special && matches && !emailTaken;
    if (signupSendOtpBtn) signupSendOtpBtn.disabled = !allOk;
    return allOk;
  }

  async function refreshEmailTaken() {
    if (!signupEmailInput) return;
    const email = signupEmailInput.value;
    try {
      const res = await checkEmailExists(email);
      emailTaken = !!(res && res.exists);
      if (signupEmailExistsWarn) signupEmailExistsWarn.classList.toggle('d-none', !emailTaken);
    } catch {
      emailTaken = false;
      if (signupEmailExistsWarn) signupEmailExistsWarn.classList.add('d-none');
    }
    updatePasswordUi();
  }

  async function doSignupSend() {
    clearErr(signupError);

    const name = nameInput ? nameInput.value : '';
    const email = signupEmailInput ? signupEmailInput.value : '';
    const p1 = signupPasswordInput ? signupPasswordInput.value : '';
    const p2 = signupConfirmPasswordInput ? signupConfirmPasswordInput.value : '';

    const ok = updatePasswordUi();
    if (!ok) {
      showErr(
        signupError,
        'Password must be at least 7 characters and include 1 uppercase letter, 1 number, and 1 special character. Also confirm password must match.'
      );
      return;
    }

    if (signupSendOtpBtn) signupSendOtpBtn.disabled = true;
    try {
      const res = await signupRequestOtp(name, email, p1);
      showOtpUi(signupOtpSection, signupOtpHint, res && res.demo_otp ? String(res.demo_otp) : '');
      toast('OTP sent', 'Enter the code to verify and create your account.', 'primary');
      if (signupOtpInput) signupOtpInput.focus();
    } catch (e) {
      showErr(signupError, e.message || 'Failed to send OTP');
    } finally {
      if (signupSendOtpBtn) signupSendOtpBtn.disabled = false;
    }
  }

  async function doSignupVerify() {
    clearErr(signupError);
    const email = signupEmailInput ? signupEmailInput.value : '';
    const otp = signupOtpInput ? signupOtpInput.value : '';
    if (signupVerifyOtpBtn) signupVerifyOtpBtn.disabled = true;
    try {
      const data = await signupVerifyOtp(email, otp);
      setCustomer(data);
      toast('Account verified', `Welcome ${data.display_name || data.email}.`, 'success');
      window.location.href = withIntroParam(next);
    } catch (e) {
      showErr(signupError, e.message || 'OTP verification failed');
    } finally {
      if (signupVerifyOtpBtn) signupVerifyOtpBtn.disabled = false;
    }
  }

  async function doLogin() {
    clearErr(loginError);
    const email = loginEmailInput ? loginEmailInput.value : '';
    const password = loginPasswordInput ? loginPasswordInput.value : '';
    if (loginBtn) loginBtn.disabled = true;
    try {
      const data = await loginWithPassword(email, password);
      setCustomer(data);
      toast('Signed in', `Welcome ${data.display_name || data.email}.`, 'success');
      window.location.href = withIntroParam(next);
    } catch (e) {
      showErr(loginError, e.message || 'Login failed');
      shakeMascot();
    } finally {
      if (loginBtn) loginBtn.disabled = false;
    }
  }

  if (signupTab) signupTab.addEventListener('click', () => setMode('signup'));
  if (loginTab) loginTab.addEventListener('click', () => setMode('login'));

  if (signupSendOtpBtn) signupSendOtpBtn.addEventListener('click', doSignupSend);
  if (signupResendOtpBtn) signupResendOtpBtn.addEventListener('click', doSignupSend);
  if (signupVerifyOtpBtn) signupVerifyOtpBtn.addEventListener('click', doSignupVerify);

  if (loginBtn) loginBtn.addEventListener('click', doLogin);

  if (signupConfirmPasswordInput) {
    signupConfirmPasswordInput.addEventListener('keydown', (ev) => {
      if (ev.key === 'Enter') doSignupSend();
    });
  }

  if (signupPasswordInput) signupPasswordInput.addEventListener('input', updatePasswordUi);
  if (signupConfirmPasswordInput) signupConfirmPasswordInput.addEventListener('input', updatePasswordUi);
  if (signupEmailInput) {
    signupEmailInput.addEventListener('blur', refreshEmailTaken);
    signupEmailInput.addEventListener('change', refreshEmailTaken);
  }
  updatePasswordUi();
  if (signupOtpInput) {
    signupOtpInput.addEventListener('keydown', (ev) => {
      if (ev.key === 'Enter') doSignupVerify();
    });
  }
  if (loginPasswordInput) {
    loginPasswordInput.addEventListener('keydown', (ev) => {
      if (ev.key === 'Enter') doLogin();
    });
  }
}

const productCache = new Map();
async function fetchProduct(productId) {
  const pid = Number(productId);
  if (productCache.has(pid)) return productCache.get(pid);
  const p = await apiFetch(GC.api.product(pid));
  productCache.set(pid, p);
  return p;
}

async function fetchProducts(params) {
  const usp = new URLSearchParams();
  Object.entries(params || {}).forEach(([k, v]) => {
    if (v === undefined || v === null || v === '') return;
    usp.set(k, String(v));
  });
  const url = usp.toString() ? `${GC.api.products}?${usp.toString()}` : GC.api.products;
  return apiFetch(url);
}

function readQuery() {
  return new URL(window.location.href).searchParams;
}

function setQuery(next) {
  const u = new URL(window.location.href);
  Object.entries(next).forEach(([k, v]) => {
    if (v === null || v === undefined || v === '') u.searchParams.delete(k);
    else u.searchParams.set(k, String(v));
  });
  window.history.replaceState({}, '', u.toString());
}

function renderSkeletonGrid(grid, n = 8) {
  if (!grid) return;
  grid.innerHTML = '';
  for (let i = 0; i < n; i++) {
    const col = document.createElement('div');
    col.className = 'col-12 col-sm-6 col-lg-4 col-xl-3';
    col.innerHTML = `
      <div class="card h-100 shadow-sm">
        <div class="gc-skeleton" style="aspect-ratio: 1/1;"></div>
        <div class="card-body">
          <div class="gc-skeleton rounded" style="height: 14px; width: 80%;"></div>
          <div class="gc-skeleton rounded mt-2" style="height: 12px; width: 55%;"></div>
          <div class="gc-skeleton rounded mt-3" style="height: 16px; width: 40%;"></div>
        </div>
      </div>
    `;
    grid.appendChild(col);
  }
}

async function initHome() {
  bindGlobalNav();

  initHomeScrollFx();

  const grid = qs('#productGrid');
  const loadMore = qs('#loadMoreBtn');
  const sortSel = qs('#sortSelect');
  const cat1Sel = qs('#cat1Select');
  const cat2Sel = qs('#cat2Select');
  const brandSel = qs('#brandSelect');
  const minPriceInput = qs('#minPriceInput');
  const maxPriceInput = qs('#maxPriceInput');
  const searchInp = qs('#searchInput');
  const resultsCountEl = qs('#resultsCount');
  const clearFiltersBtn = qs('#clearFiltersBtn');

  let offset = 0;
  const limit = 24;
  let all = [];
  let wishlistIds = await fetchWishlistIds();

  updateNavWishlistCount(wishlistIds.size);

  initHomeProductReveal(grid);

  function readClientFilters() {
    const q = searchInp && searchInp.value ? searchInp.value.trim().toLowerCase() : '';
    const brand = brandSel && brandSel.value ? String(brandSel.value) : '';
    const min = minPriceInput && minPriceInput.value !== '' ? Number(minPriceInput.value) : null;
    const max = maxPriceInput && maxPriceInput.value !== '' ? Number(maxPriceInput.value) : null;
    return {
      q,
      brand,
      minPrice: Number.isFinite(min) ? min : null,
      maxPrice: Number.isFinite(max) ? max : null,
    };
  }

  function applyClientFilters(items) {
    const f = readClientFilters();
    return (Array.isArray(items) ? items : []).filter((p) => {
      const nameOk = !f.q || String(p.product_name || '').toLowerCase().includes(f.q);
      if (!nameOk) return false;
      const brandOk = !f.brand || String(p.brand || '') === f.brand;
      if (!brandOk) return false;
      const price = Number(p.sell_price);
      if (Number.isFinite(f.minPrice) && !(Number.isFinite(price) && price >= f.minPrice)) return false;
      if (Number.isFinite(f.maxPrice) && !(Number.isFinite(price) && price <= f.maxPrice)) return false;
      return true;
    });
  }

  function syncQueryFromUi() {
    const f = readClientFilters();
    setQuery({
      sort: sortSel ? sortSel.value : 'default',
      category_l1: cat1Sel ? cat1Sel.value : '',
      category_l2: cat2Sel ? cat2Sel.value : '',
      brand: f.brand,
      min_price: f.minPrice === null ? '' : f.minPrice,
      max_price: f.maxPrice === null ? '' : f.maxPrice,
      q: f.q,
    });
  }

  function render(items, append = false) {
    if (!grid) return;
    if (!append) grid.innerHTML = '';

    const view = applyClientFilters(items);
    if (resultsCountEl) {
      resultsCountEl.textContent = '';
    }

    if (!view.length) {
      grid.innerHTML = '<div class="col-12"><div class="text-secondary">No products match your filters.</div></div>';
      return;
    }

    for (const p of view) {
      const col = document.createElement('div');
      col.className = 'col-12 col-sm-6 col-lg-4 col-xl-3 gc-reveal';
      const price = fmtMoney(p.sell_price, 'INR');
      const list = fmtMoney(p.list_price, 'INR');
      const wished = wishlistIds.has(Number(p.product_id));
      col.innerHTML = `
        <div class="card h-100 shadow-sm">
          <a href="product.html?product_id=${encodeURIComponent(p.product_id)}" class="text-decoration-none text-reset">
            <img loading="lazy" class="card-img-top gc-card-img" src="${escapeHtml(p.image_url)}" alt="${escapeHtml(p.product_name)}" />
            <div class="card-body">
              <div class="fw-semibold">${escapeHtml(p.product_name)}</div>
              <div class="small text-secondary">${escapeHtml(p.brand)} · ${escapeHtml(p.category_l2)}</div>
              <div class="mt-2">
                <span class="gc-price">${escapeHtml(price)}</span>
                <span class="text-secondary text-decoration-line-through small ms-2">${escapeHtml(list)}</span>
              </div>
              <div class="mt-2">
                <span class="badge text-bg-success-subtle border border-success-subtle">-${escapeHtml(p.discount_pct)}%</span>
              </div>
            </div>
          </a>
          <div class="card-footer bg-white border-0 pt-0">
            <div class="d-flex gap-2">
              <button class="btn btn-sm btn-primary flex-fill" data-add="${escapeHtml(p.product_id)}">Add to cart</button>
              <button class="btn btn-sm ${wished ? 'btn-outline-danger' : 'btn-outline-secondary'}" data-wish="${escapeHtml(p.product_id)}" type="button">${wished ? 'Saved' : 'Wishlist'}</button>
            </div>
          </div>
        </div>
      `;
      grid.appendChild(col);
    }

    qsa('[data-add]', grid).forEach((btn) => {
      btn.addEventListener('click', async (e) => {
        e.preventDefault();
        const pid = btn.getAttribute('data-add');
        addToCart(pid, 1);
        toast('Added to cart', '1 item added.', 'success');
        await track('ADD_TO_CART', { product_id: Number(pid) });
      });
    });

    qsa('[data-wish]', grid).forEach((btn) => {
      btn.addEventListener('click', async (e) => {
        e.preventDefault();
        const pid = btn.getAttribute('data-wish');
        const already = wishlistIds.has(Number(pid));
        try {
          const ok = await toggleWishlist(pid, !already);
          if (!ok) return;
          if (already) {
            wishlistIds.delete(Number(pid));
            toast('Removed', 'Removed from wishlist.', 'secondary');
          } else {
            wishlistIds.add(Number(pid));
            toast('Saved', 'Added to wishlist.', 'success');
          }
          updateNavWishlistCount(wishlistIds.size);
          render(all, false);
        } catch (err) {
          toast('Wishlist failed', err.message || 'Unable to update wishlist', 'danger');
        }
      });
    });
  }

  async function loadCategories() {
    try {
      const sample = await fetchProducts({ limit: 200, offset: 0 });
      const l1 = Array.from(new Set(sample.map((p) => p.category_l1))).sort();
      if (cat1Sel) {
        cat1Sel.innerHTML = '<option value="">All categories</option>' + l1.map((c) => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`).join('');
      }

      const brands = Array.from(new Set(sample.map((p) => p.brand).filter(Boolean))).sort();
      if (brandSel) {
        brandSel.innerHTML = '<option value="">All brands</option>' + brands.map((b) => `<option value="${escapeHtml(b)}">${escapeHtml(b)}</option>`).join('');
      }
    } catch {
      // ignore
    }
  }

  async function load(reset = false) {
    if (reset) {
      offset = 0;
      all = [];
    }

    const params = {
      limit,
      offset,
      sort: sortSel ? sortSel.value : 'default',
      category_l1: cat1Sel ? cat1Sel.value : '',
      category_l2: cat2Sel ? cat2Sel.value : '',
    };

    syncQueryFromUi();

    if (offset === 0) renderSkeletonGrid(grid, 8);
    const items = await fetchProducts(params);
    all = all.concat(items);

    render(all, false);
    offset += items.length;
    if (loadMore) loadMore.disabled = items.length < limit;

    if (cat2Sel) {
      const l2 = Array.from(new Set(all.map((p) => p.category_l2))).sort();
      const current = cat2Sel.value;
      cat2Sel.innerHTML = '<option value="">All subcategories</option>' + l2.map((c) => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`).join('');
      if (current) cat2Sel.value = current;
    }

    if (brandSel) {
      const brands = Array.from(new Set(all.map((p) => p.brand).filter(Boolean))).sort();
      const current = brandSel.value;
      brandSel.innerHTML = '<option value="">All brands</option>' + brands.map((b) => `<option value="${escapeHtml(b)}">${escapeHtml(b)}</option>`).join('');
      if (current) brandSel.value = current;
    }
  }

  const q = readQuery();
  if (sortSel && q.get('sort')) sortSel.value = q.get('sort');

  await loadCategories();

  if (cat1Sel && q.get('category_l1')) cat1Sel.value = q.get('category_l1');
  if (cat2Sel && q.get('category_l2')) cat2Sel.value = q.get('category_l2');
  if (brandSel && q.get('brand')) brandSel.value = q.get('brand');
  if (minPriceInput && q.get('min_price')) minPriceInput.value = q.get('min_price');
  if (maxPriceInput && q.get('max_price')) maxPriceInput.value = q.get('max_price');
  if (searchInp && q.get('q')) searchInp.value = q.get('q');

  await load(true);

  if (loadMore) {
    loadMore.addEventListener('click', async () => {
      loadMore.disabled = true;
      try {
        await load(false);
      } catch (err) {
        toast('Load failed', err.message || 'Unable to load products', 'danger');
      } finally {
        loadMore.disabled = false;
      }
    });
  }

  [sortSel, cat1Sel, cat2Sel].filter(Boolean).forEach((el) => {
    el.addEventListener('change', async () => {
      try {
        await load(true);
      } catch (err) {
        toast('Load failed', err.message || 'Unable to load products', 'danger');
      }
    });
  });

  [brandSel].filter(Boolean).forEach((el) => {
    el.addEventListener('change', () => {
      syncQueryFromUi();
      render(all, false);
    });
  });

  [minPriceInput, maxPriceInput].filter(Boolean).forEach((el) => {
    el.addEventListener('input', () => {
      syncQueryFromUi();
      render(all, false);
    });
  });

  if (searchInp) {
    searchInp.addEventListener('input', () => {
      syncQueryFromUi();
      render(all, false);
    });
  }

  if (clearFiltersBtn) {
    clearFiltersBtn.addEventListener('click', async () => {
      if (searchInp) searchInp.value = '';
      if (brandSel) brandSel.value = '';
      if (minPriceInput) minPriceInput.value = '';
      if (maxPriceInput) maxPriceInput.value = '';
      if (cat1Sel) cat1Sel.value = '';
      if (cat2Sel) cat2Sel.value = '';
      if (sortSel) sortSel.value = 'default';

      try {
        await load(true);
      } catch (err) {
        toast('Load failed', err.message || 'Unable to load products', 'danger');
      }
    });
  }
}

async function initProduct() {
  bindGlobalNav();

  const q = readQuery();
  const productId = q.get('product_id');
  if (!productId) {
    toast('Missing product', 'No product_id in URL.', 'danger');
    return;
  }

  const title = qs('#productTitle');
  const img = qs('#productImg');
  const meta = qs('#productMeta');
  const price = qs('#productPrice');
  const list = qs('#productListPrice');
  const stock = qs('#productStock');
  const qty = qs('#qtyInput');
  const addBtn = qs('#addBtn');
  const wishBtn = qs('#wishlistBtn');
  const ratingSummary = qs('#productRatingSummary');
  const relatedHost = qs('#relatedProductsSection');
  const reviewsHost = qs('#productReviewsSection');

  try {
    const p = await fetchProduct(productId);
    if (title) title.textContent = p.product_name;
    if (img) {
      img.src = p.image_url;
      img.alt = p.product_name;
    }
    if (meta) meta.textContent = `${p.brand} · ${p.category_l1} / ${p.category_l2}`;
    if (price) price.textContent = fmtMoney(p.sell_price, 'INR');
    if (list) list.textContent = fmtMoney(p.list_price, 'INR');
    if (stock) stock.textContent = p.in_stock ? `In stock (${p.stock_qty})` : 'Out of stock';

    try {
      const rs = await apiFetch(GC.api.productRating(p.product_id));
      if (ratingSummary && rs) {
        const avg = Number(rs.average_rating || 0);
        const cnt = Number(rs.rating_count || 0);
        ratingSummary.textContent = cnt ? `Rating: ${avg.toFixed(1)} / 5 (${cnt})` : 'No ratings yet.';
      }
    } catch {
      if (ratingSummary) ratingSummary.textContent = '';
    }

    if (wishBtn) {
      const ids = await fetchWishlistIds();
      updateNavWishlistCount(ids.size);
      const wished = ids.has(Number(p.product_id));
      wishBtn.classList.toggle('btn-outline-danger', wished);
      wishBtn.classList.toggle('btn-outline-secondary', !wished);
      wishBtn.textContent = wished ? 'Saved' : 'Wishlist';
      wishBtn.addEventListener('click', async () => {
        const current = wishBtn.classList.contains('btn-outline-danger');
        try {
          const ok = await toggleWishlist(p.product_id, !current);
          if (!ok) return;
          if (current) ids.delete(Number(p.product_id));
          else ids.add(Number(p.product_id));
          wishBtn.classList.toggle('btn-outline-danger', !current);
          wishBtn.classList.toggle('btn-outline-secondary', current);
          wishBtn.textContent = !current ? 'Saved' : 'Wishlist';
          updateNavWishlistCount(ids.size);
        } catch (err) {
          toast('Wishlist failed', err.message || 'Unable to update wishlist', 'danger');
        }
      });
    }

    if (relatedHost) {
      relatedHost.innerHTML = `
        <div class="d-flex justify-content-between align-items-end">
          <div>
            <div class="h5 fw-semibold mb-1">Related products</div>
            <div class="text-secondary small">Similar items you might like.</div>
          </div>
          <a class="btn btn-sm btn-outline-secondary" href="index.html">Browse all</a>
        </div>
        <div class="row g-3 mt-2" id="relatedGrid"></div>
      `;

      const relatedGrid = qs('#relatedGrid', relatedHost);
      if (relatedGrid) {
        renderSkeletonGrid(relatedGrid, 4);
        const ids = await fetchWishlistIds();
        updateNavWishlistCount(ids.size);

        const wanted = new Map();
        function addBatch(arr) {
          (Array.isArray(arr) ? arr : []).forEach((it) => {
            const pid = Number(it.product_id);
            if (!pid || pid === Number(p.product_id)) return;
            if (!wanted.has(pid)) wanted.set(pid, it);
          });
        }

        try {
          addBatch(await fetchProducts({ limit: 80, offset: 0, category_l2: p.category_l2 }));
        } catch {
        }
        if (wanted.size < 8) {
          try {
            addBatch(await fetchProducts({ limit: 80, offset: 0, category_l1: p.category_l1 }));
          } catch {
          }
        }
        if (wanted.size < 8) {
          try {
            addBatch(await fetchProducts({ limit: 80, offset: 0, sort: 'best_sellers' }));
          } catch {
          }
        }

        const rel = Array.from(wanted.values()).slice(0, 8);
        if (!rel.length) {
          relatedGrid.innerHTML = '<div class="col-12"><div class="text-secondary">No related products found.</div></div>';
        } else {
          relatedGrid.innerHTML = '';
          for (const it of rel) {
            const col = document.createElement('div');
            col.className = 'col-12 col-sm-6 col-lg-3';
            const price = fmtMoney(it.sell_price, 'INR');
            const list = fmtMoney(it.list_price, 'INR');
            const wished = ids.has(Number(it.product_id));
            col.innerHTML = `
              <div class="card h-100 shadow-sm">
                <a href="product.html?product_id=${encodeURIComponent(it.product_id)}" class="text-decoration-none text-reset">
                  <img loading="lazy" class="card-img-top gc-card-img" src="${escapeHtml(it.image_url)}" alt="${escapeHtml(it.product_name)}" />
                  <div class="card-body">
                    <div class="fw-semibold">${escapeHtml(it.product_name)}</div>
                    <div class="small text-secondary">${escapeHtml(it.brand)} · ${escapeHtml(it.category_l2)}</div>
                    <div class="mt-2">
                      <span class="gc-price">${escapeHtml(price)}</span>
                      <span class="text-secondary text-decoration-line-through small ms-2">${escapeHtml(list)}</span>
                    </div>
                  </div>
                </a>
                <div class="card-footer bg-white border-0 pt-0">
                  <div class="d-flex gap-2">
                    <button class="btn btn-sm btn-primary flex-fill" data-rel-add="${escapeHtml(it.product_id)}" type="button">Add</button>
                    <button class="btn btn-sm ${wished ? 'btn-outline-danger' : 'btn-outline-secondary'}" data-rel-wish="${escapeHtml(it.product_id)}" type="button">${wished ? 'Saved' : 'Wish'}</button>
                  </div>
                </div>
              </div>
            `;
            relatedGrid.appendChild(col);
          }

          qsa('[data-rel-add]', relatedGrid).forEach((btn) => {
            btn.addEventListener('click', async (e) => {
              e.preventDefault();
              const pid = btn.getAttribute('data-rel-add');
              addToCart(pid, 1);
              toast('Added to cart', '1 item added.', 'success');
              await track('ADD_TO_CART', { product_id: Number(pid) });
            });
          });

          qsa('[data-rel-wish]', relatedGrid).forEach((btn) => {
            btn.addEventListener('click', async (e) => {
              e.preventDefault();
              const pid = btn.getAttribute('data-rel-wish');
              const already = ids.has(Number(pid));
              try {
                const ok = await toggleWishlist(pid, !already);
                if (!ok) return;
                if (already) ids.delete(Number(pid));
                else ids.add(Number(pid));
                btn.classList.toggle('btn-outline-danger', !already);
                btn.classList.toggle('btn-outline-secondary', already);
                btn.textContent = !already ? 'Saved' : 'Wish';
                updateNavWishlistCount(ids.size);
              } catch (err) {
                toast('Wishlist failed', err.message || 'Unable to update wishlist', 'danger');
              }
            });
          });
        }
      }
    }

    if (reviewsHost) {
      const cust = getCustomer();
      const canReview = !!cust;
      reviewsHost.innerHTML = `
        <div class="card shadow-sm">
          <div class="card-body">
            <div class="fw-semibold">Reviews</div>
            <div class="small text-secondary" id="reviewsHint">${canReview ? 'Checking eligibility…' : 'Sign in to write a review.'}</div>
            <div class="mt-3" id="reviewsList"></div>
            <div class="mt-4 ${canReview ? '' : 'd-none'}" id="reviewFormWrap">
              <div class="row g-2">
                <div class="col-md-3">
                  <label class="form-label">Rating</label>
                  <select class="form-select" id="reviewRating">
                    <option value="5">5</option>
                    <option value="4">4</option>
                    <option value="3">3</option>
                    <option value="2">2</option>
                    <option value="1">1</option>
                  </select>
                </div>
                <div class="col-md-9">
                  <label class="form-label">Title</label>
                  <input class="form-control" id="reviewTitle" placeholder="Short title" />
                </div>
                <div class="col-12">
                  <label class="form-label">Review</label>
                  <textarea class="form-control" id="reviewBody" rows="3" placeholder="Write your experience..."></textarea>
                </div>
                <div class="col-12 d-flex gap-2">
                  <button class="btn btn-primary" id="submitReviewBtn" type="button">Submit review</button>
                </div>
              </div>
            </div>
          </div>
        </div>
      `;

      const listEl = qs('#reviewsList', reviewsHost);
      const ratingSel = qs('#reviewRating', reviewsHost);
      const titleInp = qs('#reviewTitle', reviewsHost);
      const bodyInp = qs('#reviewBody', reviewsHost);
      const submitBtn = qs('#submitReviewBtn', reviewsHost);
      const hintEl = qs('#reviewsHint', reviewsHost);
      const formWrap = qs('#reviewFormWrap', reviewsHost);

      let eligibleToReview = false;

      async function loadEligibility() {
        if (!cust) {
          eligibleToReview = false;
          if (formWrap) formWrap.classList.add('d-none');
          if (hintEl) hintEl.textContent = 'Sign in to write a review.';
          return;
        }
        try {
          const el = await apiFetch(
            GC.api.productReviews(p.product_id) + `/eligibility?customer_id=${encodeURIComponent(cust.customer_id)}`
          );
          eligibleToReview = !!(el && el.eligible);
          if (eligibleToReview) {
            if (formWrap) formWrap.classList.remove('d-none');
            if (hintEl) hintEl.textContent = 'Verified purchase: leave your review below.';
          } else {
            if (formWrap) formWrap.classList.add('d-none');
            const reason = el && el.reason ? String(el.reason) : '';
            if (reason === 'NOT_DELIVERED') {
              if (hintEl) hintEl.textContent = 'You can review this product after your order is delivered.';
            } else if (reason === 'NOT_PURCHASED') {
              if (hintEl) hintEl.textContent = 'Only customers who purchased and received this product can review it.';
            } else {
              if (hintEl) hintEl.textContent = 'You are not eligible to review this product yet.';
            }
          }
        } catch (err) {
          eligibleToReview = false;
          if (formWrap) formWrap.classList.add('d-none');
          const msg = String(err && err.message ? err.message : 'Eligibility check failed');
          if (hintEl) hintEl.textContent = msg;
        }
      }

      async function loadReviews() {
        if (listEl) listEl.innerHTML = '<div class="text-secondary small">Loading...</div>';
        try {
          const rows = await apiFetch(GC.api.productReviews(p.product_id) + '?limit=25&offset=0');
          const arr = Array.isArray(rows) ? rows : [];
          if (!arr.length) {
            if (listEl) listEl.innerHTML = '<div class="text-secondary small">No reviews yet.</div>';
            return;
          }
          if (listEl) {
            listEl.innerHTML = arr
              .map(
                (r) => `
                  <div class="border-top pt-3 mt-3">
                    <div class="fw-semibold">${escapeHtml(r.title || 'Review')}</div>
                    <div class="small text-secondary">Rating: ${escapeHtml(r.rating)} · Customer #${escapeHtml(r.customer_id)} · ${escapeHtml(r.created_at)}</div>
                    <div class="mt-2">${escapeHtml(r.body || '')}</div>
                  </div>
                `
              )
              .join('');
          }
        } catch (err) {
          const msg = String(err && err.message ? err.message : 'Failed to load reviews.');
          if (listEl) listEl.innerHTML = `<div class="text-danger small">${escapeHtml(msg)}</div>`;
        }
      }

      await loadReviews();
      await loadEligibility();

      if (submitBtn && cust) {
        submitBtn.addEventListener('click', async () => {
          submitBtn.disabled = true;
          try {
            await loadEligibility();
            if (!eligibleToReview) {
              toast('Not eligible', 'You can review only after delivery of this product.', 'warning');
              return;
            }
            const payload = {
              rating: Number(ratingSel ? ratingSel.value : 5),
              title: titleInp ? String(titleInp.value || '').trim() : '',
              body: bodyInp ? String(bodyInp.value || '').trim() : '',
            };
            await apiFetch(GC.api.productReviews(p.product_id) + `?customer_id=${encodeURIComponent(cust.customer_id)}` , {
              method: 'POST',
              body: JSON.stringify(payload),
            });
            toast('Thanks!', 'Your review was saved.', 'success');
            if (titleInp) titleInp.value = '';
            if (bodyInp) bodyInp.value = '';
            await loadReviews();
          } catch (err) {
            toast('Review failed', (err && err.message) ? err.message : 'Unable to save review', 'danger');
          } finally {
            submitBtn.disabled = false;
          }
        });
      }
    }

    await track('VIEW_PRODUCT', { product_id: Number(p.product_id) });

    if (addBtn) {
      addBtn.disabled = !p.in_stock;
      addBtn.addEventListener('click', async () => {
        const qv = qty ? Number(qty.value || 1) : 1;
        addToCart(p.product_id, qv);
        toast('Added to cart', `${qv} item(s) added.`, 'success');
        await track('ADD_TO_CART', { product_id: Number(p.product_id) });
      });
    }
  } catch (err) {
    toast('Failed to load', err.message || 'Unable to fetch product', 'danger');
  }
}

async function initCart() {
  bindGlobalNav();
  await track('VIEW_CART');

  const listEl = qs('#cartList');
  const totalEl = qs('#cartTotal');
  const checkoutBtn = qs('#checkoutBtn');

  async function render() {
    const cart = loadCart();
    if (!listEl) return;

    if (!cart.items.length) {
      listEl.innerHTML = '<div class="text-secondary">Your cart is empty.</div>';
      if (totalEl) totalEl.textContent = fmtMoney(0, 'INR');
      if (checkoutBtn) checkoutBtn.disabled = true;
      return;
    }

    const ps = await Promise.all(cart.items.map((it) => fetchProduct(it.product_id)));
    const map = new Map(ps.map((p) => [Number(p.product_id), p]));

    let total = 0;
    listEl.innerHTML = '';
    for (const it of cart.items) {
      const p = map.get(Number(it.product_id));
      if (!p) continue;
      const line = Number(p.sell_price) * Number(it.qty);
      total += line;

      const row = document.createElement('div');
      row.className = 'list-group-item d-flex align-items-center gap-3';
      row.innerHTML = `
        <img loading="lazy" src="${escapeHtml(p.image_url)}" class="rounded" style="width:64px;height:64px;object-fit:cover;" alt="${escapeHtml(p.product_name)}" />
        <div class="flex-grow-1">
          <div class="fw-semibold">${escapeHtml(p.product_name)}</div>
          <div class="small text-secondary">${escapeHtml(p.brand)} · ${escapeHtml(p.category_l2)}</div>
          <div class="small mt-1">${escapeHtml(fmtMoney(p.sell_price, 'INR'))} each</div>
        </div>
        <div class="d-flex align-items-center gap-2">
          <input type="number" min="1" max="20" value="${escapeHtml(it.qty)}" class="form-control form-control-sm" style="width:84px" data-qty="${escapeHtml(p.product_id)}" />
          <button class="btn btn-sm btn-outline-danger" data-rm="${escapeHtml(p.product_id)}">Remove</button>
        </div>
      `;
      listEl.appendChild(row);
    }

    qsa('[data-qty]', listEl).forEach((inp) => {
      inp.addEventListener('change', () => {
        const pid = inp.getAttribute('data-qty');
        updateCartQty(pid, Number(inp.value || 1));
        render();
      });
    });
    qsa('[data-rm]', listEl).forEach((btn) => {
      btn.addEventListener('click', () => {
        const pid = btn.getAttribute('data-rm');
        removeFromCart(pid);
        render();
      });
    });

    if (totalEl) totalEl.textContent = fmtMoney(total, 'INR');
    if (checkoutBtn) checkoutBtn.disabled = false;
  }

  await render();

  if (checkoutBtn) {
    checkoutBtn.addEventListener('click', async () => {
      await track('CHECKOUT_STARTED');
      window.location.href = 'checkout.html';
    });
  }
}

async function initAddresses() {
  bindGlobalNav();
  const listEl = qs('#addressesList');
  const addForm = qs('#addAddressForm');
  const editForm = qs('#editAddressForm');
  const addModal = bootstrap.Modal?.getOrCreateInstance(qs('#addAddressModal'));
  const editModal = bootstrap.Modal?.getOrCreateInstance(qs('#editAddressModal'));

  const cust = getCustomer();
  if (!cust || !listEl) {
    if (listEl) listEl.innerHTML = '<div class="alert alert-warning">Please sign in to manage your addresses.</div>';
    return;
  }

  let addresses = [];

  async function loadAddresses() {
    try {
      const res = await apiFetch(`/addresses?customer_id=${cust.customer_id}`);
      addresses = Array.isArray(res) ? res : [];
      renderAddresses();
    } catch (err) {
      if (listEl) listEl.innerHTML = '<div class="alert alert-danger">Failed to load addresses.</div>';
    }
  }

  function renderAddresses() {
    if (!listEl) return;
    if (!addresses.length) {
      listEl.innerHTML = '<div class="alert alert-info">No saved addresses yet.</div>';
      return;
    }
    listEl.innerHTML = '';
    addresses.forEach((addr) => {
      const card = document.createElement('div');
      card.className = 'card mb-3';
      card.innerHTML = `
        <div class="card-body">
          <div class="d-flex justify-content-between align-items-start">
            <div>
              <div class="fw-semibold">${escapeHtml(addr.recipient_name)} ${addr.label ? `<span class=\"badge bg-secondary ms-1\">${escapeHtml(addr.label)}</span>` : ''} ${addr.is_default ? '<span class="badge bg-primary ms-1">Default</span>' : ''}</div>
              <div class="text-secondary">${escapeHtml(addr.phone || '')}</div>
              <div>${escapeHtml(addr.address_line1)}</div>
              ${addr.address_line2 ? `<div>${escapeHtml(addr.address_line2)}</div>` : ''}
              <div>${escapeHtml(addr.city)}, ${escapeHtml(addr.state)} ${escapeHtml(addr.postal_code)}</div>
              <div>${escapeHtml(addr.country)}</div>
            </div>
            <div class="btn-group" role="group">
              <button type="button" class="btn btn-sm btn-outline-primary" data-edit="${addr.address_id}">Edit</button>
              <button type="button" class="btn btn-sm btn-outline-danger" data-delete="${addr.address_id}">Delete</button>
            </div>
          </div>
        </div>
      `;
      listEl.appendChild(card);
    });

    listEl.addEventListener('click', async (e) => {
      if (e.target.matches('[data-edit]')) {
        const addrId = Number(e.target.dataset.edit);
        const addr = addresses.find((a) => a.address_id === addrId);
        if (addr && editForm) {
          editForm.address_id.value = addr.address_id;
          if (editForm.label) editForm.label.value = addr.label || '';
          editForm.recipient_name.value = addr.recipient_name;
          editForm.phone.value = addr.phone || '';
          editForm.address_line1.value = addr.address_line1;
          editForm.address_line2.value = addr.address_line2 || '';
          editForm.city.value = addr.city;
          editForm.state.value = addr.state;
          editForm.postal_code.value = addr.postal_code;
          editForm.country.value = addr.country;
          editForm.is_default.checked = addr.is_default;
          editModal?.show();
        }
      } else if (e.target.matches('[data-delete]')) {
        const addrId = Number(e.target.dataset.delete);
        if (confirm('Are you sure you want to delete this address?')) {
          try {
            await apiFetch(`/addresses/${addrId}?customer_id=${cust.customer_id}`, { method: 'DELETE' });
            toast('Address deleted', 'The address has been removed.', 'success');
            await loadAddresses();
          } catch (err) {
            toast('Delete failed', err.message || 'Could not delete address', 'danger');
          }
        }
      }
    });
  }

  if (addForm) {
    qs('#saveNewAddressBtn')?.addEventListener('click', async () => {
      const formData = new FormData(addForm);
      const payload = Object.fromEntries(formData.entries());
      payload.is_default = !!payload.is_default;
      try {
        await apiFetch(`/addresses?customer_id=${cust.customer_id}`, {
          method: 'POST',
          body: JSON.stringify(payload),
        });
        toast('Address added', 'New address has been saved.', 'success');
        addForm.reset();
        addModal?.hide();
        await loadAddresses();
      } catch (err) {
        toast('Add failed', err.message || 'Could not add address', 'danger');
      }
    });
  }

  if (editForm) {
    qs('#saveEditAddressBtn')?.addEventListener('click', async () => {
      const formData = new FormData(editForm);
      const payload = Object.fromEntries(formData.entries());
      payload.is_default = !!payload.is_default;
      const addrId = Number(payload.address_id);
      delete payload.address_id;
      try {
        await apiFetch(`/addresses/${addrId}?customer_id=${cust.customer_id}`, {
          method: 'PUT',
          body: JSON.stringify(payload),
        });
        toast('Address updated', 'Your changes have been saved.', 'success');
        editModal?.hide();
        await loadAddresses();
      } catch (err) {
        toast('Update failed', err.message || 'Could not update address', 'danger');
      }
    });
  }

  await loadAddresses();
}

async function initCheckout() {
  bindGlobalNav();
  await track('CHECKOUT_STARTED');

  const cart = loadCart();
  const listEl = qs('#checkoutItems');
  const totalEl = qs('#checkoutTotal');
  const pmSel = qs('#paymentMethod');
  const failChk = qs('#simulateFail');
  const failReason = qs('#failureReason');
  const placeBtn = qs('#placeOrderBtn');
  const recipientName = qs('#recipientName');
  const recipientPhone = qs('#recipientPhone');
  const addressLine1 = qs('#addressLine1');
  const addressLine2 = qs('#addressLine2');
  const addressCity = qs('#addressCity');
  const addressState = qs('#addressState');
  const addressPostal = qs('#addressPostal');
  const addressCountry = qs('#addressCountry');
  const savedAddressSelect = qs('#savedAddressSelect');
  const saveAddressChk = qs('#saveAddress');
  const newAddressFields = qs('#newAddressFields');
  const promoCodeInput = qs('#promoCodeInput');
  const applyPromoBtn = qs('#applyPromoBtn');
  const promoMsg = qs('#promoMsg');
  const subtotalEl = qs('#checkoutSubtotal');
  const taxEl = qs('#checkoutTax');
  const promoRow = qs('#checkoutPromoRow');
  const promoCodeEl = qs('#checkoutPromoCode');
  const promoDiscountEl = qs('#checkoutPromoDiscount');

  if (!cart.items.length) {
    if (listEl) listEl.innerHTML = '<div class="alert alert-warning">Your cart is empty. <a href="index.html" class="alert-link">Continue shopping</a> to add items before checkout.</div>';
    if (placeBtn) {
      placeBtn.disabled = true;
      placeBtn.textContent = 'Cart is empty';
    }
    if (totalEl) totalEl.textContent = fmtMoney(0, 'INR');
    return;
  }

  const cust = getCustomer();
  let savedAddresses = [];
  let appliedPromoCode = '';
  let appliedPromoDiscount = 0;

  if (!cust) {
    if (placeBtn) {
      placeBtn.disabled = false;
      placeBtn.textContent = 'Sign in to place order';
    }
    toast('Sign in required', 'Please sign in to place an order.', 'warning');
    await sleep(300);
    goToLogin();
    return;
  }

  async function loadSavedAddresses() {
    if (!cust || !savedAddressSelect) return;
    try {
      const res = await apiFetch(`/addresses?customer_id=${cust.customer_id}`);
      savedAddresses = Array.isArray(res) ? res : [];
      savedAddressSelect.innerHTML = '<option value="">-- Enter a new address --</option>';
      savedAddresses.forEach((addr) => {
        const opt = document.createElement('option');
        opt.value = addr.address_id;
        const prefix = addr.label ? `${addr.label} · ` : '';
        opt.textContent = `${prefix}${addr.recipient_name}, ${addr.address_line1}, ${addr.city}, ${addr.state} ${addr.postal_code}`;
        if (addr.is_default) opt.textContent += ' (Default)';
        savedAddressSelect.appendChild(opt);
      });

      const currentVal = savedAddressSelect.value;
      if (!currentVal) {
        const def = savedAddresses.find((a) => a.is_default);
        if (def) {
          savedAddressSelect.value = String(def.address_id);
          fillAddressFromSaved(def.address_id);
          if (newAddressFields) newAddressFields.style.opacity = '0.6';
          if (saveAddressChk) saveAddressChk.disabled = true;
        }
      }
    } catch (err) {
      console.error('Failed to load saved addresses:', err);
    }
  }

  function fillAddressFromSaved(addrId) {
    const addr = savedAddresses.find((a) => a.address_id === Number(addrId));
    if (!addr) return;
    if (recipientName) recipientName.value = addr.recipient_name || '';
    if (recipientPhone) recipientPhone.value = addr.phone || '';
    if (addressLine1) addressLine1.value = addr.address_line1 || '';
    if (addressLine2) addressLine2.value = addr.address_line2 || '';
    if (addressCity) addressCity.value = addr.city || '';
    if (addressState) addressState.value = addr.state || '';
    if (addressPostal) addressPostal.value = addr.postal_code || '';
    if (addressCountry) addressCountry.value = addr.country || '';
  }

  function clearAddressFields() {
    if (recipientName) recipientName.value = '';
    if (recipientPhone) recipientPhone.value = '';
    if (addressLine1) addressLine1.value = '';
    if (addressLine2) addressLine2.value = '';
    if (addressCity) addressCity.value = '';
    if (addressState) addressState.value = '';
    if (addressPostal) addressPostal.value = '';
    if (addressCountry) addressCountry.value = 'India';
  }

  if (savedAddressSelect) {
    savedAddressSelect.addEventListener('change', () => {
      const val = savedAddressSelect.value;
      if (val) {
        fillAddressFromSaved(val);
        if (newAddressFields) newAddressFields.style.opacity = '0.6';
        if (saveAddressChk) saveAddressChk.disabled = true;
      } else {
        clearAddressFields();
        if (newAddressFields) newAddressFields.style.opacity = '1';
        if (saveAddressChk) saveAddressChk.disabled = false;
      }
    });
  }

  // Enforce numeric-only input for phone and postal code
  if (recipientPhone) {
    recipientPhone.addEventListener('input', () => {
      recipientPhone.value = recipientPhone.value.replace(/\D/g, '').slice(0, 10);
      recipientPhone.classList.remove('is-invalid', 'border-danger');
    });
  }
  if (addressPostal) {
    addressPostal.addEventListener('input', () => {
      addressPostal.value = addressPostal.value.replace(/\D/g, '').slice(0, 6);
      addressPostal.classList.remove('is-invalid', 'border-danger');
    });
  }

  // Clear error borders on input for other fields
  const errorFields = [recipientName, addressLine1, addressCity, addressState, addressCountry];
  errorFields.forEach((el) => {
    if (el) {
      el.addEventListener('input', () => {
        el.classList.remove('is-invalid', 'border-danger');
      });
    }
  });

  await loadSavedAddresses();

  try {
    const ps = await Promise.all(cart.items.map((it) => fetchProduct(it.product_id)));
    const map = new Map(ps.map((p) => [Number(p.product_id), p]));

    let subtotal = 0;
    if (listEl) {
      listEl.innerHTML = '';
      for (const it of cart.items) {
        const p = map.get(Number(it.product_id));
        if (!p) continue;
        const line = Number(p.sell_price) * Number(it.qty);
        subtotal += line;
        const row = document.createElement('div');
        row.className = 'd-flex justify-content-between py-2 border-bottom';
        row.innerHTML = `
          <div>
            <div class="fw-semibold">${escapeHtml(p.product_name)}</div>
            <div class="small text-secondary">Qty ${escapeHtml(it.qty)}</div>
          </div>
          <div class="fw-semibold">${escapeHtml(fmtMoney(line, 'INR'))}</div>
        `;
        listEl.appendChild(row);
      }
    }

    const tax = Math.round(subtotal * 0.07 * 100) / 100;
    const prePromoTotal = Math.round((subtotal + tax) * 100) / 100;

    function renderTotals() {
      const payable = Math.max(0, Math.round((prePromoTotal - appliedPromoDiscount) * 100) / 100);
      if (subtotalEl) subtotalEl.textContent = fmtMoney(subtotal, 'INR');
      if (taxEl) taxEl.textContent = fmtMoney(tax, 'INR');
      if (promoRow) promoRow.classList.toggle('d-none', !(appliedPromoCode && appliedPromoDiscount > 0));
      if (promoCodeEl) promoCodeEl.textContent = appliedPromoCode;
      if (promoDiscountEl) promoDiscountEl.textContent = fmtMoney(appliedPromoDiscount, 'INR');
      if (totalEl) totalEl.textContent = fmtMoney(payable, 'INR');
    }

    renderTotals();

    if (applyPromoBtn && promoCodeInput && !applyPromoBtn.dataset.gcWired) {
      applyPromoBtn.dataset.gcWired = '1';
      applyPromoBtn.addEventListener('click', async () => {
        const code = String(promoCodeInput.value || '').trim();
        if (!code) {
          if (promoMsg) promoMsg.textContent = 'Enter a promo code.';
          return;
        }
        applyPromoBtn.disabled = true;
        try {
          const res = await apiFetch(`${GC.api.promoValidate}?code=${encodeURIComponent(code)}&amount=${encodeURIComponent(prePromoTotal)}`);
          if (res && res.valid) {
            appliedPromoCode = String(res.code || code).toUpperCase();
            appliedPromoDiscount = Number(res.discount_amount || 0);
            if (promoMsg) promoMsg.textContent = `Applied ${appliedPromoCode} (-${fmtMoney(appliedPromoDiscount, 'INR')})`;
          } else {
            appliedPromoCode = '';
            appliedPromoDiscount = 0;
            if (promoMsg) promoMsg.textContent = (res && res.message) ? String(res.message) : 'Invalid promo code.';
          }
          renderTotals();
        } catch (err) {
          if (promoMsg) promoMsg.textContent = err.message || 'Failed to apply code.';
        } finally {
          applyPromoBtn.disabled = false;
        }
      });
    }

    if (placeBtn) {
      placeBtn.addEventListener('click', async () => {
        placeBtn.disabled = true;
        try {
          const cust = getCustomer();
          const simulate = !!(failChk && failChk.checked);
          const fr = failReason ? String(failReason.value || '').trim() : '';
          await track('PAYMENT_ATTEMPTED');

          // Validate address before placing order
          function validateAddress() {
            if (savedAddressSelect && savedAddressSelect.value) {
              // A saved address is selected
              return true;
            }
            // Clear previous error styles
            const clearError = (el) => {
              if (el) {
                el.classList.remove('is-invalid');
                el.classList.remove('border-danger');
              }
            };
            const showError = (el) => {
              if (el) {
                el.classList.add('is-invalid');
                el.classList.add('border-danger');
              }
            };
            const required = [
              { el: recipientName, name: 'Recipient name', validate: (v) => v.trim().length > 0 },
              { el: recipientPhone, name: 'Phone', validate: (v) => /^\d{10}$/.test(v) },
              { el: addressLine1, name: 'Address line 1', validate: (v) => v.trim().length > 0 },
              { el: addressCity, name: 'City', validate: (v) => v.trim().length > 0 },
              { el: addressState, name: 'State', validate: (v) => v.trim().length > 0 },
              { el: addressPostal, name: 'Postal code', validate: (v) => /^\d{6}$/.test(v) },
              { el: addressCountry, name: 'Country', validate: (v) => v.trim().length > 0 },
            ];
            let firstInvalid = null;
            for (const { el, name, validate } of required) {
              clearError(el);
              if (!el) continue;
              const val = String(el.value || '').trim();
              if (!validate(val)) {
                if (!firstInvalid) firstInvalid = el;
                showError(el);
              }
            }
            if (firstInvalid) {
              firstInvalid.focus();
              return false;
            }
            return true;
          }

          if (!validateAddress()) {
            placeBtn.disabled = false;
            return;
          }

          // If save address is checked and not selecting a saved address, save it first
          if (saveAddressChk && saveAddressChk.checked && !cust) {
            console.error('Save address attempted by non-signed-in user');
            toast('Sign in required', 'Please sign in to save addresses.', 'warning');
            placeBtn.disabled = false;
            return;
          }

          if (saveAddressChk && saveAddressChk.checked && savedAddressSelect && !savedAddressSelect.value && cust) {
            console.log('Attempting to save address for customer:', cust.customer_id);
            const addrPayload = {
              recipient_name: recipientName ? String(recipientName.value || '').trim() : '',
              phone: recipientPhone ? String(recipientPhone.value || '').trim() : '',
              address_line1: addressLine1 ? String(addressLine1.value || '').trim() : '',
              address_line2: addressLine2 ? String(addressLine2.value || '').trim() : '',
              city: addressCity ? String(addressCity.value || '').trim() : '',
              state: addressState ? String(addressState.value || '').trim() : '',
              postal_code: addressPostal ? String(addressPostal.value || '').trim() : '',
              country: addressCountry ? String(addressCountry.value || '').trim() : '',
              is_default: savedAddresses.length === 0,
            };
            console.log('Address payload to save:', addrPayload);
            try {
              const created = await apiFetch(`/addresses?customer_id=${cust.customer_id}`, {
                method: 'POST',
                body: JSON.stringify(addrPayload),
              });
              console.log('Address saved successfully:', created);
              toast('Address saved', 'Your address has been saved for future orders.', 'success');
              await loadSavedAddresses();
              if (savedAddressSelect && created && created.address_id) {
                savedAddressSelect.value = String(created.address_id);
                fillAddressFromSaved(created.address_id);
                if (newAddressFields) newAddressFields.style.opacity = '0.6';
                saveAddressChk.checked = false;
                saveAddressChk.disabled = true;
              }
            } catch (err) {
              console.error('Failed to save address', err);
              console.error('Error details:', {
                status: err.status,
                message: err.message,
                stack: err.stack
              });
              toast('Failed to save address', err.message || 'Could not save address', 'danger');
              placeBtn.disabled = false;
              return;
            }
          } else if (saveAddressChk && saveAddressChk.checked) {
            console.log('Save address checkbox checked but conditions not met:', {
              hasSaveAddressChk: !!saveAddressChk,
              isChecked: saveAddressChk.checked,
              hasSavedAddressSelect: !!savedAddressSelect,
              selectValue: savedAddressSelect?.value,
              hasCustomer: !!cust
            });
          }

          const req = {
            items: cart.items.map((x) => ({ product_id: Number(x.product_id), qty: Number(x.qty) })),
            channel: 'WEB',
            currency: 'INR',
            customer_id: cust ? cust.customer_id : null,
            promo_code: appliedPromoCode || null,
            payment_method: pmSel ? pmSel.value : 'UPI',
            simulate_payment_failure: simulate,
            failure_reason: simulate ? (fr || 'BANK_DECLINED') : null,
            address: {
              recipient_name: recipientName ? String(recipientName.value || '').trim() : '',
              phone: recipientPhone ? String(recipientPhone.value || '').trim() : '',
              address_line1: addressLine1 ? String(addressLine1.value || '').trim() : '',
              address_line2: addressLine2 ? String(addressLine2.value || '').trim() : '',
              city: addressCity ? String(addressCity.value || '').trim() : '',
              state: addressState ? String(addressState.value || '').trim() : '',
              postal_code: addressPostal ? String(addressPostal.value || '').trim() : '',
              country: addressCountry ? String(addressCountry.value || '').trim() : '',
            },
          };

          const res = await apiFetch(GC.api.createOrder, { method: 'POST', body: JSON.stringify(req) });

          if (res && String(res.payment_status || '').toUpperCase() === 'FAILED') {
            toast('Payment failed', `Order #${res.order_id} marked as failed.`, 'danger');
            await track('PAYMENT_FAILED', {
              order_id: Number(res.order_id),
              failure_reason: simulate ? (fr || 'BANK_DECLINED') : null,
            });
            return;
          }

          const overlay = qs('#orderConfirmOverlay');
          const overlayText = qs('#orderConfirmText');
          const confetti = qs('#orderConfirmConfetti');
          if (overlayText) overlayText.textContent = `Order #${res.order_id} confirmed`;
          if (overlay) {
            overlay.classList.remove('d-none');
            overlay.setAttribute('aria-hidden', 'false');
          }
          renderConfetti(confetti, 30);

          await track('ORDER_PLACED', { order_id: Number(res.order_id) });

          saveCart({ items: [] });
          await sleep(5800);
          window.location.href = 'orders.html';
        } catch (err) {
          toast('Checkout failed', err.message || 'Unable to place order', 'danger');
        } finally {
          placeBtn.disabled = false;
        }
      });
    }
  } catch (err) {
    toast('Checkout failed', err.message || 'Unable to load checkout', 'danger');
  }
}

async function initOrders() {
  bindGlobalNav();

  const listEl = qs('#ordersList');
  const refreshBtn = qs('#refreshOrders');

  async function load() {
    const cust = getCustomer();
    if (!cust) {
      if (listEl) listEl.innerHTML = '<div class="text-secondary">Sign in to view orders.</div>';
      return;
    }

    if (listEl) listEl.innerHTML = '<div class="text-secondary">Loading…</div>';

    try {
      const data = await apiFetch(GC.api.ordersByCustomer(cust.customer_id) + '?limit=25');
      const orders = data && data.orders ? data.orders : [];
      if (!orders.length) {
        if (listEl) listEl.innerHTML = '<div class="text-secondary">No orders yet.</div>';
        return;
      }

      if (listEl) {
        listEl.innerHTML = '';
        for (const o of orders) {
          const card = document.createElement('div');
          card.className = 'card shadow-sm mb-3';
          const canCancel = String(o.order_status || '').toUpperCase() === 'PLACED';
          const items = (o.items || []).slice(0, 3).map((it) => `${escapeHtml(it.product_name)} × ${escapeHtml(it.qty)}`).join('<br/>');
          card.innerHTML = `
            <div class="card-body">
              <div class="d-flex justify-content-between align-items-start">
                <div>
                  <div class="fw-semibold">Order #${escapeHtml(o.order_id)}</div>
                  <div class="small text-secondary">${escapeHtml(o.order_ts)}</div>
                </div>
                <span class="badge text-bg-secondary">${escapeHtml(o.order_status)}</span>
              </div>
              <div class="mt-2 small">${items}</div>
              <div class="mt-3 d-flex justify-content-between align-items-center">
                <div class="fw-semibold">${escapeHtml(fmtMoney(o.net_amount, 'INR'))}</div>
                <div class="d-flex gap-2">
                  <a class="btn btn-sm btn-outline-primary" href="order.html?order_id=${encodeURIComponent(o.order_id)}">View</a>
                  ${canCancel ? `<button class="btn btn-sm btn-outline-danger" type="button" data-cancel-order="${escapeHtml(o.order_id)}">Cancel</button>` : ''}
                </div>
              </div>
            </div>
          `;
          listEl.appendChild(card);
        }

        qsa('[data-cancel-order]', listEl).forEach((btn) => {
          btn.addEventListener('click', async () => {
            const cust = getCustomer();
            if (!cust) {
              toast('Sign in required', 'Sign in to cancel orders.', 'warning');
              return;
            }
            const orderId = btn.getAttribute('data-cancel-order');
            const reason = await pickCancellationReason();
            if (!reason) return;
            btn.disabled = true;
            try {
              await apiFetch(GC.api.cancelOrder(orderId), {
                method: 'POST',
                body: JSON.stringify({ customer_id: Number(cust.customer_id), reason }),
              });
              toast('Order cancelled', `Order #${orderId} cancelled.`, 'secondary');
              await load();
            } catch (err) {
              toast('Cancel failed', err.message || 'Unable to cancel order', 'danger');
              btn.disabled = false;
            }
          });
        });
      }
    } catch (err) {
      if (listEl) listEl.innerHTML = '<div class="text-danger">Failed to load orders.</div>';
      toast('Orders failed', err.message || 'Unable to load orders', 'danger');
    }
  }

  await load();

  if (refreshBtn) {
    refreshBtn.addEventListener('click', async () => {
      refreshBtn.disabled = true;
      try {
        await load();
      } finally {
        refreshBtn.disabled = false;
      }
    });
  }
}

document.addEventListener('DOMContentLoaded', async () => {
  const page = document.body ? document.body.getAttribute('data-page') : '';

  if (page !== 'login') {
    if (!requireCustomerOrRedirect()) return;
  }

  showBrandIntro();
  setActiveNavLink();

  document.querySelectorAll('.navbar a.nav-link').forEach((a) => {
    a.addEventListener('click', (e) => {
      const href = a.getAttribute('href') || '';
      if (!href || href.startsWith('#')) return;
      if (a.getAttribute('target') === '_blank') return;
      if (e.defaultPrevented) return;
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
      try {
        const u = new URL(href, window.location.href);
        if (u.origin !== window.location.origin) return;
        if (u.pathname === window.location.pathname && u.search === window.location.search) return;
      } catch {
        return;
      }
      e.preventDefault();
      document.body.classList.add('gc-page-exit');
      window.setTimeout(() => {
        window.location.href = href;
      }, 160);
    });
  });

  if (page === 'home') return initHome();
  if (page === 'product') return initProduct();
  if (page === 'cart') return initCart();
  if (page === 'checkout') return initCheckout();
  if (page === 'orders') return initOrders();
  if (page === 'login') return initLogin();
  if (page === 'addresses') return initAddresses();
  if (page === 'wishlist') return initWishlist();
  if (page === 'order') return initOrder();
  if (page === 'emails') return initEmails();
  bindGlobalNav();
});
