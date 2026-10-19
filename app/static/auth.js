"use strict";

// JWTs live only in HttpOnly cookies. JavaScript reads the CSRF cookie, not JWTs.
const InventoryAuth = (() => {
    const prefix = "/api/v1";
    let refreshPromise;
    class ApiError extends Error {
        constructor(response, data) {
            const detail = data?.detail;
            super(typeof detail === "string" ? detail : Array.isArray(detail)
                ? detail.map(item => `${item.loc.at(-1)}: ${item.msg}`).join("; ")
                : "Не удалось выполнить действие");
            this.status = response.status;
            this.code = data?.code;
        }
    }
    const csrfCookie = () => document.cookie.split("; ").find(item => item.startsWith("inventory_csrf="))?.split("=").slice(1).join("=") || "";
    async function raw(path, options = {}, retryCsrf = true) {
        const method = (options.method || "GET").toUpperCase();
        const headers = new Headers(options.headers);
        if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
            if (!csrfCookie()) await raw("/auth/web/csrf");
            headers.set("X-CSRF-Token", csrfCookie());
        }
        const response = await fetch(prefix + path, { ...options, method, headers, credentials: "same-origin", cache: "no-store" });
        const data = response.status === 204 ? null : await response.json();
        if (!response.ok) {
            if (data?.code === "csrf_invalid" && retryCsrf) {
                await raw("/auth/web/csrf");
                return raw(path, options, false);
            }
            throw new ApiError(response, data);
        }
        return data;
    }
    function json(data) {
        return { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) };
    }
    async function refresh() {
        if (!refreshPromise) {
            const work = async () => {
                // Another tab may have refreshed while this tab waited for the lock.
                try { await raw("/auth/me"); return; }
                catch (error) { if (error.status !== 401) throw error; }
                await raw("/auth/web/refresh", { method: "POST" });
            };
            refreshPromise = (navigator.locks
                ? navigator.locks.request("inventory-auth-refresh", work) : work())
                .finally(() => { refreshPromise = undefined; });
        }
        return refreshPromise;
    }
    async function api(path, options = {}) {
        try { return await raw(path, options); }
        catch (error) {
            if (error.status !== 401) throw error;
            await refresh();
            return raw(path, options);
        }
    }
    function show(message, error = false) {
        let output = document.getElementById("message");
        if (!output) {
            output = document.createElement("p");
            output.id = "message";
            output.setAttribute("role", "status");
            document.querySelector("main").append(output);
        }
        output.textContent = message;
        output.className = error ? "error" : "success";
    }
    function goLogin(reason = "ended") {
        location.replace(`/static/login.html?reason=${reason}`);
    }
    function fail(error) {
        if (error.status === 401) goLogin();
        else show(error.message || "Сервер недоступен. Повторите действие.", true);
    }
    async function submit(form, work) {
        const button = form.querySelector('[type="submit"]');
        if (button.disabled) return;
        button.disabled = true;
        try { await work(); }
        catch (error) { show(error.message || "Сервер недоступен. Повторите действие.", true); }
        finally { button.disabled = false; }
    }
    function matchingPassword(form) {
        const password = form.elements.new_password.value;
        if (password !== form.elements.repeat_password.value) throw new Error("Пароли не совпадают");
        return password; // Do not trim passwords: spaces are significant.
    }
    async function initLogin() {
        const loginForm = document.getElementById("login-form");
        const setupForm = document.getElementById("setup-form");
        const dialog = document.getElementById("confirm-login");
        const reason = new URLSearchParams(location.search).get("reason");
        if (reason === "changed") show("Пароль изменён. Войдите с новым паролем.");
        if (reason === "ended") show("Сессия завершена. Войдите снова.", true);
        const handleResult = result => {
            if (result.status === "authenticated") location.replace("/static/index.html");
            else if (result.status === "password_setup") {
                loginForm.hidden = true;
                setupForm.hidden = false;
                show(result.message);
                setupForm.elements.new_password.focus();
            } else if (result.status === "confirm_login") dialog.showModal();
        };
        loginForm.addEventListener("submit", event => {
            event.preventDefault();
            submit(loginForm, async () => {
                const result = await raw("/auth/web/login", json({
                    login: loginForm.elements.login.value, password: loginForm.elements.password.value,
                }));
                loginForm.elements.password.value = "";
                handleResult(result);
            });
        });
        setupForm.addEventListener("submit", event => {
            event.preventDefault();
            submit(setupForm, async () => {
                handleResult(await raw("/auth/web/password/setup", json({ new_password: matchingPassword(setupForm) })));
                setupForm.reset();
            });
        });
        const cancel = async () => {
            try {
                await raw("/auth/web/cancel-login", { method: "POST" });
                dialog.close();
                show("Вход отменён. Предыдущая сессия не изменена.");
            } catch (error) { show(error.message, true); }
        };
        document.getElementById("cancel-confirm").addEventListener("click", cancel);
        dialog.addEventListener("cancel", event => { event.preventDefault(); cancel(); });
        document.getElementById("accept-confirm").addEventListener("click", async event => {
            event.target.disabled = true;
            try {
                handleResult(await raw("/auth/web/confirm-login", json({ confirm: true })));
                dialog.close();
            } catch (error) { dialog.close(); show(error.message, true); }
            finally { event.target.disabled = false; }
        });
        document.getElementById("back-login").addEventListener("click", async () => {
            try { await raw("/auth/web/cancel-login", { method: "POST" }); }
            catch (error) { show(error.message, true); return; }
            setupForm.reset();
            setupForm.hidden = true;
            loginForm.hidden = false;
            show("Введите логин и пароль.");
        });
        await raw("/auth/web/csrf");
    }
    function sessionBar(user) {
        const bar = document.createElement("section");
        bar.className = "session-bar";
        const name = document.createElement("span");
        name.textContent = `${user.full_name} · ${user.role === "admin" ? "Администратор" : "Работник"}`;
        bar.append(name);
        for (const [href, label] of [["/static/index.html", "Склад"], ["/static/password.html", "Сменить пароль"],
            ...(user.role === "admin" ? [["/static/users.html", "Пользователи"]] : [])]) {
            const link = document.createElement("a"); link.href = href; link.textContent = label; bar.append(link);
        }
        const logout = document.createElement("button");
        logout.type = "button"; logout.textContent = "Выйти";
        logout.addEventListener("click", async () => {
            logout.disabled = true;
            try { await raw("/auth/web/logout", { method: "POST" }); location.replace("/static/login.html"); }
            catch (error) { fail(error); logout.disabled = false; }
        });
        bar.append(logout);
        document.querySelector("main").prepend(bar);
    }
    async function initUsers() {
        const list = document.getElementById("user-list");
        const result = document.getElementById("temporary-result");
        const displayTemporary = data => {
            result.hidden = false;
            document.getElementById("temporary-login").textContent = data.user.login;
            document.getElementById("temporary-password").textContent = data.temporary_password;
            show("Передайте временный пароль пользователю. В базе сохранён только его хеш.");
        };
        document.getElementById("hide-temporary").addEventListener("click", () => {
            result.hidden = true;
            document.getElementById("temporary-password").textContent = "";
        });
        async function reload() {
            list.replaceChildren();
            for (let offset = 0; ; offset += 100) {
                const users = await api(`/users/?offset=${offset}&limit=100`);
                for (const user of users) {
                    const row = document.createElement("tr");
                    for (const value of [user.login, user.full_name, user.role === "admin" ? "Администратор" : "Работник",
                        user.must_change_password ? "Нужна установка пароля" : "Постоянный пароль"] ) {
                        const cell = document.createElement("td"); cell.textContent = value; row.append(cell);
                    }
                    const cell = document.createElement("td");
                    const reset = document.createElement("button"); reset.type = "button"; reset.textContent = "Сбросить пароль";
                    reset.addEventListener("click", async () => {
                        if (!window.confirm(`Сбросить пароль ${user.login}? Его текущая сессия будет завершена.`)) return;
                        reset.disabled = true;
                        try {
                            displayTemporary(await api(`/users/${user.id}/reset-password`, { method: "POST" }));
                            // Self-reset ends this administrator's session too. Keep the one-time password visible.
                            if (user.id !== currentUser.id) await reload();
                            else show("Ваш пароль сброшен. Сохраните временный пароль и перейдите на страницу входа.");
                        } catch (error) { fail(error); reset.disabled = false; }
                    });
                    cell.append(reset); row.append(cell); list.append(row);
                }
                if (users.length < 100) break;
            }
        }
        const form = document.getElementById("create-user");
        form.addEventListener("submit", event => {
            event.preventDefault();
            submit(form, async () => {
                displayTemporary(await api("/users/", json(Object.fromEntries(new FormData(form)))));
                form.reset();
                await reload();
            });
        });
        await reload();
    }
    let currentUser;
    async function initProtected(page) {
        currentUser = await api("/auth/me");
        sessionBar(currentUser);
        if (currentUser.role !== "admin") {
            document.querySelectorAll('a[href="/static/delete_product.html"], a[href="/static/delete_shelf_stock.html"]').forEach(link => { link.hidden = true; });
            if (page === "users" || /\/delete_(product|shelf_stock)\.html$/.test(location.pathname)) {
                document.querySelectorAll("main form, main table").forEach(element => { element.hidden = true; });
                show("Это действие доступно только администратору.", true);
                return;
            }
        }
        if (page === "users") await initUsers();
        else if (page === "password") {
            const form = document.getElementById("change-password");
            form.addEventListener("submit", event => {
                event.preventDefault();
                submit(form, async () => {
                    await api("/auth/password/change", json({ current_password: form.elements.current_password.value, new_password: matchingPassword(form) }));
                    form.reset(); goLogin("changed");
                });
            });
        } else {
            const form = document.querySelector("main form");
            form.addEventListener("submit", event => {
                event.preventDefault();
                submit(form, async () => {
                    try {
                        await api(new URL(form.action).pathname.slice(prefix.length), {
                            method: "POST", body: new URLSearchParams(new FormData(form)),
                        });
                        show("Действие выполнено.");
                    } catch (error) { fail(error); }
                });
            });
        }
    }
    async function init() {
        const page = document.body.dataset.page || "warehouse";
        // Prevent native form navigation while checking the current session.
        const blocker = event => event.preventDefault();
        document.addEventListener("submit", blocker, true);
        try {
            if (page === "login") await initLogin();
            else await initProtected(page);
            document.removeEventListener("submit", blocker, true);
        } catch (error) { if (page === "login") show(error.message, true); else fail(error); }
    }
    return { init };
})();
InventoryAuth.init();
