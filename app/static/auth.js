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
        if (error.code === "recovery_setup_required") location.replace("/static/security.html");
        else if (error.status === 401) goLogin();
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
        if (reason === "recovered") show("Пароль восстановлен. Войдите и сохраните новый резервный код.");
        if (reason === "ended") show("Сессия завершена. Войдите снова.", true);
        const handleResult = result => {
            if (result.status === "authenticated") location.replace(result.user?.recovery_required
                ? "/static/security.html" : "/static/index.html");
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
        const navigation = document.querySelector(".sidebar-nav");
        if (user.role === "admin" && navigation) {
            const link = document.createElement("a");
            link.href = "/static/security.html";
            const icon = document.createElement("span");
            icon.className = "nav-icon";
            icon.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m12 3 8 3v5c0 5-4 8-8 10-4-2-8-5-8-10V6l8-3Z"/><path d="m8 12 3 3 5-6"/></svg>';
            const label = document.createElement("span");
            label.textContent = "Безопасность";
            link.append(icon, label);
            if (location.pathname.endsWith("/security.html")) {
                link.className = "active";
                link.setAttribute("aria-current", "page");
            }
            navigation.append(link);
        }
        const bar = document.createElement("section");
        bar.className = "session-bar";
        const name = document.createElement("span");
        name.textContent = `${user.full_name} · ${user.role === "admin" ? "Администратор" : "Работник"}`;
        bar.append(name);
        for (const [href, label] of [["/static/index.html", "Склад"], ["/static/password.html", "Сменить пароль"],
            ...(user.role === "admin" ? [["/static/users.html", "Пользователи"], ["/static/security.html", "Безопасность"]] : [])]) {
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
    async function initRecovery() {
        const form = document.getElementById("recovery-form");
        form.addEventListener("submit", event => {
            event.preventDefault();
            return submit(form, async () => {
                const password = matchingPassword(form);
                await raw("/auth/web/password/recover", json({
                    login: form.elements.login.value, recovery_code: form.elements.recovery_code.value,
                    new_password: password, repeat_password: form.elements.repeat_password.value,
                }));
                form.reset();
                goLogin("recovered");
            });
        });
        window.addEventListener("pagehide", () => form.reset());
        await raw("/auth/web/csrf");
    }
    async function initSecurity() {
        const form = document.getElementById("issue-code-form");
        const confirmation = document.getElementById("activate-code-form");
        const panel = document.getElementById("code-result");
        const value = document.getElementById("recovery-code");
        const status = document.getElementById("recovery-status");
        const continuation = document.getElementById("continue-warehouse");
        let pendingCode = "";
        const clearCode = () => {
            pendingCode = ""; value.textContent = ""; panel.hidden = true; confirmation.reset();
        };
        const updateStatus = () => {
            status.textContent = currentUser.recovery_required
                ? "Сохраните резервный код, чтобы продолжить работу."
                : "Восстановление настроено. Резервный код действует до использования или замены.";
            continuation.hidden = currentUser.recovery_required;
            form.querySelector('[type="submit"]').textContent = currentUser.recovery_required
                ? "Создать резервный код" : "Заменить резервный код";
        };
        updateStatus();
        form.addEventListener("submit", event => {
            event.preventDefault();
            return submit(form, async () => {
                const result = await api("/auth/recovery/code", json({ current_password: form.elements.current_password.value }));
                form.reset(); clearCode();
                pendingCode = result.recovery_code;
                value.textContent = pendingCode; panel.hidden = false;
                show("Сохраните код вне этого браузера, затем подтвердите сохранение в течение 15 минут.");
            });
        });
        confirmation.addEventListener("submit", event => {
            event.preventDefault();
            return submit(confirmation, async () => {
                if (!pendingCode || !confirmation.elements.saved.checked) throw new Error("Подтвердите, что сохранили код.");
                await api("/auth/recovery/activate", json({ recovery_code: pendingCode, saved: true }));
                clearCode();
                currentUser = await api("/auth/me"); updateStatus();
                show("Новый код активирован. Прежний код больше не действует. Можно продолжить работу.");
            });
        });
        document.getElementById("copy-code").addEventListener("click", async () => {
            if (!pendingCode) return;
            try {
                await navigator.clipboard.writeText(pendingCode);
                show("Код скопирован. Сохраните его в надёжном месте вне браузера.");
            } catch (_) { show("Не удалось скопировать автоматически. Выделите код и скопируйте его вручную.", true); }
        });
        document.getElementById("download-code").addEventListener("click", () => {
            if (!pendingCode) return;
            const text = `Склад — код восстановления\nЛогин: ${currentUser.login}\nКод: ${pendingCode}\n\nХраните файл в защищённом месте. Код даёт право сменить пароль.\nПосле скачивания подтвердите сохранение в приложении.\n`;
            const url = URL.createObjectURL(new Blob([text], { type: "text/plain;charset=utf-8" }));
            const link = document.createElement("a");
            link.href = url; link.download = `inventory-recovery-${currentUser.login}.txt`;
            link.click();
            setTimeout(() => URL.revokeObjectURL(url), 1000);
        });
        window.addEventListener("pagehide", () => { clearCode(); form.reset(); });
        const list = document.getElementById("recovery-history");
        const more = document.getElementById("history-more");
        let offset = 0;
        async function loadHistory() {
            const events = await api(`/auth/recovery/history?offset=${offset}&limit=100`);
            if (offset === 0) list.replaceChildren();
            for (const event of events) {
                const row = document.createElement("tr");
                for (const text of [new Date(event.occurred_at * 1000).toLocaleString("ru-RU"),
                    { success: "Пароль восстановлен", failure: "Неудачная попытка", rate_limited: "Превышен лимит попыток" }[event.outcome] || "Событие восстановления",
                    event.source]) {
                    const cell = document.createElement("td"); cell.textContent = text; row.append(cell);
                }
                list.append(row);
            }
            if (offset === 0 && events.length === 0) {
                const row = document.createElement("tr"), cell = document.createElement("td");
                cell.colSpan = 3; cell.textContent = "Событий восстановления за последние 90 дней нет.";
                row.append(cell); list.append(row);
            }
            offset += events.length; more.hidden = events.length < 100;
        }
        more.addEventListener("click", async () => {
            more.disabled = true;
            try { await loadHistory(); } catch (error) { fail(error); }
            finally { more.disabled = false; }
        });
        await loadHistory();
    }
    async function initProtected(page) {
        currentUser = await api("/auth/me");
        if (currentUser.recovery_required && page !== "security" && page !== "password") {
            location.replace("/static/security.html"); return;
        }
        sessionBar(currentUser);
        if (currentUser.role !== "admin") {
            document.querySelectorAll('a[href="/static/delete_product.html"], a[href="/static/delete_shelf_stock.html"]').forEach(link => { link.hidden = true; });
            if (page === "users" || page === "security" || /\/delete_(product|shelf_stock)\.html$/.test(location.pathname)) {
                document.querySelectorAll("main form, main table").forEach(element => { element.hidden = true; });
                show("Это действие доступно только администратору.", true);
                return;
            }
        }
        if (page === "users") await initUsers();
        else if (page === "security") await initSecurity();
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
            else if (page === "recovery") await initRecovery();
            else await initProtected(page);
            document.removeEventListener("submit", blocker, true);
        } catch (error) { if (page === "login" || page === "recovery") show(error.message, true); else fail(error); }
    }
    return { init };
})();
InventoryAuth.init();
