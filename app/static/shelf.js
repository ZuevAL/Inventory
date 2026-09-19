const form = document.querySelector("#shelf-form");
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

form.addEventListener("submit", async (event) => {
    event.preventDefault();
    button.disabled = true;
    message.textContent = "Сохранение...";
    message.className = "";

    const code = form.elements.code.value.trim();

    try {
        const response = await fetch("/api/v1/shelves/", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({code})
        });

        if (!response.ok) {
            throw new Error(await getErrorMessage(response, "Не удалось создать полку"));
        }

        const shelf = await response.json();
        const idText = shelf.id == null ? "" : ` ID: ${shelf.id}`;
        message.textContent = `Полка ${shelf.code || code} создана.${idText}`;
        message.className = "success";
        form.reset();
        form.elements.code.focus();
    } catch (error) {
        message.textContent = error.message;
        message.className = "error";
    } finally {
        button.disabled = false;
    }
});
