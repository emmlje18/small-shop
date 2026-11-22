// The shop's pages, drawn in the browser from the services' JSON.
//
// The page never reloads. The part of the address after "#" says which page
// to show (#/, #/product/3, #/cart, #/admin ...), and render() draws it when
// that changes. Everything the services send is escaped with esc() before it
// is put into the page, so a product name cannot inject HTML or scripts.

const app = document.getElementById("app");
const statusArea = document.getElementById("status");
const PLACEHOLDER_IMAGE = "product-placeholder.svg";
const MAX_IMAGE_BYTES = 5 * 1024 * 1024;

let renderToken = 0; // increases on every navigation; stale pages are dropped
let flash = ""; // a one-time message shown on the next page ("Saved.")

// ------------------------------------------------------------------ helpers

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[c]);
}

function money(cents) {
  return `€${(cents / 100).toFixed(2)}`;
}

function catalogImage(path) {
  return path ? SERVICE_URLS.catalog + path : PLACEHOLDER_IMAGE;
}

// Draw a page, unless the visitor has already moved to another one.
function paint(token, html) {
  if (token !== renderToken) return false;
  app.innerHTML = (flash ? `<p class="message success">${esc(flash)}</p>` : "") + html;
  flash = "";
  // Pictures that fail to load (no image stored) show the placeholder.
  app.querySelectorAll("img").forEach((img) => {
    img.addEventListener("error", () => { img.src = PLACEHOLDER_IMAGE; }, { once: true });
  });
  return true;
}

function go(hash, message) {
  flash = message || "";
  if (location.hash === hash) render();
  else location.hash = hash;
}

function formData(form) {
  return Object.fromEntries(new FormData(form).entries());
}

// Run a form's action with its button disabled and errors shown under it.
function onSubmit(form, action) {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = form.querySelector("button[type=submit], button:not([type])");
    const errorBox = form.querySelector(".form-error");
    if (button) button.disabled = true;
    if (errorBox) errorBox.textContent = "";
    try {
      await action(formData(form), form);
    } catch (error) {
      if (error instanceof ServiceError && error.status === 401 && error.service === "catalog") {
        setAdminPassword(null);
        go("#/admin", "Please sign in again.");
        return;
      }
      if (errorBox) errorBox.innerHTML = explainInline(error);
      else showProblem(error);
    } finally {
      if (button) button.disabled = false;
    }
  });
}

// ------------------------------------------------- service status messages

waitListeners.start = () => {
  statusArea.innerHTML = `<p class="message info"><span class="spinner"></span>
    The shop is starting up. It sleeps when nobody is using it, so the first
    visit can take up to a minute. Please wait…</p>`;
};
waitListeners.stop = () => { statusArea.innerHTML = ""; };

// What still works when one service is down (partial failure).
const STILL_WORKS = {
  catalog: `The product catalog is not responding right now, so products and
    prices cannot be shown. Your cart is saved in this browser, and you can
    still look up an existing order below.`,
  orders: `The order service is not responding right now, so the cart and
    checkout are unavailable. You can still browse the products; your cart is
    saved in this browser.`,
};

function explainInline(error) {
  if (error instanceof ServiceError && error.unavailable) {
    return `${esc(STILL_WORKS[error.service])} <button type="button" class="text-button"
      onclick="render()">Try again</button>`;
  }
  return esc(error.message || "Something went wrong.");
}

// A whole page could not load: say which part is down and what still works.
function showProblem(error) {
  const unavailable = error instanceof ServiceError && error.unavailable;
  statusArea.innerHTML = "";
  app.innerHTML = `
    <section class="panel">
      <h1>${unavailable ? "Part of the shop is unavailable" : "Something went wrong"}</h1>
      <p>${unavailable ? esc(STILL_WORKS[error.service]) : esc(error.message)}</p>
      <button type="button" id="try-again">Try again</button>
      ${unavailable && error.service === "orders" ? '<a class="button" href="#/">Browse products</a>' : ""}
    </section>
    ${!unavailable || error.service === "catalog" ? orderLookupHtml() : ""}`;
  app.querySelector("#try-again").addEventListener("click", render);
  bindOrderLookup();
}

function orderLookupHtml() {
  return `
    <section class="panel form-panel">
      <h2>Look up an order</h2>
      <form id="order-lookup">
        <label for="lookup-id">Order number</label>
        <input id="lookup-id" name="order_id" inputmode="numeric" pattern="[0-9]+" required>
        <label for="lookup-email">Email used at checkout</label>
        <input id="lookup-email" name="email" type="email" required>
        <button type="submit">Find order</button>
      </form>
    </section>`;
}

function bindOrderLookup() {
  const form = app.querySelector("#order-lookup");
  if (!form) return;
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const { order_id: orderId, email } = formData(form);
    location.hash = `#/order/${encodeURIComponent(orderId.trim())}?email=${encodeURIComponent(email.trim())}`;
  });
}

// --------------------------------------------------------------- shop pages

async function shopPage(token) {
  const products = await callService("catalog", "/products");
  const cards = products.map((p) => `
    <a class="store-card" href="#/product/${p.id}">
      <img class="store-image" src="${esc(catalogImage(p.image_url))}" alt="">
      <div class="store-card-content">
        <h2>${esc(p.name)}</h2>
        <p class="price">${money(p.price_cents)}</p>
      </div>
    </a>`).join("");
  paint(token, `
    <h1>Shop</h1>
    ${products.length ? `<div class="store-grid">${cards}</div>` : '<p class="panel">No products yet.</p>'}
    ${orderLookupHtml()}`);
  bindOrderLookup();
}

async function productPage(token, id) {
  const product = await callService("catalog", `/products/${id}`);
  const options = product.variants.filter((v) => v.stock > 0);
  paint(token, `
    <a class="back-link" href="#/">← Back to the shop</a>
    <article class="product-detail">
      <img class="detail-image" src="${esc(catalogImage(product.image_url))}" alt="">
      <div>
        <h1>${esc(product.name)}</h1>
        <p class="price">${money(product.price_cents)}</p>
        <p>${esc(product.description)}</p>
        ${options.length ? `
          <form id="add-to-cart">
            <label for="variant">Option</label>
            <select id="variant" name="variant_id">
              ${options.map((v) => `<option value="${v.id}">${esc(v.option_label)} (${v.stock} left)</option>`).join("")}
            </select>
            <label for="quantity">Quantity</label>
            <input id="quantity" name="quantity" type="number" min="1" value="1" required>
            <button type="submit">Add to cart</button>
            <p class="form-error"></p>
          </form>` : "<p><strong>Sold out.</strong></p>"}
      </div>
    </article>`);
  const form = app.querySelector("#add-to-cart");
  if (!form) return;
  onSubmit(form, async (data) => {
    // Orders checks the live stock in the catalog before accepting the change.
    const result = await callService("orders", "/cart/add", {
      method: "POST", safeToRepeat: true,
      json: { cart: loadCart(), variant_id: Number(data.variant_id), quantity: Number(data.quantity) },
    });
    saveCart(result.cart);
    go("#/cart", "Added to your cart.");
  });
}

async function cartPage(token) {
  const cart = loadCart();
  if (!cart.length) {
    paint(token, '<h1>Your cart</h1><p class="panel">Your cart is empty. <a href="#/">Browse the shop</a></p>');
    return;
  }
  const summary = await callService("orders", "/cart/summary", { method: "POST", safeToRepeat: true, json: { cart } });

  // Options that are no longer for sale are left out of the summary; drop
  // them from the saved cart too so checkout does not fail on them.
  const forSale = new Set(summary.items.map((item) => item.variant_id));
  const kept = cart.filter((line) => forSale.has(line.variant_id));
  if (kept.length !== cart.length) {
    saveCart(kept);
    flash = "Some items are no longer for sale and were removed from your cart.";
  }
  const allInStock = summary.items.every((item) => item.has_enough_stock);

  paint(token, `
    <h1>Your cart</h1>
    <div class="cart-layout">
      <div class="cart-list panel">
        ${summary.items.map((item) => `
          <div class="cart-line">
            <img class="cart-image" src="${esc(SERVICE_URLS.catalog)}/variants/${item.variant_id}/image" alt="">
            <div>
              <h2>${esc(item.product_name)}</h2>
              <p>${esc(item.option_label)} · ${money(item.unit_price_cents)}</p>
              ${item.has_enough_stock ? "" : `<p class="form-error">Only ${item.stock} left. Lower the quantity.</p>`}
              <form class="cart-update" data-variant="${item.variant_id}">
                <label>Quantity <input name="quantity" type="number" min="1" value="${item.quantity}"></label>
                <button type="submit">Update</button>
                <button type="button" class="text-button remove">Remove</button>
                <p class="form-error"></p>
              </form>
            </div>
            <p class="line-subtotal">${money(item.line_total_cents)}</p>
          </div>`).join("")}
      </div>
      <aside class="cart-summary">
        <h2>Summary</h2>
        <div class="summary-total"><span>Total</span><strong>${money(summary.total_cents)}</strong></div>
        <a class="button checkout-button ${allInStock ? "" : "disabled"}" href="${allInStock ? "#/checkout" : "#/cart"}">Checkout</a>
      </aside>
    </div>`);

  app.querySelectorAll(".cart-update").forEach((form) => {
    const variantId = Number(form.dataset.variant);
    const update = async (quantity) => {
      const result = await callService("orders", "/cart/update", {
        method: "POST", safeToRepeat: true, json: { cart: loadCart(), variant_id: variantId, quantity },
      });
      saveCart(result.cart);
      go("#/cart", quantity === 0 ? "Removed." : "Cart updated.");
    };
    onSubmit(form, (data) => update(Number(data.quantity)));
    form.querySelector(".remove").addEventListener("click", () => {
      update(0).catch((error) => { form.querySelector(".form-error").innerHTML = explainInline(error); });
    });
  });
}

async function checkoutPage(token) {
  const cart = loadCart();
  if (!cart.length) {
    go("#/cart");
    return;
  }
  const summary = await callService("orders", "/cart/summary", { method: "POST", safeToRepeat: true, json: { cart } });
  paint(token, `
    <h1>Checkout</h1>
    <div class="checkout-layout">
      <form id="checkout" class="panel checkout-form">
        <h2>Your details</h2>
        <label for="name">Name</label>
        <input id="name" name="customer_name" autocomplete="name" required>
        <label for="email">Email</label>
        <input id="email" name="customer_email" type="email" autocomplete="email" required>
        <h2>Payment</h2>
        <label for="card">Card number</label>
        <input id="card" name="card_number" inputmode="numeric" autocomplete="off" required>
        <p class="hint">Fake payment: any card works, except one ending in 0000, which is declined.
          The card number is never stored.</p>
        <button type="submit">Pay ${money(summary.total_cents)}</button>
        <p class="form-error"></p>
      </form>
      <aside class="cart-summary">
        <h2>Order</h2>
        ${summary.items.map((item) => `
          <div class="summary-row"><span>${esc(item.product_name)} · ${esc(item.option_label)} × ${item.quantity}</span>
          <span>${money(item.line_total_cents)}</span></div>`).join("")}
        <div class="summary-total"><span>Total</span><strong>${money(summary.total_cents)}</strong></div>
      </aside>
    </div>`);

  onSubmit(app.querySelector("#checkout"), async (data) => {
    try {
      const result = await callService("orders", "/checkout", {
        method: "POST", json: { cart: loadCart(), ...data },
      });
      saveCart([]);
      go(`#/order/${result.order_id}?email=${encodeURIComponent(data.customer_email.trim())}`,
        "Thank you! Your payment went through.");
    } catch (error) {
      if (error instanceof ServiceError && error.status === 402) {
        throw new Error(`${error.message} Try another card.`);
      }
      throw error;
    }
  });
}

async function orderPage(token, id, query) {
  let order;
  try {
    order = await callService("orders", `/orders/${id}?email=${encodeURIComponent(query.get("email") || "")}`);
  } catch (error) {
    if (error instanceof ServiceError && error.status === 404) {
      paint(token, `<section class="panel"><h1>Order not found</h1>
        <p>Check the order number and the email you used at checkout.</p></section>${orderLookupHtml()}`);
      bindOrderLookup();
      return;
    }
    throw error;
  }
  paint(token, `
    <section class="panel confirmation-panel">
      <h1>Order #${order.id}</h1>
      <p>Status: <strong>${esc(order.status)}</strong> · ${esc(new Date(order.created_at).toLocaleString())}</p>
      <p>Thanks, ${esc(order.customer_name)}.</p>
      ${order.items.map((item) => `
        <div class="summary-row"><span>${esc(item.product_name)} · ${esc(item.option_label)} × ${item.quantity}</span>
        <span>${money(item.unit_price_cents * item.quantity)}</span></div>`).join("")}
      <div class="summary-total"><span>Total</span><strong>${money(order.total_cents)}</strong></div>
      <a class="button" href="#/">Continue shopping</a>
    </section>`);
}

// -------------------------------------------------------------- admin pages

function adminLoginPage(token, message) {
  paint(token, `
    <form id="login" class="panel narrow">
      <h1>Admin sign in</h1>
      ${message ? `<p class="form-error">${esc(message)}</p>` : ""}
      <label for="password">Password</label>
      <input id="password" name="password" type="password" autocomplete="current-password" required>
      <button type="submit">Sign in</button>
      <p class="form-error"></p>
    </form>`);
  onSubmit(app.querySelector("#login"), async (data) => {
    setAdminPassword(data.password);
    try {
      await callService("catalog", "/admin/products", { admin: true });
    } catch (error) {
      setAdminPassword(null);
      if (error instanceof ServiceError && error.status === 401) throw new Error("Wrong password.");
      throw error;
    }
    go("#/admin", "Signed in.");
  });
}

// Admin pages call this first; it shows the sign-in form when needed.
function signedIn(token) {
  if (adminPassword()) return true;
  adminLoginPage(token);
  return false;
}

async function adminCall(path, options = {}) {
  return callService("catalog", path, { ...options, admin: true });
}

async function adminListPage(token) {
  if (!signedIn(token)) return;
  const products = await adminCall("/admin/products");
  paint(token, `
    <div class="page-heading">
      <h1>Products</h1>
      <div class="form-actions">
        <a class="button" href="#/admin/new">Add product</a>
        <button type="button" id="sign-out" class="text-button">Sign out</button>
      </div>
    </div>
    ${products.length ? "" : '<p class="panel">No products yet.</p>'}
    <div class="product-list">
      ${products.map((p) => `
        <div class="panel product-card">
          <img class="product-image" src="${esc(catalogImage(p.image_url))}" alt="">
          <div>
            <h2>${esc(p.name)}</h2>
            <p class="price">${money(p.price_cents)}</p>
            <p>${p.variants.map((v) => `${esc(v.option_label)}: ${v.stock}`).join(" · ") || "No options"}</p>
            <div class="form-actions">
              <a class="button" href="#/admin/product/${p.id}">Edit</a>
              <button type="button" class="text-button remove-product" data-id="${p.id}"
                data-name="${esc(p.name)}">Remove from shop</button>
            </div>
          </div>
        </div>`).join("")}
    </div>`);
  app.querySelector("#sign-out").addEventListener("click", () => {
    setAdminPassword(null);
    go("#/admin", "Signed out.");
  });
  app.querySelectorAll(".remove-product").forEach((button) => {
    button.addEventListener("click", async () => {
      if (!confirm(`Remove "${button.dataset.name}" from the shop? Past orders keep their details.`)) return;
      try {
        await adminCall(`/admin/products/${button.dataset.id}`, { method: "DELETE" });
        go("#/admin", "Product removed from the shop.");
      } catch (error) {
        showProblem(error);
      }
    });
  });
}

function optionRowHtml(label = "", stock = 0) {
  return `<div class="option-row">
      <input name="option_label" placeholder="Option, e.g. Blue" value="${esc(label)}" required>
      <input name="stock" type="number" min="0" value="${stock}" required aria-label="Stock">
      <button type="button" class="text-button remove-option">Remove</button>
    </div>`;
}

async function uploadImage(productId, file) {
  if (file.size > MAX_IMAGE_BYTES) throw new Error("The image is larger than 5 MB.");
  const body = new FormData();
  body.append("image", file);
  await adminCall(`/admin/products/${productId}/image`, { method: "PUT", body });
}

function adminNewPage(token) {
  if (!signedIn(token)) return;
  paint(token, `
    <a class="back-link" href="#/admin">← Products</a>
    <form id="new-product" class="panel form-panel">
      <h1>Add product</h1>
      <label for="name">Name</label>
      <input id="name" name="name" required>
      <label for="description">Description</label>
      <textarea id="description" name="description" rows="3"></textarea>
      <label for="price">Price (€)</label>
      <input id="price" name="price" inputmode="decimal" placeholder="12.50" required>
      <label>Options and stock</label>
      <div id="options">${optionRowHtml()}</div>
      <button type="button" id="add-option" class="text-button">+ Add option</button>
      <label for="image">Picture (optional, up to 5 MB: png, jpg, gif, webp)</label>
      <input id="image" name="image" type="file" accept="image/png,image/jpeg,image/gif,image/webp">
      <button type="submit">Save product</button>
      <p class="form-error"></p>
    </form>`);
  const form = app.querySelector("#new-product");
  const options = form.querySelector("#options");
  form.querySelector("#add-option").addEventListener("click", () => {
    options.insertAdjacentHTML("beforeend", optionRowHtml());
  });
  options.addEventListener("click", (event) => {
    // Keep at least one option row.
    if (event.target.matches(".remove-option") && options.children.length > 1) {
      event.target.closest(".option-row").remove();
    }
  });
  onSubmit(form, async (data, element) => {
    const variants = [...element.querySelectorAll(".option-row")].map((row) => ({
      option_label: row.querySelector("[name=option_label]").value,
      stock: Number(row.querySelector("[name=stock]").value),
    }));
    const created = await adminCall("/admin/products", {
      method: "POST",
      json: { name: data.name, description: data.description, price: data.price, variants },
    });
    const file = element.querySelector("#image").files[0];
    if (file) {
      try {
        await uploadImage(created.id, file);
      } catch (error) {
        go(`#/admin/product/${created.id}`, `Product saved, but the picture was not: ${error.message}`);
        return;
      }
    }
    go(`#/admin/product/${created.id}`, "Product saved.");
  });
}

async function adminEditPage(token, id) {
  if (!signedIn(token)) return;
  const product = await adminCall(`/admin/products/${id}`);
  const here = `#/admin/product/${id}`;
  // ?v= makes the browser fetch a freshly uploaded picture instead of its cached copy.
  const picture = product.image_url ? `${catalogImage(product.image_url)}?v=${Date.now()}` : PLACEHOLDER_IMAGE;
  paint(token, `
    <a class="back-link" href="#/admin">← Products</a>
    <h1>Edit ${esc(product.name)}</h1>
    ${product.is_active ? "" : "<p class=\"message info\">This product has been removed from the shop.</p>"}
    <form id="details" class="panel form-panel">
      <h2>Details</h2>
      <label for="name">Name</label>
      <input id="name" name="name" value="${esc(product.name)}" required>
      <label for="description">Description</label>
      <textarea id="description" name="description" rows="3">${esc(product.description)}</textarea>
      <label for="price">Price (€)</label>
      <input id="price" name="price" inputmode="decimal" value="${(product.price_cents / 100).toFixed(2)}" required>
      <button type="submit">Save details</button>
      <p class="form-error"></p>
    </form>
    <form id="picture" class="panel form-panel">
      <h2>Picture</h2>
      <img class="product-image" src="${esc(picture)}" alt="">
      <input name="image" type="file" accept="image/png,image/jpeg,image/gif,image/webp" required>
      <button type="submit">Upload picture</button>
      <p class="form-error"></p>
    </form>
    <section class="panel form-panel">
      <h2>Options and stock</h2>
      ${product.variants.map((v) => `
        <form class="variant" data-id="${v.id}">
          <div class="option-row">
            <input name="option_label" value="${esc(v.option_label)}" required aria-label="Option">
            <input name="stock" type="number" min="0" value="${v.stock}" required aria-label="Stock">
            <button type="submit">Save</button>
            <button type="button" class="text-button take-off-sale">Take off sale</button>
          </div>
          <p class="form-error"></p>
        </form>`).join("")}
      <form id="new-variant">
        <h3>Add an option</h3>
        ${optionRowHtml().replace(/<button[^>]*remove-option[^>]*>Remove<\/button>/, '<button type="submit">Add</button>')}
        <p class="form-error"></p>
      </form>
    </section>`);

  onSubmit(app.querySelector("#details"), async (data) => {
    await adminCall(`/admin/products/${id}`, { method: "PUT", json: data });
    go(here, "Details saved.");
  });
  onSubmit(app.querySelector("#picture"), async (data, form) => {
    await uploadImage(id, form.querySelector("[name=image]").files[0]);
    go(here, "Picture uploaded.");
  });
  app.querySelectorAll("form.variant").forEach((form) => {
    const path = `/admin/products/${id}/variants/${form.dataset.id}`;
    onSubmit(form, async (data) => {
      await adminCall(path, { method: "PUT", json: { option_label: data.option_label, stock: Number(data.stock) } });
      go(here, "Option saved.");
    });
    form.querySelector(".take-off-sale").addEventListener("click", async () => {
      try {
        await adminCall(path, { method: "DELETE" });
        go(here, "Option taken off sale (stock set to 0).");
      } catch (error) {
        form.querySelector(".form-error").innerHTML = explainInline(error);
      }
    });
  });
  onSubmit(app.querySelector("#new-variant"), async (data) => {
    await adminCall(`/admin/products/${id}/variants`, {
      method: "POST", json: { option_label: data.option_label, stock: Number(data.stock) },
    });
    go(here, "Option added.");
  });
}

// ------------------------------------------------------------------- router

const ROUTES = [
  [/^\/?$/, shopPage],
  [/^\/product\/(\d+)$/, productPage],
  [/^\/cart$/, cartPage],
  [/^\/checkout$/, checkoutPage],
  [/^\/order\/(\d+)$/, orderPage],
  [/^\/admin$/, adminListPage],
  [/^\/admin\/new$/, adminNewPage],
  [/^\/admin\/product\/(\d+)$/, adminEditPage],
];

async function render() {
  renderToken += 1;
  const token = renderToken;
  const [path, queryString] = location.hash.replace(/^#/, "").split("?");
  const query = new URLSearchParams(queryString || "");
  statusArea.innerHTML = "";
  showCartCount();
  window.scrollTo(0, 0);

  const route = ROUTES.find(([pattern]) => pattern.test(path));
  if (!route) {
    paint(token, '<section class="panel"><h1>Page not found</h1><a href="#/">Back to the shop</a></section>');
    return;
  }
  const [pattern, page] = route;
  const match = path.match(pattern);
  try {
    await page(token, match[1], query);
  } catch (error) {
    if (token !== renderToken) return;
    if (error instanceof ServiceError && error.status === 401 && error.service === "catalog") {
      setAdminPassword(null);
      adminLoginPage(token, "Please sign in again.");
      return;
    }
    if (error instanceof ServiceError && error.status === 404) {
      paint(token, `<section class="panel"><h1>Not found</h1><p>${esc(error.message)}</p>
        <a href="#/">Back to the shop</a></section>`);
      return;
    }
    showProblem(error);
  }
}

window.addEventListener("hashchange", render);
// Another tab changed the cart: update the count in the top bar.
window.addEventListener("storage", showCartCount);
render();
