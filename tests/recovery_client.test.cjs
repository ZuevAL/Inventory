const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");

const source = fs.readFileSync(path.join(__dirname, "../app/static/auth.js"), "utf8")
    .replace("InventoryAuth.init();", "globalThis.client = InventoryAuth;");

class Element {
    constructor() { this.listeners = {}; this.children = []; this.hidden = false; this.disabled = false; this.value = ""; this.textContent = ""; }
    addEventListener(type, handler) { (this.listeners[type] ||= []).push(handler); }
    removeEventListener() {}
    async emit(type) {
        for (const handler of this.listeners[type] || []) await handler({ preventDefault() {}, target: this });
        await new Promise(setImmediate);
    }
    append(...children) { this.children.push(...children); }
    prepend(...children) { this.children.unshift(...children); }
    replaceChildren(...children) { this.children = [...children]; }
    setAttribute() {}
    click() { this.clicked = true; }
    focus() {}
    reset() { for (const input of Object.values(this.elements || {})) { input.value = ""; input.checked = false; } }
    querySelector() { return this.button ||= new Element(); }
}

function browser(page, user, handler = () => ({})) {
    const nodes = new Map();
    const get = id => { if (!nodes.has(id)) nodes.set(id, new Element()); return nodes.get(id); };
    const form = get(page === "recovery" ? "recovery-form" : page === "password" ? "change-password" : "issue-code-form");
    form.action = "http://testserver/api/v1/auth/web/password/recover";
    form.elements = Object.fromEntries(["login", "recovery_code", "new_password", "repeat_password", "current_password"]
        .map(name => [name, new Element()]));
    const confirm = get("activate-code-form");
    confirm.elements = { saved: Object.assign(new Element(), { checked: false }) };
    const calls = [], redirects = [], created = [];
    const document = Object.assign(new Element(), {
        cookie: "inventory_csrf=valid-csrf", body: { dataset: { page } },
        getElementById: get, createElement: () => { const element = new Element(); created.push(element); return element; }, querySelectorAll: () => [],
        querySelector: selector => selector === "main form" ? form : selector === ".sidebar-nav" ? get("sidebar-nav") : get("main"),
    });
    const window = new Element();
    const context = { Headers, URL, URLSearchParams, Blob, setTimeout, clearTimeout, navigator: {}, window, document,
        location: { pathname: `/static/${page}.html`, search: "", replace: url => redirects.push(url) },
        fetch: async (url, options) => {
            calls.push({ url, options });
            let result = url.endsWith("/auth/me") ? user : url.includes("/history") ? [] : handler(url, options);
            const status = result?.httpStatus || 200;
            return { status, ok: status < 400, json: async () => result };
        },
    };
    vm.createContext(context); vm.runInContext(source, context);
    return { ...context, form, confirm, get, calls, redirects, created };
}

const admin = required => ({ id: 1, login: "admin_01", full_name: "Администратор", role: "admin", recovery_required: required });

test("administrator can find Security in the main sidebar", async () => {
    const b = browser("warehouse", admin(false));
    await b.client.init();
    const link = b.get("sidebar-nav").children.find(element => element.href === "/static/security.html");
    assert.ok(link, "Security link is missing from the main sidebar");
    assert.ok(link.children.some(element => element.textContent === "Безопасность"));
});

test("worker does not receive an administrator Security sidebar link", async () => {
    const b = browser("warehouse", { role: "worker", recovery_required: false });
    await b.client.init();
    assert.equal(b.get("sidebar-nav").children.some(element => element.href === "/static/security.html"), false);
});

test("forgot-password page works anonymously without requesting a session", async () => {
    const b = browser("recovery", { role: "worker" });
    await b.client.init();
    assert.deepEqual(b.calls.map(call => call.url), ["/api/v1/auth/web/csrf"]);
});

test("recovery submits confirmed password without refresh or automatic login", async () => {
    const b = browser("recovery", { role: "worker" });
    await b.client.init();
    Object.assign(b.form.elements.login, { value: "admin_01" });
    b.form.elements.recovery_code.value = "ABCD-1234";
    b.form.elements.new_password.value = b.form.elements.repeat_password.value = " New permanent password ";
    await b.form.emit("submit");
    const submitted = b.calls.find(call => call.url.endsWith("/password/recover"));
    assert.ok(submitted);
    assert.deepEqual(JSON.parse(submitted.options.body), { login: "admin_01", recovery_code: "ABCD-1234",
        new_password: " New permanent password ", repeat_password: " New permanent password " });
    assert.deepEqual(b.redirects, ["/static/login.html?reason=recovered"]);
    assert.equal(b.form.elements.recovery_code.value, "");
});

test("unconfigured admin is redirected before warehouse actions are attached", async () => {
    const b = browser("warehouse", admin(true));
    await b.client.init();
    assert.deepEqual(b.redirects, ["/static/security.html"]);
    assert.equal((b.form.listeners.submit || []).length, 0);
});

test("unconfigured admin can still change their own password", async () => {
    const b = browser("password", admin(true));
    await b.client.init();
    assert.deepEqual(b.redirects, []);
    assert.equal(b.form.listeners.submit.length, 1);
});

test("issuing a code does not activate it before explicit save confirmation", async () => {
    const code = "ABCD-1234-ABCD-1234-ABCD-1234-ABCD-1234";
    const b = browser("security", admin(false), url => url.endsWith("/recovery/code") ? { recovery_code: code, expires_in: 900 } : {});
    await b.client.init();
    b.form.elements.current_password.value = "Current password 123";
    await b.form.emit("submit");
    assert.equal(b.get("recovery-code").textContent, code);
    assert.equal(b.form.elements.current_password.value, "");
    assert.equal(b.calls.filter(call => call.url.endsWith("/activate")).length, 0);
    await b.confirm.emit("submit");
    assert.equal(b.calls.filter(call => call.url.endsWith("/activate")).length, 0);
    b.confirm.elements.saved.checked = true;
    await b.confirm.emit("submit");
    const activated = b.calls.find(call => call.url.endsWith("/activate"));
    assert.ok(activated);
    assert.deepEqual(JSON.parse(activated.options.body), { recovery_code: code, saved: true });
    assert.equal(b.get("recovery-code").textContent, "");
});

test("leaving security page clears a displayed code for browser back navigation", async () => {
    const b = browser("security", admin(false), () => ({ recovery_code: "SECRET-CODE", expires_in: 900 }));
    await b.client.init();
    b.form.elements.current_password.value = "Current password 123";
    await b.form.emit("submit");
    assert.equal(b.get("recovery-code").textContent, "SECRET-CODE");
    await b.window.emit("pagehide");
    assert.equal(b.get("recovery-code").textContent, "");
});

test("downloaded recovery file contains the issued code and account", async () => {
    const code = "ABCD-1234-ABCD-1234-ABCD-1234-ABCD-1234";
    const b = browser("security", admin(false), () => ({ recovery_code: code, expires_in: 900 }));
    await b.client.init();
    b.form.elements.current_password.value = "Current password 123";
    await b.form.emit("submit");
    await b.get("download-code").emit("click");
    const file = b.created.find(element => element.download);
    assert.ok(file?.clicked);
    assert.equal(file.download, "inventory-recovery-admin_01.txt");
    const contents = await (await fetch(file.href)).text();
    assert.ok(contents.includes(code));
    assert.ok(contents.includes("admin_01"));
    assert.equal(contents.includes("Current password 123"), false);
    assert.equal(b.calls.some(call => call.url.endsWith("/activate")), false);
});

test("failed recovery stays on the form without attempting refresh", async () => {
    const b = browser("recovery", {}, url => url.endsWith("/password/recover")
        ? { httpStatus: 400, code: "invalid_recovery", detail: "Неверный логин или код восстановления" } : {});
    await b.client.init();
    b.form.elements.login.value = "admin_01";
    b.form.elements.recovery_code.value = "WRONG-CODE";
    b.form.elements.new_password.value = b.form.elements.repeat_password.value = "New permanent password";
    await b.form.emit("submit");
    assert.deepEqual(b.redirects, []);
    assert.equal(b.calls.some(call => call.url.endsWith("/refresh")), false);
    assert.equal(b.get("message").textContent, "Неверный логин или код восстановления");
});
