const form = document.querySelector("#shelf-stock-form");
const message = document.querySelector("#message");
const button = form.querySelector("button");

async function getErrorMessage(response, fallback) {
    try {
        const error = await response.json();
        if (typeof error.detail === "string") {
            return error.detail;
        }
    } catch {
        // Сервер мог вернуть ответ без JSON.
    }
    return fallback;
}

async function findByValue(url, notFoundMessage) {
    const response = await fetch(url);
    if (!response.ok) {
        throw new Error(await getErrorMessage(response, notFoundMessage));
    }

    const item = await response.json();
    if (item.id == null) {
        throw new Error(notFoundMessage);
    }
    return item;
}

form.addEventListener("submit", async (event) => {
    event.preventDefault();
    button.disabled = true;
    message.textContent = "Поиск товара и полки...";
    message.className = "";

    const barcode = form.elements.barcode.value.trim();
    const shelfCode = form.elements.shelf_code.value.trim();
    const quantity = Number(form.elements.quantity.value);

    try {
        const [product, shelf] = await Promise.all([
            findByValue(
                `/api/v1/products/by-barcode/${encodeURIComponent(barcode)}`,
                `Товар со штрихкодом ${barcode} не найден`
            ),
            findByValue(
                `/api/v1/shelves/by-code/${encodeURIComponent(shelfCode)}`,
                `Полка с кодом ${shelfCode} не найдена`
            )
        ]);

        message.textContent = "Сохранение...";
        const response = await fetch("/api/v1/shelf-stock/", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({
                product_id: product.id,
                shelf_id: shelf.id,
                quantity
            })
        });

        if (!response.ok) {
            throw new Error(await getErrorMessage(response, "Не удалось добавить товар на полку"));
        }

        message.textContent = `${product.name || "Товар"} добавлен на полку ${shelf.code || shelfCode}.`;
        message.className = "success";
        form.reset();
        form.elements.quantity.value = "1";
        form.elements.barcode.focus();
    } catch (error) {
        message.textContent = error.message;
        message.className = "error";
    } finally {
        button.disabled = false;
    }
});
