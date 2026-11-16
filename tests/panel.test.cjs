const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");

const source = fs.readFileSync(path.join(__dirname, "../app/static/panel.js"), "utf8");

class Element {
    constructor(tag) {
        this.tag = tag;
        this.children = [];
        this.attributes = {};
        this.listeners = {};
        this.hidden = false;
        this.disabled = false;
        this.textContent = "";
    }
    append(...children) { this.children.push(...children); }
    replaceChildren(...children) { this.children = children; }
    setAttribute(name, value) { this.attributes[name] = value; }
    addEventListener(name, callback, options) {
        (this.listeners[name] ||= []).push({ callback, once: options?.once });
    }
    async emit(name) {
        const listeners = this.listeners[name] || [];
        this.listeners[name] = listeners.filter(listener => !listener.once);
        await Promise.all(listeners.map(listener => listener.callback()));
    }
    find(tag) {
        if (this.tag === tag) return this;
        for (const child of this.children) {
            const match = child.find(tag);
            if (match) return match;
        }
    }
}

function browser(kind, api, ready = false) {
    const panel = new Element("section");
    panel.dataset = { list: kind };
    const document = new Element("document");
    document.createElement = tag => new Element(tag);
    document.querySelector = () => panel;
    const failures = [];
    const context = { document, InventoryApi: { api, ready, fail: error => failures.push(error) } };
    vm.runInNewContext(source, context);
    return {
        document, panel, failures,
        get rows() { return panel.find("tbody")?.children; },
        get toggle() { return panel.children[4]; },
        get retry() { return panel.children[5]; },
        get status() { return panel.children[1]; },
        get count() { return panel.children[0].children[1]; },
        get empty() { return panel.children[2]; },
        get scroll() { return panel.children[3]; },
    };
}

const settle = () => new Promise(setImmediate);
const products = count => Array.from({ length: count }, (_, id) => ({
    id, name: `Товар ${id}`, barcode: `000${id}`,
}));
function paged(items, calls = []) {
    return async path => {
        calls.push(path);
        const params = new URL(path, "http://inventory.test").searchParams;
        const offset = Number(params.get("offset"));
        return items.slice(offset, offset + Number(params.get("limit")));
    };
}
async function start(view) {
    await view.document.emit("inventory:ready");
    await settle();
}

test("loads five rows only after authentication, expands all batches and collapses", async () => {
    const calls = [];
    const view = browser("products", paged(products(205), calls));
    assert.deepEqual(calls, []);
    await start(view);
    assert.deepEqual(calls, ["/products/?offset=0&limit=5"]);
    assert.equal(view.rows.length, 5);
    assert.equal(view.toggle.hidden, false);
    assert.equal(view.toggle.attributes["aria-expanded"], "false");

    await view.toggle.emit("click");
    assert.equal(view.rows.length, 205);
    assert.equal(view.count.textContent, "Всего: 205");
    assert.equal(view.toggle.textContent, "Свернуть");
    assert.equal(view.toggle.attributes["aria-expanded"], "true");
    assert.deepEqual(calls.slice(1), [
        "/products/?offset=0&limit=100",
        "/products/?offset=100&limit=100",
        "/products/?offset=200&limit=100",
    ]);

    await view.toggle.emit("click");
    assert.equal(view.rows.length, 5);
    assert.equal(view.toggle.textContent, "Показать все");
    assert.equal(view.toggle.attributes["aria-expanded"], "false");
});

test("initializes when authentication finishes before panel.js loads", async () => {
    const view = browser("shelves", paged([{ code: "A-1" }]), true);
    await settle();
    assert.equal(view.rows[0].children[0].textContent, "A-1");
    assert.equal(view.toggle.hidden, true);
});

test("stock rows show product name, barcode, shelf code and zero quantity safely", async () => {
    const name = "<img src=x onerror=alert(1)>";
    const view = browser("stock", paged([{
        product_name: name, product_barcode: "000123", shelf_code: "A-3", quantity: 0,
    }]));
    await start(view);
    assert.deepEqual(view.rows[0].children.map(cell => cell.textContent), [name, "000123", "A-3", 0]);
    assert.ok(view.rows[0].children.every(cell => cell.children.length === 0));
});

test("empty and short lists hide the expansion button", async () => {
    for (const count of [0, 1, 4]) {
        const view = browser("products", paged(products(count)));
        await start(view);
        assert.equal(view.rows.length, count);
        assert.equal(view.toggle.hidden, true);
        assert.equal(view.empty.hidden, count !== 0);
        assert.equal(view.scroll.hidden, count === 0);
        assert.equal(view.status.hidden, true);
    }
});

test("exactly five rows can expand and collapse without disappearing", async () => {
    const view = browser("products", paged(products(5)));
    await start(view);
    await view.toggle.emit("click");
    assert.equal(view.rows.length, 5);
    assert.equal(view.count.textContent, "Всего: 5");
    assert.equal(view.toggle.hidden, false);
    await view.toggle.emit("click");
    assert.equal(view.toggle.textContent, "Показать все");
});

test("successful warehouse changes refresh the expanded list and preserve its state", async () => {
    const items = products(7);
    const view = browser("products", paged(items));
    await start(view);
    await view.toggle.emit("click");
    items.push({ id: 7, name: "Новый товар", barcode: "0007" });
    await view.document.emit("inventory:changed");
    assert.equal(view.rows.length, 8);
    assert.equal(view.rows[7].children[0].textContent, "Новый товар");
    assert.equal(view.toggle.attributes["aria-expanded"], "true");
});

test("an initial load failure offers retry instead of claiming the list is empty", async () => {
    let fail = true;
    const api = paged(products(1));
    const view = browser("products", path => fail ? Promise.reject(new Error("Offline")) : api(path));
    await start(view);
    assert.equal(view.retry.hidden, false);
    assert.equal(view.empty.hidden, true);
    assert.equal(view.status.className, "error list-status");
    fail = false;
    await view.retry.emit("click");
    assert.equal(view.rows.length, 1);
    assert.equal(view.retry.hidden, true);
    assert.equal(view.status.hidden, true);
});

test("failed expansion keeps the five visible rows and allows another attempt", async () => {
    let fail = true;
    const api = paged(products(7));
    const view = browser("products", path => {
        if (fail && path.endsWith("limit=100")) return Promise.reject(new Error("Offline"));
        return api(path);
    });
    await start(view);
    await view.toggle.emit("click");
    assert.equal(view.rows.length, 5);
    assert.equal(view.toggle.attributes["aria-expanded"], "false");
    assert.equal(view.toggle.disabled, false);
    fail = false;
    await view.toggle.emit("click");
    assert.equal(view.rows.length, 7);
});

test("a stale load cannot overwrite the list refreshed after a form submission", async () => {
    let resolveFirst;
    let calls = 0;
    const view = browser("products", () => {
        if (++calls === 1) return new Promise(resolve => { resolveFirst = resolve; });
        return Promise.resolve([{ name: "Обновлённый товар", barcode: "new" }]);
    });
    await start(view);
    await view.document.emit("inventory:changed");
    resolveFirst([{ name: "Старый товар", barcode: "old" }]);
    await settle();
    assert.equal(view.rows[0].children[0].textContent, "Обновлённый товар");
    assert.equal(view.panel.attributes["aria-busy"], "false");
});

test("authentication failures use the shared session-expiration handler", async () => {
    const error = { status: 401 };
    const view = browser("products", async () => { throw error; });
    await start(view);
    assert.deepEqual(view.failures, [error]);
});
