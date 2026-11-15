"use strict";

// Списки справа от формы: сначала первые 5 записей, кнопка ниже раскрывает всю таблицу.
(() => {
    const PAGE = 5;
    const BATCH = 100;

    const configs = {
        products: {
            title: "Добавленные товары",
            columns: ["Название", "Штрихкод"],
            path: "/products/",
            empty: "В каталоге пока нет товаров.",
            row: item => [item.name, item.barcode],
        },
        shelves: {
            title: "Добавленные полки",
            columns: ["Код полки"],
            path: "/shelves/",
            empty: "Пока не создано ни одной полки.",
            row: item => [item.code],
        },
        stock: {
            title: "Товары на полках",
            columns: ["Товар", "Штрихкод", "Полка", "Количество"],
            path: "/stock/",
            empty: "Товары ещё не размещены на полках.",
            row: item => [item.product_name, item.product_barcode, item.shelf_code, item.quantity],
        },
    };

    function build(panel, config) {
        const head = document.createElement("div");
        head.className = "list-head";
        const title = document.createElement("h2");
        title.textContent = config.title;
        const count = document.createElement("span");
        count.className = "list-count";
        head.append(title, count);

        const empty = document.createElement("p");
        empty.className = "hint list-empty";
        empty.textContent = config.empty;
        empty.hidden = true;

        const scroll = document.createElement("div");
        scroll.className = "table-scroll";
        scroll.hidden = true;
        const table = document.createElement("table");
        table.id = "inventory-list-table";
        table.setAttribute("aria-label", config.title);
        const headRow = document.createElement("tr");
        for (const name of config.columns) {
            const th = document.createElement("th");
            th.scope = "col";
            th.textContent = name;
            headRow.append(th);
        }
        const thead = document.createElement("thead");
        thead.append(headRow);
        const tbody = document.createElement("tbody");
        table.append(thead, tbody);
        scroll.append(table);

        const toggle = document.createElement("button");
        toggle.type = "button";
        toggle.className = "secondary list-toggle";
        toggle.textContent = "Показать все";
        toggle.hidden = true;
        toggle.setAttribute("aria-controls", table.id);
        toggle.setAttribute("aria-expanded", "false");

        const status = document.createElement("p");
        status.className = "hint list-status";
        status.setAttribute("role", "status");
        const retry = document.createElement("button");
        retry.type = "button";
        retry.className = "secondary list-toggle";
        retry.textContent = "Повторить загрузку";
        retry.hidden = true;

        panel.append(head, status, empty, scroll, toggle, retry);
        return { count, empty, scroll, tbody, toggle, status, retry };
    }

    async function fetchAll(path) {
        const items = [];
        for (let offset = 0; ; offset += BATCH) {
            const batch = await InventoryApi.api(`${path}?offset=${offset}&limit=${BATCH}`);
            items.push(...batch);
            if (batch.length < BATCH) return items;
        }
    }

    function render(ui, config, items, expanded) {
        ui.tbody.replaceChildren();
        for (const item of items) {
            const row = document.createElement("tr");
            for (const value of config.row(item)) {
                const cell = document.createElement("td");
                cell.textContent = value ?? "—";
                row.append(cell);
            }
            ui.tbody.append(row);
        }
        const empty = items.length === 0;
        ui.empty.hidden = !empty;
        ui.scroll.hidden = empty;
        ui.count.textContent = empty ? "" : expanded ? `Всего: ${items.length}` : `Показано: ${items.length}`;
        // Five rows may be the entire result; only expanding can determine that.
        ui.toggle.hidden = !expanded && items.length < PAGE;
        ui.toggle.textContent = expanded ? "Свернуть" : "Показать все";
        ui.toggle.setAttribute("aria-expanded", String(expanded));
    }

    function init() {
        const panel = document.querySelector("[data-list]");
        if (!panel) return;
        const config = configs[panel.dataset.list];
        if (!config) return;

        const ui = build(panel, config);
        const state = { expanded: false, request: 0 };

        async function load(expanded = state.expanded) {
            const request = ++state.request;
            panel.setAttribute("aria-busy", "true");
            ui.toggle.disabled = true;
            ui.retry.hidden = true;
            ui.status.hidden = false;
            ui.status.className = "hint list-status";
            ui.status.textContent = "Загрузка списка…";
            try {
                const items = expanded
                    ? await fetchAll(config.path)
                    : await InventoryApi.api(`${config.path}?offset=0&limit=${PAGE}`);
                // A form submission can trigger a newer load before this one finishes.
                if (request !== state.request) return;
                state.expanded = expanded;
                render(ui, config, items, expanded);
                ui.status.hidden = true;
            } catch (error) {
                if (request !== state.request) return;
                ui.status.className = "error list-status";
                ui.status.textContent = "Не удалось загрузить список. Повторите попытку.";
                ui.retry.hidden = false;
                if (error.status === 401) InventoryApi.fail(error);
            } finally {
                if (request === state.request) {
                    panel.setAttribute("aria-busy", "false");
                    ui.toggle.disabled = false;
                }
            }
        }

        ui.toggle.addEventListener("click", () => load(!state.expanded));
        ui.retry.addEventListener("click", () => load());
        document.addEventListener("inventory:changed", () => load());

        load();
    }

    // auth.js can finish before this deferred script has been downloaded.
    if (InventoryApi.ready) init();
    else document.addEventListener("inventory:ready", init, { once: true });
})();
