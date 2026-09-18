const form = document.querySelector("#product-form");
    const message = document.querySelector("#message");
    const button = form.querySelector("button");

    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        button.disabled = true;
        message.textContent = "Сохранение...";
        message.className = "";

        const data = new FormData(form);

        try {
            const response = await fetch("/api/v1/products/", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({
                    name: data.get("name"),
                    barcode: data.get("barcode")
                })
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || "Не удалось сохранить товар");
            }

            const product = await response.json();
            message.textContent = `Товар сохранён. ID: ${product.id}`;
            message.className = "success";
            form.reset();
            form.name.focus();
        } catch (error) {
            message.textContent = error.message;
            message.className = "error";
        } finally {
            button.disabled = false;
        }
    });