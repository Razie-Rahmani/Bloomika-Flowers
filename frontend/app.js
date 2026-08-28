let cart = [];

const viewCart = document.getElementById("view-cart-btn");
viewCart.addEventListener("click", function() {renderCart()})

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
            let html = `<button id="back-to-catalog-btn">Back to Catalog</button>`;
            for (let item of cart) {
                html += `<div>${item.name} - ${item.price} - ${item.quantity}</div>`;
            }
            cartSection.innerHTML = html;
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