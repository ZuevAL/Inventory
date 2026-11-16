import asyncio
from concurrent.futures import ThreadPoolExecutor
from time import time

import pytest
from sqlalchemy import select, text

from app.core import tokens
from app.models.user import User
from tests.conftest import TEST_PASSWORD
from tests.test_auth import PREFIX, headers, login, me, web_post

NEW_PASSWORD = "Recovered permanent password 789"


def admin_session(env, name="admin_01"):
    env.create_user(login=name, role="admin", recovery_ready=False)
    return login(env.client, name)


def issue(env, pair, password=TEST_PASSWORD):
    return env.client.post(
        PREFIX + "/auth/recovery/code",
        headers=headers(pair),
        json={"current_password": password},
    )


def activate(env, pair, code):
    return env.client.post(
        PREFIX + "/auth/recovery/activate",
        headers=headers(pair),
        json={"recovery_code": code, "saved": True},
    )


def enrolled_admin(env, name="admin_01"):
    pair = admin_session(env, name)
    result = issue(env, pair)
    assert result.status_code == 200, result.text
    code = result.json()["recovery_code"]
    assert activate(env, pair, code).status_code == 200
    return pair, code


def recover(env, code, name="admin_01", password=NEW_PASSWORD, repeat=None):
    return web_post(
        env.client,
        "/auth/web/password/recover",
        {
            "login": name,
            "recovery_code": code,
            "new_password": password,
            "repeat_password": password if repeat is None else repeat,
        },
    )


def test_code_requires_current_password(auth_env):
    pair = admin_session(auth_env)
    result = issue(auth_env, pair, "wrong password")
    assert result.status_code == 400
    assert "recovery_code" not in result.json()


def test_code_only_activates_after_saved_confirmation(auth_env):
    pair = admin_session(auth_env)
    result = issue(auth_env, pair)
    assert result.status_code == 200, result.text
    code = result.json()["recovery_code"]
    assert me(auth_env.client, pair).json()["recovery_required"] is True
    assert recover(auth_env, code).status_code == 400
    assert activate(auth_env, pair, code).status_code == 200
    assert me(auth_env.client, pair).json()["recovery_required"] is False


def test_recovery_installs_password_without_logging_in(auth_env):
    pair, code = enrolled_admin(auth_env)
    result = recover(auth_env, code)
    assert result.status_code == 200, result.text
    assert "access_token" not in result.json()
    assert me(auth_env.client, pair).status_code == 401
    new = login(auth_env.client, "admin_01", NEW_PASSWORD)
    assert new["status"] == "authenticated"
    assert new["user"]["recovery_required"] is True
    assert recover(auth_env, code).status_code == 400


@pytest.mark.parametrize("path", ["/products/", "/shelves/", "/stock/", "/users/"])
def test_admin_must_save_code_before_warehouse_access(auth_env, path):
    pair = admin_session(auth_env)
    response = auth_env.client.get(PREFIX + path, headers=headers(pair))
    assert response.status_code == 403
    assert response.json()["code"] == "recovery_setup_required"
    code = issue(auth_env, pair).json()["recovery_code"]
    assert activate(auth_env, pair, code).status_code == 200
    assert auth_env.client.get(PREFIX + path, headers=headers(pair)).status_code == 200


def test_admin_reset_revokes_active_and_pending_recovery_codes(auth_env):
    actor, _ = enrolled_admin(auth_env, "owner_01")
    target, old_code = enrolled_admin(auth_env)
    pending = issue(auth_env, target).json()["recovery_code"]
    response = auth_env.client.post(
        PREFIX + f"/users/{target['user']['id']}/reset-password", headers=headers(actor)
    )
    assert response.status_code == 200

    async def state(db):
        user = await db.get(User, target["user"]["id"])
        return user.recovery_code_hash, user.pending_recovery_hash

    assert auth_env.database(state) == (None, None)
    assert recover(auth_env, old_code).status_code == 400
    assert recover(auth_env, pending).status_code == 400


def test_cli_reset_revokes_recovery_code(auth_env, monkeypatch):
    from app.cli import reset_admin_password as cli

    pair, code = enrolled_admin(auth_env)
    monkeypatch.setattr(cli, "AsyncSessionLocal", auth_env.session_factory)
    monkeypatch.setattr(cli, "engine", auth_env.session_factory.kw["bind"])
    temporary = asyncio.run(cli.reset_admin_password("ADMIN_01"))

    async def state(db):
        return (await db.get(User, pair["user"]["id"])).recovery_code_hash

    assert auth_env.database(state) is None
    assert recover(auth_env, code).status_code == 400
    assert login(auth_env.client, "admin_01", temporary)["status"] == "password_setup"


def test_recovery_attempts_are_throttled_without_blocking_login(auth_env, monkeypatch):
    pair, code = enrolled_admin(auth_env)
    for _ in range(5):
        assert recover(auth_env, "wrong code").status_code == 400
    blocked = recover(auth_env, code)
    assert blocked.status_code == 429
    assert blocked.headers.get("Retry-After")
    assert me(auth_env.client, pair).status_code == 200
    assert login(auth_env.client, "admin_01")["status"] == "confirm_login"
    now = tokens.utc_timestamp()
    monkeypatch.setattr(tokens, "utc_timestamp", lambda: now + 901)
    assert recover(auth_env, code).status_code == 200


def test_history_is_private_and_contains_no_secrets(auth_env):
    pair, code = enrolled_admin(auth_env)
    assert recover(auth_env, "wrong code").status_code == 400
    response = auth_env.client.get(
        PREFIX + "/auth/recovery/history", headers=headers(pair)
    )
    assert response.status_code == 200
    events = response.json()
    assert len(events) == 1
    assert events[0]["outcome"] == "failure"
    assert events[0]["source"] == "testclient"
    assert code not in response.text and TEST_PASSWORD not in response.text
    other, _ = enrolled_admin(auth_env, "other_admin")
    assert (
        auth_env.client.get(
            PREFIX + "/auth/recovery/history", headers=headers(other)
        ).json()
        == []
    )


def test_history_retains_only_ninety_days(auth_env):
    pair, _ = enrolled_admin(auth_env)
    history = auth_env.client.get(
        PREFIX + "/auth/recovery/history", headers=headers(pair)
    )
    assert history.status_code == 200

    async def insert_old(db):
        await db.execute(
            text(
                "INSERT INTO recovery_events (user_id, occurred_at, outcome, source) "
                "VALUES (:id, :at, 'failure', 'old-source')"
            ),
            {"id": pair["user"]["id"], "at": int(time()) - 91 * 86400},
        )

    auth_env.database(insert_old)
    assert (
        auth_env.client.get(
            PREFIX + "/auth/recovery/history", headers=headers(pair)
        ).json()
        == []
    )

    async def retained(db):
        return await db.scalar(text("SELECT count(*) FROM recovery_events"))

    assert auth_env.database(retained) == 0


@pytest.mark.parametrize("page", ["recovery", "security"])
def test_recovery_pages_are_served(auth_env, page):
    response = auth_env.client.get(f"/static/{page}.html")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")


def test_source_limit_does_not_create_unbounded_buckets(auth_env):
    from sqlalchemy import func

    from app.models.recovery import RecoveryLimit

    for number in range(30):
        assert recover(auth_env, "wrong", name=f"unknown_{number}").status_code == 400

    async def count(db):
        return await db.scalar(select(func.count()).select_from(RecoveryLimit))

    before = auth_env.database(count)
    for number in range(30, 35):
        assert recover(auth_env, "wrong", name=f"unknown_{number}").status_code == 429
    assert auth_env.database(count) == before


def test_concurrent_recovery_commits_only_once(auth_env):
    from fastapi.testclient import TestClient

    pair, code = enrolled_admin(auth_env)

    def attempt(_):
        with TestClient(auth_env.application) as client:
            return web_post(
                client,
                "/auth/web/password/recover",
                {
                    "login": "admin_01",
                    "recovery_code": code,
                    "new_password": NEW_PASSWORD,
                    "repeat_password": NEW_PASSWORD,
                },
            ).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(attempt, range(2)))
    assert sorted(results) == [200, 400]

    async def version(db):
        return (await db.get(User, pair["user"]["id"])).credential_version

    assert auth_env.database(version) == 1


def test_pending_replacement_keeps_old_code_usable(auth_env):
    pair, old = enrolled_admin(auth_env)
    pending = issue(auth_env, pair).json()["recovery_code"]
    assert recover(auth_env, pending).status_code == 400
    assert recover(auth_env, old).status_code == 200


def test_confirmed_replacement_revokes_old_code(auth_env):
    pair, old = enrolled_admin(auth_env)
    replacement = issue(auth_env, pair).json()["recovery_code"]
    assert activate(auth_env, pair, replacement).status_code == 200
    assert recover(auth_env, old).status_code == 400
    assert recover(auth_env, replacement).status_code == 200


def test_stale_confirmation_cannot_replace_current_code(auth_env):
    pair, old = enrolled_admin(auth_env)
    first = issue(auth_env, pair).json()["recovery_code"]
    second = issue(auth_env, pair).json()["recovery_code"]
    assert activate(auth_env, pair, first).status_code == 409

    async def expire(db):
        (await db.get(User, pair["user"]["id"])).pending_recovery_expires_at = 1

    auth_env.database(expire)
    assert activate(auth_env, pair, second).status_code == 409
    assert recover(auth_env, old).status_code == 200


@pytest.mark.parametrize("kind", ["same", "mismatch", "short"])
def test_invalid_new_password_does_not_consume_code(auth_env, kind):
    _, code = enrolled_admin(auth_env)
    password = (
        TEST_PASSWORD
        if kind == "same"
        else "tinySecret9!"
        if kind == "short"
        else NEW_PASSWORD
    )
    result = recover(
        auth_env,
        code,
        password=password,
        repeat="Different confirmation" if kind == "mismatch" else None,
    )
    assert result.status_code == (400 if kind == "same" else 422)
    assert code not in result.text and password not in result.text
    assert recover(auth_env, code).status_code == 200


def test_unknown_worker_and_wrong_code_have_identical_errors(auth_env):
    pair, _ = enrolled_admin(auth_env)
    auth_env.create_user()
    results = [
        recover(auth_env, "wrong", name=name)
        for name in ("unknown_user", "worker_01", "admin_01")
    ]
    assert [result.status_code for result in results] == [400, 400, 400]
    assert results[0].json() == results[1].json() == results[2].json()
    assert me(auth_env.client, pair).status_code == 200


def test_regular_password_change_preserves_code(auth_env):
    pair, code = enrolled_admin(auth_env)
    result = auth_env.client.post(
        PREFIX + "/auth/password/change",
        headers=headers(pair),
        json={
            "current_password": TEST_PASSWORD,
            "new_password": "Changed ordinary password 123",
        },
    )
    assert result.status_code == 200
    assert recover(auth_env, code).status_code == 200


def test_code_remains_valid_after_a_year(auth_env, monkeypatch):
    _, code = enrolled_admin(auth_env)
    now = tokens.utc_timestamp()
    monkeypatch.setattr(tokens, "utc_timestamp", lambda: now + 366 * 86400)
    assert recover(auth_env, code.lower().replace("-", " ")).status_code == 200


def test_only_hashes_are_stored_and_code_cannot_be_retrieved(auth_env):
    pair = admin_session(auth_env)
    code = issue(auth_env, pair).json()["recovery_code"]

    async def stored(db):
        user = await db.get(User, pair["user"]["id"])
        return user.pending_recovery_hash, str(user.__dict__)

    digest, record = auth_env.database(stored)
    assert len(digest) == 64
    assert code not in record and code.replace("-", "") not in record
    assert activate(auth_env, pair, code).status_code == 200
    assert activate(auth_env, pair, code).status_code == 409
    assert code not in me(auth_env.client, pair).text
    assert (
        code not in auth_env.client.get(PREFIX + "/users/", headers=headers(pair)).text
    )


def test_another_admin_cannot_activate_someone_elses_code(auth_env):
    owner = admin_session(auth_env)
    code = issue(auth_env, owner).json()["recovery_code"]
    other = admin_session(auth_env, "other_admin")
    assert activate(auth_env, other, code).status_code == 409
    assert me(auth_env.client, owner).json()["recovery_required"] is True
    assert activate(auth_env, owner, code).status_code == 200


def test_worker_cannot_manage_recovery(auth_env):
    auth_env.create_user()
    worker = login(auth_env.client)
    assert issue(auth_env, worker).status_code == 403
    assert activate(auth_env, worker, "wrong").status_code == 403
    assert (
        auth_env.client.get(
            PREFIX + "/auth/recovery/history", headers=headers(worker)
        ).status_code
        == 403
    )


def test_browser_recovery_requires_csrf(auth_env):
    _, code = enrolled_admin(auth_env)
    response = auth_env.client.post(
        PREFIX + "/auth/web/password/recover",
        json={
            "login": "admin_01",
            "recovery_code": code,
            "new_password": NEW_PASSWORD,
            "repeat_password": NEW_PASSWORD,
        },
    )
    assert response.status_code == 403
    assert recover(auth_env, code).status_code == 200


def test_code_issue_limits_current_password_guesses(auth_env):
    pair = admin_session(auth_env)
    for _ in range(5):
        assert issue(auth_env, pair, "wrong password").status_code == 400
    assert issue(auth_env, pair).status_code == 429
    assert me(auth_env.client, pair).status_code == 200


def test_throttled_requests_produce_bounded_audit_history(auth_env):
    pair, _ = enrolled_admin(auth_env)
    for _ in range(5):
        assert recover(auth_env, "wrong").status_code == 400
    for _ in range(20):
        assert recover(auth_env, "wrong").status_code == 429
    history = auth_env.client.get(
        PREFIX + "/auth/recovery/history", headers=headers(pair)
    ).json()
    assert len(history) == 6
    assert [event["outcome"] for event in history].count("rate_limited") == 1


def test_browser_cookie_recovery_round_trip(auth_env):
    from app.core.cookies import ACCESS_COOKIE

    auth_env.create_user(login="admin_01", role="admin", recovery_ready=False)
    response = web_post(
        auth_env.client,
        "/auth/web/login",
        {
            "login": "admin_01",
            "password": TEST_PASSWORD,
        },
    )
    assert response.status_code == 200
    assert response.json()["user"]["recovery_required"] is True
    old_access = auth_env.client.cookies.get(ACCESS_COOKIE)
    assert auth_env.client.get(PREFIX + "/products/").status_code == 403
    code = web_post(
        auth_env.client,
        "/auth/recovery/code",
        {
            "current_password": TEST_PASSWORD,
        },
    ).json()["recovery_code"]
    assert (
        web_post(
            auth_env.client,
            "/auth/recovery/activate",
            {
                "recovery_code": code,
                "saved": True,
            },
        ).status_code
        == 200
    )
    assert auth_env.client.get(PREFIX + "/products/").status_code == 200
    assert recover(auth_env, code).status_code == 200
    assert not auth_env.client.cookies.get(ACCESS_COOKIE)
    assert (
        auth_env.client.get(
            PREFIX + "/auth/me",
            headers={
                "Authorization": "Bearer " + old_access,
            },
        ).status_code
        == 401
    )
    response = web_post(
        auth_env.client,
        "/auth/web/login",
        {
            "login": "admin_01",
            "password": NEW_PASSWORD,
        },
    )
    assert response.json()["status"] == "authenticated"
    assert response.json()["user"]["recovery_required"] is True
    assert auth_env.client.get(PREFIX + "/products/").status_code == 403
