"""认证接口测试：注册 / 登录 / 刷新 / 登出 / 协议留痕。"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi.testclient import TestClient

from app.core.config import settings

EMAIL = f"auth_{uuid.uuid4().hex[:10]}@example.com"
PASSWORD = "Passw0rd123"


def _register(client: TestClient, email: str = EMAIL, password: str = PASSWORD) -> Any:
    return client.post("/api/v1/auth/register", json={"email": email, "password": password})


def test_register_returns_token_and_cookie(client: TestClient) -> None:
    response = _register(client)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["expires_in"] > 0
    assert body["user"]["email"] == EMAIL
    assert "password" not in response.text
    assert settings.refresh_cookie_name in response.cookies


def test_duplicate_email_is_conflict(client: TestClient) -> None:
    _register(client)
    response = _register(client)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EMAIL_TAKEN"


def test_duplicate_email_is_case_insensitive(client: TestClient) -> None:
    email = f"case_{uuid.uuid4().hex[:8]}@example.com"
    _register(client, email=email)
    response = _register(client, email=email.upper())
    assert response.status_code == 409


def test_weak_password_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register", json={"email": f"w_{uuid.uuid4().hex[:8]}@example.com", "password": "12345678"}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_invalid_email_rejected(client: TestClient) -> None:
    response = client.post("/api/v1/auth/register", json={"email": "not-an-email", "password": PASSWORD})
    assert response.status_code == 422


def test_consent_must_be_accepted(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"c_{uuid.uuid4().hex[:8]}@example.com",
            "password": PASSWORD,
            "consent": {"accepted": False},
        },
    )
    assert response.status_code == 422


def test_consents_are_recorded(client: TestClient) -> None:
    token = _register(client).json()["access_token"]
    response = client.get("/api/v1/me/consents", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    items = response.json()["items"]
    assert {item["doc_type"] for item in items} == {"privacy", "terms"}
    assert all(item["doc_version"] for item in items)


def test_login_and_me(client: TestClient) -> None:
    _register(client)
    response = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert response.status_code == 200
    token = response.json()["access_token"]

    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == EMAIL


def test_login_with_wrong_password_is_401(client: TestClient) -> None:
    _register(client)
    response = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": "WrongPass123"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"
    # 不得暴露"用户是否存在"
    assert EMAIL not in response.text


def test_login_unknown_user_is_401(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/login", json={"email": f"none_{uuid.uuid4().hex[:8]}@example.com", "password": PASSWORD}
    )
    assert response.status_code == 401


def test_me_requires_token(client: TestClient) -> None:
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.json()["error"]["request_id"]


def test_refresh_rotates_access_token(client: TestClient) -> None:
    _register(client)
    first = client.post("/api/v1/auth/refresh")
    assert first.status_code == 200
    assert first.json()["access_token"]
    me = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {first.json()['access_token']}"}
    )
    assert me.status_code == 200


def test_refresh_without_cookie_is_401(client: TestClient) -> None:
    client.cookies.clear()
    response = client.post("/api/v1/auth/refresh")
    assert response.status_code == 401


def test_logout_invalidates_tokens(client: TestClient) -> None:
    token = _register(client).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 204

    # access token 因 token_version 变化立即失效
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401
    # refresh 也失效
    assert client.post("/api/v1/auth/refresh").status_code == 401


def test_tampered_token_rejected(client: TestClient) -> None:
    _register(client)
    response = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not.a.real.token"})
    assert response.status_code == 401


def test_error_envelope_shape(client: TestClient) -> None:
    response = client.get("/api/v1/charts/999999")
    body = response.json()
    assert set(body) == {"error"}
    assert {"code", "message", "request_id"} <= set(body["error"])
