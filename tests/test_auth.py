from concurrent.futures import ThreadPoolExecutor
from time import time
from uuid import uuid4

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update

from app.core.config import settings
from app.core.cookies import ACCESS_COOKIE, CSRF_COOKIE, PENDING_COOKIE, REFRESH_COOKIE
from app.core.tokens import create_access_token, decode_token
from app.models.auth_session import AuthSession
from app.models.user import User
from tests.conftest import TEST_PASSWORD

NEW_PASSWORD = "A new permanent password 456"
PREFIX = "/api/v1"


def login(client, login="worker_01", password=TEST_PASSWORD):
    response = client.post(PREFIX + "/auth/login", json={"login": login, "password": password})
    assert response.status_code == 200, response.text
    return response.json()


def headers(pair):
    return {"Authorization": "Bearer " + pair["access_token"]}


def refresh(client, pair):
    return client.post(PREFIX + "/auth/refresh", json={"refresh_token": pair["refresh_token"]})


def me(client, pair):
    return client.get(PREFIX + "/auth/me", headers=headers(pair))


def web_post(client, path, data=None):
    if not client.cookies.get(CSRF_COOKIE):
        assert client.get(PREFIX + "/auth/web/csrf").status_code == 200
    return client.post(
        PREFIX + path, json=data,
        headers={"X-CSRF-Token": client.cookies.get(CSRF_COOKIE)},
    )


def sign(payload):
    return jwt.encode(payload, settings.jwt_secret_key.get_secret_value(), algorithm="HS256")


def session_count(environment, open_only=True):
    async def count(db):
        query = select(func.count()).select_from(AuthSession)
        if open_only:
            query = query.where(AuthSession.revoked_at.is_(None))
        return await db.scalar(query)
    return environment.database(count)


@pytest.mark.parametrize("path", ["/products/", "/shelves/", "/stock/", "/auth/me", "/users/"])
def test_anonymous_cannot_use_warehouse(auth_env, path):
    assert auth_env.client.get(PREFIX + path).status_code == 401


def test_invalid_credentials_have_same_response(auth_env):
    auth_env.create_user()
    unknown = auth_env.client.post(PREFIX + "/auth/login", json={
        "login": "unknown_user", "password": TEST_PASSWORD,
    })
    wrong = auth_env.client.post(PREFIX + "/auth/login", json={
        "login": "WORKER_01", "password": "wrong",
    })
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json() == wrong.json()


def test_temporary_password_only_allows_setup_and_survives_failed_setup(auth_env):
    auth_env.create_user(temporary=True)
    first = login(auth_env.client)
    second = login(auth_env.client)
    assert first["status"] == second["status"] == "password_setup"
    assert "access_token" not in first and "refresh_token" not in first
    assert auth_env.client.get(PREFIX + "/products/", headers={
        "Authorization": "Bearer " + first["password_setup_token"],
    }).status_code == 401
    assert auth_env.client.post(PREFIX + "/auth/password/setup", json={
        "password_setup_token": first["password_setup_token"], "new_password": "123",
    }).status_code == 422
    assert login(auth_env.client)["status"] == "password_setup"
    unchanged = auth_env.client.post(PREFIX + "/auth/password/setup", json={
        "password_setup_token": first["password_setup_token"], "new_password": TEST_PASSWORD,
    })
    assert unchanged.status_code == 400
    # No common-password blocklist: this deliberately simple 15-character password is accepted.
    result = auth_env.client.post(PREFIX + "/auth/password/setup", json={
        "password_setup_token": first["password_setup_token"], "new_password": "a" * 15,
    })
    assert result.status_code == 200, result.text
    assert result.json()["user"]["must_change_password"] is False
    assert me(auth_env.client, result.json()).status_code == 200
    assert auth_env.client.post(PREFIX + "/auth/login", json={
        "login": "worker_01", "password": TEST_PASSWORD,
    }).status_code == 401
    assert auth_env.client.post(PREFIX + "/auth/password/setup", json={
        "password_setup_token": second["password_setup_token"], "new_password": NEW_PASSWORD,
    }).status_code == 401
    assert session_count(auth_env) == 1


def test_new_login_requires_explicit_confirmation_and_cannot_replay(auth_env):
    auth_env.create_user()
    old = login(auth_env.client)
    challenge = login(auth_env.client, "WORKER_01")
    assert challenge["status"] == "confirm_login"
    assert "access_token" not in challenge and "refresh_token" not in challenge
    assert me(auth_env.client, old).status_code == 200
    for data in ({}, {"confirm": False}):
        result = auth_env.client.post(PREFIX + "/auth/confirm-login", json={
            "confirmation_token": challenge["confirmation_token"], **data,
        })
        assert result.status_code == 422
    assert me(auth_env.client, old).status_code == 200
    new = auth_env.client.post(PREFIX + "/auth/confirm-login", json={
        "confirmation_token": challenge["confirmation_token"], "confirm": True,
    })
    assert new.status_code == 200, new.text
    assert me(auth_env.client, old).status_code == 401
    assert refresh(auth_env.client, old).status_code == 401
    assert me(auth_env.client, new.json()).status_code == 200
    assert auth_env.client.post(PREFIX + "/auth/confirm-login", json={
        "confirmation_token": challenge["confirmation_token"], "confirm": True,
    }).status_code == 409
    assert me(auth_env.client, new.json()).status_code == 200
    assert session_count(auth_env) == 1
    assert session_count(auth_env, False) == 2


def test_expired_confirmation_does_not_end_previous_session(auth_env):
    auth_env.create_user()
    old = login(auth_env.client)
    challenge = login(auth_env.client)
    payload = decode_token(challenge["confirmation_token"], "login_confirm").model_dump(exclude_none=True)
    payload.update(iat=int(time()) - 301, exp=int(time()) - 1)
    response = auth_env.client.post(PREFIX + "/auth/confirm-login", json={
        "confirmation_token": sign(payload), "confirm": True,
    })
    assert response.status_code == 401
    assert me(auth_env.client, old).status_code == 200


def test_refresh_rotates_and_reuse_revokes_session(auth_env):
    auth_env.create_user()
    original = login(auth_env.client)
    rotated = refresh(auth_env.client, original)
    assert rotated.status_code == 200, rotated.text
    assert rotated.json()["refresh_token"] != original["refresh_token"]
    assert rotated.json()["session_expires_at"] == original["session_expires_at"]
    assert me(auth_env.client, original).status_code == 200
    reused = refresh(auth_env.client, original)
    assert reused.status_code == 401
    assert reused.json()["code"] == "refresh_reused"
    assert me(auth_env.client, rotated.json()).status_code == 401
    assert refresh(auth_env.client, rotated.json()).status_code == 401
    assert session_count(auth_env) == 0


def test_absolute_session_expiry_and_access_cap(auth_env):
    auth_env.create_user()
    original = login(auth_env.client)
    claims = decode_token(original["refresh_token"], "refresh")
    expires_at = int(time()) + 120

    async def shorten(db):
        await db.execute(update(AuthSession).where(AuthSession.id == claims.sid).values(expires_at=expires_at))
    auth_env.database(shorten)
    rotated = refresh(auth_env.client, original).json()
    assert rotated["session_expires_at"] == expires_at
    assert decode_token(rotated["access_token"], "access").exp == expires_at
    assert decode_token(rotated["refresh_token"], "refresh").exp == expires_at

    async def expire(db):
        await db.execute(update(AuthSession).where(AuthSession.id == claims.sid).values(expires_at=int(time()) - 1))
    auth_env.database(expire)
    assert me(auth_env.client, rotated).status_code == 401
    assert refresh(auth_env.client, rotated).status_code == 401
    assert login(auth_env.client)["status"] == "authenticated"
    assert session_count(auth_env) == 1


def test_access_lifetime_and_expired_access_can_refresh(auth_env):
    auth_env.create_user()
    pair = login(auth_env.client)
    payload = decode_token(pair["access_token"], "access").model_dump(exclude_none=True)
    assert payload["exp"] - payload["iat"] == 900
    assert pair["session_expires_at"] - payload["iat"] == 43200
    payload.update(iat=int(time()) - 901, exp=int(time()) - 1)
    assert auth_env.client.get(PREFIX + "/auth/me", headers={
        "Authorization": "Bearer " + sign(payload),
    }).status_code == 401
    assert refresh(auth_env.client, pair).status_code == 200
    capped = create_access_token(1, str(uuid4()), int(time()) + 60)
    claims = decode_token(capped, "access")
    assert 0 < claims.exp - claims.iat <= 60


def test_password_change_revokes_session_and_preserves_spaces(auth_env):
    auth_env.create_user()
    pair = login(auth_env.client)
    wrong = auth_env.client.post(PREFIX + "/auth/password/change", headers=headers(pair), json={
        "current_password": "wrong", "new_password": NEW_PASSWORD,
    })
    assert wrong.status_code == 400
    assert me(auth_env.client, pair).status_code == 200
    new_password = "  " + NEW_PASSWORD + "  "
    result = auth_env.client.post(PREFIX + "/auth/password/change", headers=headers(pair), json={
        "current_password": TEST_PASSWORD, "new_password": new_password,
    })
    assert result.status_code == 200, result.text
    assert "access_token" not in result.json()
    assert me(auth_env.client, pair).status_code == 401
    assert refresh(auth_env.client, pair).status_code == 401
    assert auth_env.client.post(PREFIX + "/auth/login", json={
        "login": "worker_01", "password": TEST_PASSWORD,
    }).status_code == 401
    assert login(auth_env.client, password=new_password)["status"] == "authenticated"


def test_stale_confirmation_after_password_change_cannot_kill_new_session(auth_env):
    auth_env.create_user()
    old = login(auth_env.client)
    challenge = login(auth_env.client)
    assert auth_env.client.post(PREFIX + "/auth/password/change", headers=headers(old), json={
        "current_password": TEST_PASSWORD, "new_password": NEW_PASSWORD,
    }).status_code == 200
    new = login(auth_env.client, password=NEW_PASSWORD)
    assert auth_env.client.post(PREFIX + "/auth/confirm-login", json={
        "confirmation_token": challenge["confirmation_token"], "confirm": True,
    }).status_code == 409
    assert me(auth_env.client, new).status_code == 200


@pytest.mark.parametrize("role", ["worker", "admin"])
def test_admin_creates_both_roles_and_reset_invalidates_setup_tokens(auth_env, role):
    auth_env.create_user("admin_01", "admin")
    admin = login(auth_env.client, "admin_01")
    created = auth_env.client.post(PREFIX + "/users/", headers=headers(admin), json={
        "login": "NEW_USER", "full_name": "Новый пользователь", "role": role,
    })
    assert created.status_code == 201, created.text
    account = created.json()
    assert account["user"]["role"] == role
    assert account["user"]["login"] == "new_user"
    assert "password_hash" not in account["user"]
    assert len(account["temporary_password"]) == 16
    pending = login(auth_env.client, "new_user", account["temporary_password"])
    reset = auth_env.client.post(
        PREFIX + f'/users/{account["user"]["id"]}/reset-password', headers=headers(admin),
    )
    assert reset.status_code == 200, reset.text
    assert auth_env.client.post(PREFIX + "/auth/password/setup", json={
        "password_setup_token": pending["password_setup_token"], "new_password": NEW_PASSWORD,
    }).status_code == 401
    assert login(auth_env.client, "new_user", reset.json()["temporary_password"])["status"] == "password_setup"
    assert auth_env.client.post(PREFIX + "/users/", headers=headers(admin), json={
        "login": "NEW_USER", "full_name": "Дубликат",
    }).status_code == 409
    listed = auth_env.client.get(PREFIX + "/users/", headers=headers(admin))
    assert listed.status_code == 200
    assert all("password_hash" not in user and "credential_version" not in user for user in listed.json())


@pytest.mark.parametrize("role", ["worker", "admin"])
def test_reset_ends_target_session(auth_env, role):
    auth_env.create_user("admin_01", "admin")
    target_id = auth_env.create_user("target_01", role)
    admin = login(auth_env.client, "admin_01")
    target = login(auth_env.client, "target_01")
    response = auth_env.client.post(PREFIX + f"/users/{target_id}/reset-password", headers=headers(admin))
    assert response.status_code == 200
    assert me(auth_env.client, target).status_code == 401
    assert refresh(auth_env.client, target).status_code == 401
    assert me(auth_env.client, admin).status_code == 200


def test_worker_can_work_but_cannot_delete_or_manage_users(auth_env):
    auth_env.create_user()
    worker = login(auth_env.client)
    auth = headers(worker)
    assert auth_env.client.post(PREFIX + "/products/", headers=auth, json={
        "name": "Товар", "barcode": "12345",
    }).status_code == 200
    assert auth_env.client.post(PREFIX + "/shelves/", headers=auth, json={"code": "A1"}).status_code == 200
    assert auth_env.client.post(PREFIX + "/stock/", headers=auth, json={
        "product_barcode": "12345", "shelf_code": "A1", "quantity": 2,
    }).status_code == 200
    assert auth_env.client.patch(PREFIX + "/stock/", headers=auth, params={
        "barcode": "12345", "shelf_code": "A1", "adding": 3,
    }).status_code == 200
    assert auth_env.client.get(PREFIX + "/stock/", headers=auth).json()[0]["quantity"] == 5
    for path in ("/products/", "/stock/"):
        response = auth_env.client.delete(PREFIX + path, headers=auth, params={
            "barcode": "12345", "shelf_code": "A1",
        })
        assert response.status_code == 403 and response.json()["code"] == "forbidden"
    for path in ("/products/del_any", "/stock/delete-form"):
        response = auth_env.client.post(PREFIX + path, headers=auth, data={
            "barcode": "12345", "shelf_code": "A1",
        })
        assert response.status_code == 403 and response.json()["code"] == "forbidden"
    assert auth_env.client.get(PREFIX + "/users/", headers=auth).status_code == 403
    assert auth_env.client.post(PREFIX + "/users/", headers=auth, json={
        "login": "other_user", "full_name": "Другой пользователь",
    }).status_code == 403
    assert auth_env.client.post(PREFIX + "/users/1/reset-password", headers=auth).status_code == 403


def test_logout_ends_access_and_refresh_immediately(auth_env):
    auth_env.create_user()
    pair = login(auth_env.client)
    assert auth_env.client.post(PREFIX + "/auth/logout", headers=headers(pair)).status_code == 204
    assert me(auth_env.client, pair).status_code == 401
    assert refresh(auth_env.client, pair).status_code == 401
    assert login(auth_env.client)["status"] == "authenticated"


def test_web_cookies_csrf_refresh_and_logout(auth_env):
    auth_env.create_user()
    client = auth_env.client
    data = {"login": "worker_01", "password": TEST_PASSWORD}
    assert client.post(PREFIX + "/auth/web/login", json=data).status_code == 403
    result = web_post(client, "/auth/web/login", data)
    assert result.status_code == 200, result.text
    assert result.json()["status"] == "authenticated"
    assert "access_token" not in result.json() and "refresh_token" not in result.json()
    cookies = result.headers.get_list("set-cookie")
    assert any(ACCESS_COOKIE in value and "HttpOnly" in value for value in cookies)
    assert any(REFRESH_COOKIE in value and "HttpOnly" in value for value in cookies)
    assert all("SameSite=strict" in value for value in cookies)
    assert result.headers["cache-control"] == "no-store"
    assert client.get(PREFIX + "/auth/me").status_code == 200
    assert client.post(PREFIX + "/shelves/form", data={"code": "A1"}).status_code == 403
    assert client.post(PREFIX + "/shelves/form", data={"code": "A1"}, headers={
        "X-CSRF-Token": client.cookies.get(CSRF_COOKIE),
    }).status_code == 200
    previous_csrf = client.cookies.get(CSRF_COOKIE)
    previous_refresh = client.cookies.get(REFRESH_COOKIE)
    client.cookies.delete(ACCESS_COOKIE)
    assert client.get(PREFIX + "/auth/me").status_code == 401
    assert web_post(client, "/auth/web/refresh").status_code == 200
    assert client.cookies.get(REFRESH_COOKIE) != previous_refresh
    assert client.cookies.get(CSRF_COOKIE) == previous_csrf
    assert client.get(PREFIX + "/auth/me").status_code == 200
    assert web_post(client, "/auth/web/logout").status_code == 204
    assert not client.cookies.get(ACCESS_COOKIE) and not client.cookies.get(REFRESH_COOKIE)


def test_web_cancel_preserves_old_session_and_confirm_replaces_it(auth_env):
    auth_env.create_user()
    client = auth_env.client
    data = {"login": "worker_01", "password": TEST_PASSWORD}
    assert web_post(client, "/auth/web/login", data).status_code == 200
    with TestClient(auth_env.application) as other:
        pending = web_post(other, "/auth/web/login", data)
        assert pending.json()["status"] == "confirm_login"
        assert other.cookies.get(PENDING_COOKIE)
        assert client.get(PREFIX + "/auth/me").status_code == 200
        assert web_post(other, "/auth/web/cancel-login").status_code == 200
        assert not other.cookies.get(PENDING_COOKIE)
        assert client.get(PREFIX + "/auth/me").status_code == 200
        assert web_post(other, "/auth/web/login", data).json()["status"] == "confirm_login"
        assert web_post(other, "/auth/web/confirm-login", {"confirm": True}).status_code == 200
        assert other.get(PREFIX + "/auth/me").status_code == 200
        assert client.get(PREFIX + "/auth/me").status_code == 401


def test_web_temporary_password_setup(auth_env):
    auth_env.create_user(temporary=True)
    result = web_post(auth_env.client, "/auth/web/login", {"login": "worker_01", "password": TEST_PASSWORD})
    assert result.json()["status"] == "password_setup"
    assert auth_env.client.cookies.get(PENDING_COOKIE)
    assert not auth_env.client.cookies.get(ACCESS_COOKIE)
    assert auth_env.client.get(PREFIX + "/auth/me").status_code == 401
    result = web_post(auth_env.client, "/auth/web/password/setup", {"new_password": NEW_PASSWORD})
    assert result.status_code == 200, result.text
    assert not auth_env.client.cookies.get(PENDING_COOKIE)
    assert auth_env.client.get(PREFIX + "/auth/me").status_code == 200


def test_validation_does_not_echo_passwords(auth_env):
    secret = "do-not-echo-" + "x" * 150
    response = auth_env.client.post(PREFIX + "/auth/login", json={"login": "worker_01", "password": secret})
    assert response.status_code == 422
    assert secret not in response.text and "input" not in response.json()["detail"][0]


@pytest.mark.parametrize("claim,value", [
    ("credential_version", True), ("credential_version", -1),
    ("sid", "not-a-uuid"), ("jti", 123), ("token_type", "refresh"),
    ("aud", "another-app"), ("iss", "another-server"), ("exp", "9999999999"),
    ("sub", "99999999999999999999"),
])
def test_rejects_wrong_claims(auth_env, claim, value):
    auth_env.create_user()
    pair = login(auth_env.client)
    payload = decode_token(pair["access_token"], "access").model_dump(exclude_none=True)
    payload[claim] = value
    assert auth_env.client.get(PREFIX + "/auth/me", headers={
        "Authorization": "Bearer " + sign(payload),
    }).status_code == 401


@pytest.mark.parametrize("variant", ["wrong-key", "wrong-algorithm", "unsigned", "missing-exp"])
def test_rejects_invalid_signatures_and_missing_exp(auth_env, variant):
    auth_env.create_user()
    pair = login(auth_env.client)
    payload = decode_token(pair["access_token"], "access").model_dump(exclude_none=True)
    key, algorithm = settings.jwt_secret_key.get_secret_value(), "HS256"
    if variant == "wrong-key":
        key = "a completely different testing key" * 2
    elif variant == "wrong-algorithm":
        algorithm = "HS512"
    elif variant == "unsigned":
        key, algorithm = "", "none"
    else:
        del payload["exp"]
    token = jwt.encode(payload, key, algorithm=algorithm)
    assert auth_env.client.get(PREFIX + "/auth/me", headers={"Authorization": "Bearer " + token}).status_code == 401


def test_concurrent_login_creates_only_one_session(auth_env):
    auth_env.create_user()
    def attempt(_):
        return auth_env.client.post(PREFIX + "/auth/login", json={"login": "worker_01", "password": TEST_PASSWORD})
    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(attempt, range(2)))
    assert all(response.status_code == 200 for response in responses)
    assert sorted(response.json()["status"] for response in responses) == ["authenticated", "confirm_login"]
    assert session_count(auth_env) == 1


def test_concurrent_refresh_is_single_use(auth_env):
    auth_env.create_user()
    pair = login(auth_env.client)
    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(lambda _: refresh(auth_env.client, pair), range(2)))
    assert sorted(response.status_code for response in responses) == [200, 401]
    assert next(response for response in responses if response.status_code == 401).json()["code"] == "refresh_reused"
    assert session_count(auth_env) == 0


@pytest.mark.parametrize("form_route", [False, True])
def test_admin_can_use_both_deletion_routes(auth_env, form_route):
    auth_env.create_user(login="admin_01", role="admin")
    client = auth_env.client
    auth = headers(login(client, "admin_01"))
    assert client.post(PREFIX + "/products/", json={"name": "Product", "barcode": "p1"}, headers=auth).status_code == 200
    assert client.post(PREFIX + "/shelves/", json={"code": "S1"}, headers=auth).status_code == 200
    assert client.post(PREFIX + "/stock/", json={"product_barcode": "p1", "shelf_code": "S1", "quantity": 2}, headers=auth).status_code == 200
    if form_route:
        deleted = client.post(PREFIX + "/stock/delete-form", data={"barcode": "p1", "shelf_code": "S1"}, headers=auth)
        assert deleted.status_code == 200
        deleted = client.post(PREFIX + "/products/del_any", data={"barcode": "p1"}, headers=auth)
    else:
        deleted = client.delete(PREFIX + "/stock/", params={"barcode": "p1", "shelf_code": "S1"}, headers=auth)
        assert deleted.status_code == 200
        deleted = client.delete(PREFIX + "/products/", params={"barcode": "p1"}, headers=auth)
    assert deleted.status_code == 200
    assert client.get(PREFIX + "/products/", headers=auth).json() == []


def test_worker_browser_forms_and_password_change(auth_env):
    auth_env.create_user()
    client = auth_env.client
    assert web_post(client, "/auth/web/login", {"login": "worker_01", "password": TEST_PASSWORD}).status_code == 200
    csrf = {"X-CSRF-Token": client.cookies.get(CSRF_COOKIE)}
    for path, data in [
        ("/products/form", {"name": "Product", "barcode": "p1"}),
        ("/shelves/form", {"code": "S1"}),
        ("/stock/form", {"product_barcode": "p1", "shelf_code": "S1", "quantity": 2}),
        ("/stock/patch-form", {"barcode": "p1", "shelf_code": "S1", "adding": 3}),
    ]:
        assert client.post(PREFIX + path, data=data, headers=csrf).status_code == 200
    assert client.get(PREFIX + "/stock/").json()[0]["quantity"] == 5
    assert web_post(client, "/auth/password/change", {"current_password": TEST_PASSWORD, "new_password": NEW_PASSWORD}).status_code == 200
    assert not client.cookies.get(ACCESS_COOKIE) and not client.cookies.get(REFRESH_COOKIE)
    assert client.get(PREFIX + "/auth/me").status_code == 401


def test_forged_csrf_and_previous_session_csrf_are_rejected(auth_env):
    auth_env.create_user()
    client = auth_env.client
    client.cookies.set(CSRF_COOKIE, "anonymous." + "a" * 64 + ".forged", domain="testserver.local", path="/")
    assert web_post(client, "/auth/web/login", {"login": "worker_01", "password": TEST_PASSWORD}).status_code == 403
    client.get(PREFIX + "/auth/web/csrf")
    assert web_post(client, "/auth/web/login", {"login": "worker_01", "password": TEST_PASSWORD}).status_code == 200
    old_csrf = client.cookies.get(CSRF_COOKIE)
    assert web_post(client, "/auth/web/logout").status_code == 204
    assert web_post(client, "/auth/web/login", {"login": "worker_01", "password": TEST_PASSWORD}).status_code == 200
    client.cookies.set(CSRF_COOKIE, old_csrf, domain="testserver.local", path="/")
    assert client.post(PREFIX + "/shelves/form", data={"code": "S1"}, headers={"X-CSRF-Token": old_csrf}).status_code == 403


def test_concurrent_password_setup_is_single_use(auth_env):
    auth_env.create_user(temporary=True)
    pending = login(auth_env.client)
    def attempt(_):
        return auth_env.client.post(PREFIX + "/auth/password/setup", json={
            "password_setup_token": pending["password_setup_token"], "new_password": NEW_PASSWORD,
        })
    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(attempt, range(2)))
    assert sorted(response.status_code for response in responses) == [200, 401]
    assert session_count(auth_env) == 1


def test_expired_setup_does_not_consume_temporary_password(auth_env):
    auth_env.create_user(temporary=True)
    pending = login(auth_env.client)
    payload = decode_token(pending["password_setup_token"], "password_setup").model_dump(exclude_none=True)
    payload.update(iat=int(time()) - 120, exp=int(time()) - 60)
    assert auth_env.client.post(PREFIX + "/auth/password/setup", json={
        "password_setup_token": sign(payload), "new_password": NEW_PASSWORD,
    }).status_code == 401
    assert login(auth_env.client)["status"] == "password_setup"
    assert session_count(auth_env) == 0


def test_bootstrap_refuses_second_admin(auth_env):
    from app.schemas.users import UserCreate
    from app.services.users import FirstAdminAlreadyExists, create_first_admin
    async def create(db):
        return await create_first_admin(UserCreate(login="admin_01", full_name="First Admin", role="admin"), db)
    first = auth_env.database(create)
    assert first.user.must_change_password
    assert len(first.temporary_password) == 16
    with pytest.raises(FirstAdminAlreadyExists):
        auth_env.database(create)


@pytest.mark.parametrize("page", ["login", "password", "users", "index", "shelf", "shelf_stock", "update_shelf_stock", "delete_product", "delete_shelf_stock"])
def test_static_pages_include_auth_script(auth_env, page):
    response = auth_env.client.get(f"/static/{page}.html")
    assert response.status_code == 200
    assert '<script src="/static/auth.js" defer></script>' in response.text
    assert 'method="post"' in response.text
