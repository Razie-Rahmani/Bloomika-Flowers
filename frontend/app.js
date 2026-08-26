let cart = [];

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
            html += `<div>${item.name} - ${item.price} <button data-id="${item.id}">Add to Cart</button></div>`;
        }

        const catalogSection = document.getElementById("catalog-section");
        catalogSection.innerHTML = html;

        const buttons = document.querySelectorAll("button");
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