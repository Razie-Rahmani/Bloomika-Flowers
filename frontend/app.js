let cart = [];

const viewCart = document.getElementById("view-cart-btn");
viewCart.addEventListener("click", function() {renderCart()})

async function placeOrder(orderData) {
    try {
        const response = await fetch("http://127.0.0.1:8000/orders/", {
            method: "POST",
            headers: { "Content-Type": "application/json"},
            body: JSON.stringify(orderData)
        });
        const result = await response.json();
        console.log(result);

        const cartSection = document.getElementById("cart-section");
        cartSection.innerHTML = `<p>Order #${result.order_id} placed successfully!<br>Total: ${result.total_price}</p>`;
        
    } catch (error) {
        console.error(error.message);
    }
}

async function getData() {
    const url = "http://127.0.0.1:8000/products";
    try {
        const response = await fetch(url);
        if (!response.ok) {
            throw new Error (`Response status: ${response.status}`);
        }

        const result = await response.json();
        console.log(result);

        let html = "";
        for (let item of result) {
            html += `<div>${item.name} - ${item.price} <button class="add-to-cart-btn" data-id="${item.id}">Add to Cart</button></div>`;
        }

        const catalogSection = document.getElementById("catalog-section");
        catalogSection.innerHTML = html;

        const buttons = document.querySelectorAll(".add-to-cart-btn");
        for (let button of buttons) {
            button.addEventListener("click", function() {
                const productID = Number(button.dataset.id);
                function isAlreadyAdded(cartItem) {
                    return cartItem.id === productID;
                }

                const existingItem = cart.find(isAlreadyAdded);

                if (existingItem) {
                    existingItem.quantity += 1;
                } else {
                    const product = result.find(p => p.id === productID);
                    cart.push({id: productID, name: product.name, price: product.price, quantity: 1})
                };
                console.log(cart);
            });
        }

    } catch (error) {
        console.error(error.message);
    }
}
getData();

function renderCart() {
    try {
        const catalogSection = document.getElementById("catalog-section");
        const cartSection = document.getElementById("cart-section");

        catalogSection.style.display = "none";
        cartSection.style.display = "block";

        if (cart.length === 0) {
            cartSection.innerHTML = `<button id="back-to-catalog-btn">Back to Catalog</button><p>Cart is empty.</p>`;
        } else {        
            let totalPrice = 0;
            let html = `<button id="back-to-catalog-btn">Back to Catalog</button>`;
            for (let item of cart) {
                totalPrice += item.quantity*item.price;
                html += `<div>${item.name} - ${item.price} - ${item.quantity}</div>`;
            }

            html += `<div id="total-price">Total Price: ${totalPrice}</div>`
            html += `<p><label for="name">Name:</label><input type="text" id="name" /></p>`
            html += `<p><label for="address">Address:</label><input type="text" id="address" /></p>`
            html += `<p><label for="postal_code">Postal Code:</label><input type="text" id="postal_code" /></p>`
            html += `<p><label for="phone_number">Phone Number:</label><input type="text" id="phone_number" /></p>`
            html += `<button type="button" id="place-order-btn">Place Order.</button>`

            cartSection.innerHTML = html;

            const placeOrderBtn = document.getElementById("place-order-btn");
            placeOrderBtn.addEventListener("click", function() {
                const items = cart.reduce((acc, item) => {
                    acc[item.name] = item.quantity;
                    return acc;
                }, {});
                const orderData = {
                    customer_name: document.getElementById("name").value,
                    address: document.getElementById("address").value,
                    postal_code: document.getElementById("postal_code").value,
                    phone_number: document.getElementById("phone_number").value,
                    items: items,
                    total_price: totalPrice
                };
                placeOrder(orderData);
            })

        }
        const backToCatalog = document.getElementById("back-to-catalog-btn");
        backToCatalog.addEventListener("click", function() {
            catalogSection.style.display = "block";
            cartSection.style.display = "none";
        })

    } catch(error) {
        console.error(error.message)
    }

}