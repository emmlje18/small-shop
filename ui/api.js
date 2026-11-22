// Talking to the catalog and orders services.
//
// Both services scale to zero and their databases pause when idle, so the
// first request after a quiet period can take up to about a minute (a "cold
// start"). Requests that fail in a way a cold start explains (no answer,
// timeout, 502/503/504) are retried for up to two minutes while the page shows
// "the shop is starting up". If a service still does not answer, the call
// fails with a ServiceError that names the service, so each page can say
// which part of the shop is unavailable and what still works.

const SHOP_CONFIG = window.SHOP_CONFIG || {};
const SERVICE_URLS = {
  catalog: (SHOP_CONFIG.catalogUrl || "").replace(/\/$/, ""),
  orders: (SHOP_CONFIG.ordersUrl || "").replace(/\/$/, ""),
};

const ATTEMPT_TIMEOUT_MS = 30000; // give up on one attempt after 30 s
const WAIT_BUDGET_MS = 120000; // keep retrying for up to 2 minutes in total
const RETRY_DELAYS_MS = [2000, 4000, 6000, 10000, 15000];

// The orders service answers 503 with this text when it cannot reach the
// catalog (see services/orders/openapi.yaml).
const CATALOG_DOWN_TEXT = "catalog";

class ServiceError extends Error {
  // service: "catalog" or "orders", the one that is not working.
  // status: the HTTP status, or 0 when there was no answer at all.
  // unavailable: true when the service could not be reached in time.
  constructor(service, status, message, body, unavailable) {
    super(message);
    this.service = service;
    this.status = status;
    this.body = body || {};
    this.unavailable = unavailable;
  }
}

// Pages register these to show and hide the "starting up" message.
const waitListeners = { start: () => {}, stop: () => {} };

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// One HTTP attempt with a timeout. Returns {status, body} or throws when
// there was no answer (network error or timeout).
async function attempt(url, options) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), ATTEMPT_TIMEOUT_MS);
  try {
    const response = await fetch(url, { ...options, signal: controller.signal });
    const type = response.headers.get("Content-Type") || "";
    const body = type.includes("application/json") ? await response.json() : null;
    return { status: response.status, body };
  } finally {
    clearTimeout(timer);
  }
}

// Call a service and return its JSON body (or null for an empty answer).
//
//   service   "catalog" or "orders"
//   path      e.g. "/products"
//   options   fetch options; plus
//             json: an object to send as the JSON body
//             admin: true to send the admin password
//             retryOnlyOn503: for checkout, which must not be sent twice.
//               A 503 from orders means nothing was charged, so it is safe to
//               retry; a lost answer is not, because the order may exist.
async function callService(service, path, options = {}) {
  const { json, admin, retryOnlyOn503, ...fetchOptions } = options;
  const headers = { ...(fetchOptions.headers || {}) };
  if (json !== undefined) {
    headers["Content-Type"] = "application/json";
    fetchOptions.body = JSON.stringify(json);
  }
  if (admin) {
    headers.Authorization = `Bearer ${adminPassword()}`;
  }
  const url = SERVICE_URLS[service] + path;
  const started = Date.now();
  let waiting = false;

  try {
    for (let tries = 0; ; tries += 1) {
      let result = null;
      try {
        result = await attempt(url, { ...fetchOptions, headers });
      } catch (networkError) {
        result = null; // no answer: the service may be starting
      }

      const status = result ? result.status : 0;
      const body = (result && result.body) || {};
      const retryable = retryOnlyOn503 ? status === 503 : [0, 502, 503, 504].includes(status);

      if (!retryable) {
        if (status >= 200 && status < 300) return result.body;
        throw new ServiceError(service, status, body.error || `Request failed (${status}).`, body, false);
      }

      if (Date.now() - started > WAIT_BUDGET_MS) {
        // Orders answering "catalog unavailable" means the catalog is the
        // part that is down, not orders.
        const failed = status === 503 && service === "orders" &&
          String(body.error || "").toLowerCase().includes(CATALOG_DOWN_TEXT) ? "catalog" : service;
        throw new ServiceError(failed, status, body.error || `The ${failed} service is not responding.`, body, true);
      }

      if (!waiting) {
        waiting = true;
        waitListeners.start(service);
      }
      await sleep(RETRY_DELAYS_MS[Math.min(tries, RETRY_DELAYS_MS.length - 1)]);
    }
  } finally {
    if (waiting) waitListeners.stop(service);
  }
}

// ------------------------------------------------------------ browser storage
// localStorage can be missing or blocked (private windows), so every access
// is wrapped and the shop still works, just without remembering the cart.

function readStored(storage, key, fallback) {
  try {
    const value = window[storage].getItem(key);
    return value === null ? fallback : JSON.parse(value);
  } catch (error) {
    return fallback;
  }
}

function writeStored(storage, key, value) {
  try {
    if (value === null) window[storage].removeItem(key);
    else window[storage].setItem(key, JSON.stringify(value));
  } catch (error) {
    // Storage unavailable: nothing to do.
  }
}

// The cart is [{"variant_id": 4, "qty": 2}], the same shape the orders API uses.
function loadCart() {
  const cart = readStored("localStorage", "shop.cart", []);
  return Array.isArray(cart) ? cart : [];
}

function saveCart(cart) {
  writeStored("localStorage", "shop.cart", cart);
  showCartCount();
}

// The number of items in the cart, shown in the top bar.
function showCartCount() {
  document.getElementById("cart-count").textContent =
    loadCart().reduce((total, line) => total + line.qty, 0);
}

// The admin password is kept only for this browser tab (sessionStorage) and
// is sent as "Authorization: Bearer ..." on admin requests.
function adminPassword() {
  return readStored("sessionStorage", "shop.admin", "");
}

function setAdminPassword(password) {
  writeStored("sessionStorage", "shop.admin", password || null);
}
