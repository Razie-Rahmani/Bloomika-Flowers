let cart = [];

/* ========================================
   Inline SVG icons (no emoji — accessible, theme-colored via currentColor)
   ======================================== */
const ICONS = {
    backArrow: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M19 12H5"></path><path d="M12 19l-7-7 7-7"></path></svg>`,
    check: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 6 9 17l-5-5"></path></svg>`,
    flower: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="2.2"></circle><path d="M12 9.8c-1.5 0-2.7-1.2-2.7-2.7S10.5 4.4 12 4.4s2.7 1.2 2.7 2.7-1.2 2.7-2.7 2.7Z"></path><path d="M12 14.2c1.5 0 2.7 1.2 2.7 2.7s-1.2 2.7-2.7 2.7-2.7-1.2-2.7-2.7 1.2-2.7 2.7-2.7Z"></path><path d="M14.2 12c0-1.5 1.2-2.7 2.7-2.7s2.7 1.2 2.7 2.7-1.2 2.7-2.7 2.7-2.7-1.2-2.7-2.7Z"></path><path d="M9.8 12c0 1.5-1.2 2.7-2.7 2.7S4.4 13.5 4.4 12s1.2-2.7 2.7-2.7 2.7 1.2 2.7 2.7Z"></path></svg>`,
    emptyCart: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><circle cx="9" cy="21" r="1"></circle><circle cx="20" cy="21" r="1"></circle><path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6"></path></svg>`,
    alert: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>`
};

const API_BASE = "https://bloomika-flowers.onrender.com";
const customerTelegramId = window.Telegram?.WebApp?.initDataUnsafe?.user?.id;

const catalogSection = document.getElementById("catalog-section");
const cartSection = document.getElementById("cart-section");
const viewCartBtn = document.getElementById("view-cart-btn");
const cartCountBadge = document.getElementById("cart-count");

viewCartBtn.addEventListener("click", function () {
    renderCart();
});

function escapeHtml(value) {
    const div = document.createElement("div");
    div.textContent = String(value);
    return div.innerHTML;
}

function updateCartBadge() {
    const totalItems = cart.reduce((sum, item) => sum + item.quantity, 0);
    if (totalItems > 0) {
        cartCountBadge.textContent = totalItems > 99 ? "99+" : totalItems;
        cartCountBadge.hidden = false;
    } else {
        cartCountBadge.hidden = true;
    }
}

/* ========================================
   Order placement
   Payment receipts are no longer uploaded from here — the customer sends
   the receipt photo directly to the bot in Telegram, and the backend
   matches it to their most recent order via customer_telegram_id. See
   the `customer_receipt_photo` handler in backend/main.py.
   ======================================== */
async function placeOrder(orderData, placeOrderBtn) {
    const originalContent = placeOrderBtn.innerHTML;
    placeOrderBtn.disabled = true;
    placeOrderBtn.innerHTML = `<span class="btn-spinner" aria-hidden="true"></span> در حال ثبت سفارش...`;

    try {
        const response = await fetch(`${API_BASE}/orders/`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(orderData)
        });

        if (!response.ok) {
            throw new Error(`Response status: ${response.status}`);
        }

        const result = await response.json();

        let itemsHtml = "";
        for (let name in result.items) {
            itemsHtml += `<div class="cart-item"><span class="cart-item-name">${escapeHtml(name)}</span><span class="cart-item-meta">×${escapeHtml(result.items[name])}</span></div>`;
        }

        cartSection.innerHTML = `
            <p class="order-confirmation-title">${ICONS.check} سفارش شما با کد #${escapeHtml(result.order_id)} ثبت شد</p>
            <div class="cart-item-list">${itemsHtml}</div>
            <div id="total-price">مبلغ قابل پرداخت: ${escapeHtml(result.total_price)} تومان</div>
            <p>لطفاً مبلغ را به شماره کارت زیر واریز کنید:</p>
            <div class="payment-card-number">0000-0000-0000-0000<br>ملیکا عبیدانی</div>
            <p>سپس تصویر رسید پرداخت را <strong>همین‌جا در چت ربات</strong> ارسال کنید تا سفارش شما توسط ادمین تأیید شود.</p>
        `;

        cart = [];
        updateCartBadge();

    } catch (error) {
        console.error(error.message);
        placeOrderBtn.disabled = false;
        placeOrderBtn.innerHTML = originalContent;
        cartSection.insertAdjacentHTML("afterbegin", `<p class="field-error-msg">ثبت سفارش ناموفق بود. لطفاً دوباره تلاش کنید.</p>`);
    }
}

/* ========================================
   Catalog loading
   ======================================== */
async function getData() {
    const url = `${API_BASE}/products`;
    try {
        const response = await fetch(url);
        if (!response.ok) {
            throw new Error(`Response status: ${response.status}`);
        }

        const result = await response.json();
        catalogSection.setAttribute("aria-busy", "false");

        if (!result.length) {
            catalogSection.innerHTML = `
                <div class="empty-state">
                    ${ICONS.flower}
                    <p>در حال حاضر محصولی موجود نیست. بعداً دوباره سر بزنید!</p>
                </div>`;
            return;
        }

        let html = "";
        for (let item of result) {
            const media = item.image_url
                ? `<img class="product-photo" src="${escapeHtml(API_BASE + item.image_url)}" alt="${escapeHtml(item.name)}" loading="lazy">`
                : `<div class="product-icon">${ICONS.flower}</div>`;
            html += `
                <div class="product-card">
                    ${media}
                    <span class="product-name">${escapeHtml(item.name)}</span>
                    <span class="price">${escapeHtml(item.price)} تومان</span>
                    <button type="button" class="add-to-cart-btn" data-id="${item.id}">افزودن به سبد</button>
                </div>`;
        }

        catalogSection.innerHTML = html;

        const buttons = document.querySelectorAll(".add-to-cart-btn");
        for (let button of buttons) {
            button.addEventListener("click", function () {
                const productID = Number(button.dataset.id);

                const existingItem = cart.find(cartItem => cartItem.id === productID);
                if (existingItem) {
                    existingItem.quantity += 1;
                } else {
                    const product = result.find(p => p.id === productID);
                    cart.push({ id: productID, name: product.name, price: product.price, quantity: 1 });
                }

                updateCartBadge();

                const originalLabel = button.textContent;
                button.classList.add("just-added");
                button.textContent = "اضافه شد";
                setTimeout(() => {
                    button.classList.remove("just-added");
                    button.textContent = originalLabel;
                }, 900);
            });
        }

    } catch (error) {
        console.error(error.message);
        catalogSection.setAttribute("aria-busy", "false");
        catalogSection.innerHTML = `
            <div class="error-state">
                ${ICONS.alert}
                <p>خطا در بارگذاری محصولات. اتصال اینترنت خود را بررسی و دوباره تلاش کنید.</p>
                <button type="button" id="retry-load-btn">تلاش دوباره</button>
            </div>`;
        const retryBtn = document.getElementById("retry-load-btn");
        if (retryBtn) {
            retryBtn.addEventListener("click", () => {
                catalogSection.setAttribute("aria-busy", "true");
                catalogSection.innerHTML = `
                    <div class="loading-state">
                        <span class="spinner" aria-hidden="true"></span>
                        <p>در حال بارگذاری محصولات...</p>
                    </div>`;
                getData();
            });
        }
    }
}
getData();

/* ========================================
   Cart rendering
   ======================================== */
function renderCart() {
    try {
        catalogSection.style.display = "none";
        cartSection.style.display = "block";

        if (cart.length === 0) {
            cartSection.innerHTML = `
                <button type="button" id="back-to-catalog-btn">${ICONS.backArrow} بازگشت به فروشگاه</button>
                <div class="empty-state">
                    ${ICONS.emptyCart}
                    <p>سبد خرید شما خالی است.</p>
                </div>`;
        } else {
            let totalPrice = 0;
            let html = `<button type="button" id="back-to-catalog-btn">${ICONS.backArrow} بازگشت به فروشگاه</button>`;
            for (let item of cart) {
                totalPrice += item.quantity * item.price;
                html += `<div class="cart-item"><span class="cart-item-name">${escapeHtml(item.name)}</span><span class="cart-item-meta">${escapeHtml(item.price)} تومان × ${escapeHtml(item.quantity)}</span></div>`;
            }

            html += `<div id="total-price">مبلغ کل: ${escapeHtml(totalPrice)} تومان</div>`;
            html += `
                <form id="checkout-form">
                    <div class="field"><label for="name">نام و نام خانوادگی</label><input type="text" id="name" required /></div>
                    <div class="field"><label for="address">آدرس</label><input type="text" id="address" required /></div>
                    <div class="field"><label for="postal-code">کد پستی</label><input type="text" id="postal-code" inputmode="numeric" required /></div>
                    <div class="field"><label for="phone-number">شماره تماس</label><input type="tel" id="phone-number" inputmode="tel" required /></div>
                    <button type="submit" id="place-order-btn">ثبت سفارش</button>
                </form>`;

            cartSection.innerHTML = html;

            const checkoutForm = document.getElementById("checkout-form");
            checkoutForm.addEventListener("submit", function (event) {
                event.preventDefault();

                const fields = [
                    ["name", "customer_name"],
                    ["address", "address"],
                    ["postal-code", "postal_code"],
                    ["phone-number", "phone_number"]
                ];

                let hasError = false;
                const values = {};
                for (const [fieldId, key] of fields) {
                    const input = document.getElementById(fieldId);
                    const value = input.value.trim();
                    input.classList.toggle("field-error", value === "");
                    if (value === "") hasError = true;
                    values[key] = value;
                }
                if (hasError) return;

                const items = cart.reduce((acc, item) => {
                    acc[item.name] = item.quantity;
                    return acc;
                }, {});

                const orderData = {
                    customer_telegram_id: String(customerTelegramId),
                    customer_name: values.customer_name,
                    address: values.address,
                    postal_code: values.postal_code,
                    phone_number: values.phone_number,
                    items: items,
                    total_price: totalPrice
                };

                placeOrder(orderData, document.getElementById("place-order-btn"));
            });
        }

        const backToCatalog = document.getElementById("back-to-catalog-btn");
        backToCatalog.addEventListener("click", function () {
            catalogSection.style.display = "";
            cartSection.style.display = "none";
        });

    } catch (error) {
        console.error(error.message);
    }
}