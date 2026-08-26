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
                const productID = button.dataset.id;
                console.log("Clicked product id:", productID);
            });
        }

    } catch (error) {
        console.error(error.message);
    }
}
getData();