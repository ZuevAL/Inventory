const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");

// Exercise the real request helpers in a mock browser, without reading real cookies.
const source = fs.readFileSync(path.join(__dirname, "../app/static/auth.js"), "utf8")
    .replace("return { init };", "return { init, api, raw, matchingPassword };")
    .replace("InventoryAuth.init();", "globalThis.client = InventoryAuth;");
function browser(fetch) {
    const context = { Headers, URL, URLSearchParams, navigator: {}, document: { cookie: "inventory_csrf=valid-csrf" }, fetch };
    vm.createContext(context);
    vm.runInContext(source, context);
    return context;
}
const reply = (status, data) => ({ status, ok: status >= 200 && status < 300, json: async () => data });

test("mutating requests include CSRF and cookies, not Authorization or JWT storage", async () => {
    const context = browser(async (url, options) => {
        assert.equal(url, "/api/v1/shelves/form");
        assert.equal(options.credentials, "same-origin");
        assert.equal(options.cache, "no-store");
        assert.equal(options.headers.get("X-CSRF-Token"), "valid-csrf");
        assert.equal(options.headers.has("Authorization"), false);
        return reply(200, { code: "S1" });
    });
    await context.client.api("/shelves/form", { method: "POST" });
});

test("CSRF failure is recovered once before resending the action", async () => {
    const calls = [];
    const context = browser(async (url, options) => {
        calls.push(url);
        if (url.endsWith("/csrf")) {
            context.document.cookie = "inventory_csrf=updated";
            return reply(200, {});
        }
        if (calls.length === 1) return reply(403, { code: "csrf_invalid", detail: "Update" });
        assert.equal(options.headers.get("X-CSRF-Token"), "updated");
        return reply(200, {});
    });
    await context.client.api("/shelves/form", { method: "POST" });
    assert.deepEqual(calls, ["/api/v1/shelves/form", "/api/v1/auth/web/csrf", "/api/v1/shelves/form"]);
});

test("expired access refreshes once and retries the protected request", async () => {
    const calls = [];
    let refreshed = false;
    const context = browser(async url => {
        calls.push(url);
        if (url.endsWith("/refresh")) { refreshed = true; return reply(200, {}); }
        return refreshed ? reply(200, {}) : reply(401, { code: "token_expired" });
    });
    await context.client.api("/products/");
    assert.deepEqual(calls, ["/api/v1/products/", "/api/v1/auth/me", "/api/v1/auth/web/refresh", "/api/v1/products/"]);
});

test("concurrent requests share a single refresh operation", async () => {
    let refreshed = false;
    let refreshes = 0;
    const context = browser(async url => {
        if (url.endsWith("/refresh")) { refreshes++; refreshed = true; return reply(200, {}); }
        return refreshed ? reply(200, {}) : reply(401, {});
    });
    await Promise.all([context.client.api("/products/"), context.client.api("/shelves/")]);
    assert.equal(refreshes, 1);
});

test("a waiting browser tab checks access after acquiring the cross-tab lock", async () => {
    let refreshed = false;
    let refreshes = 0;
    const context = browser(async url => {
        if (url.endsWith("/refresh")) { refreshes++; return reply(200, {}); }
        return refreshed ? reply(200, {}) : reply(401, {});
    });
    context.navigator.locks = { request: async (name, work) => {
        assert.equal(name, "inventory-auth-refresh");
        refreshed = true; // The preceding tab refreshed while this tab was waiting.
        return work();
    } };
    await context.client.api("/products/");
    assert.equal(refreshes, 0);
});

test("business permission errors are not retried or refreshed", async () => {
    let calls = 0;
    const context = browser(async () => { calls++; return reply(403, { code: "forbidden", detail: "Admin only" }); });
    await assert.rejects(context.client.api("/products/", { method: "DELETE" }), { status: 403 });
    assert.equal(calls, 1);
});

test("failed refresh is not retried in a loop", async () => {
    let refreshes = 0;
    const context = browser(async url => {
        if (url.endsWith("/refresh")) refreshes++;
        return reply(401, { code: "session_ended" });
    });
    await assert.rejects(context.client.api("/products/"), { status: 401 });
    assert.equal(refreshes, 1);
});

test("password confirmation preserves spaces and rejects a mismatch", () => {
    const context = browser(() => {});
    const form = { elements: { new_password: { value: " Password with spaces " }, repeat_password: { value: " Password with spaces " } } };
    assert.equal(context.client.matchingPassword(form), " Password with spaces ");
    form.elements.repeat_password.value = "Password with spaces";
    assert.throws(() => context.client.matchingPassword(form), /Пароли не совпадают/);
});
