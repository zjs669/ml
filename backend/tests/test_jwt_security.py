"""JWT 与登录防爆破的攻击面用例。

每个用例对应一种真实存在的攻击手法，失败即代表防线破了：
- `alg=none` 与签名篡改（算法混淆）
- 换系统签发（iss/aud 不符）
- access / refresh 混用
- 过期令牌
- 登出后旧 access 仍可用
- refresh 重放（同族整链作废）
- 撞库（按账号锁定）
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import jwt
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.security import ALGORITHM, AUDIENCE, ISSUER

ME = "/api/v1/auth/me"
LOGIN = "/api/v1/auth/login"
REGISTER = "/api/v1/auth/register"
REFRESH = "/api/v1/auth/refresh"
LOGOUT = "/api/v1/auth/logout"


def _register(client: TestClient, password: str = "Passw0rd123") -> tuple[str, str]:
    email = f"jwt_{uuid.uuid4().hex[:8]}@example.com"
    response = client.post(REGISTER, json={"email": email, "password": password})
    assert response.status_code == 201, response.text
    return email, response.json()["access_token"]


def _claims(**overrides) -> dict:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": "1",
        "typ": "access",
        "ver": 0,
        "iss": ISSUER,
        "aud": AUDIENCE,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=5)).timestamp()),
        "jti": uuid.uuid4().hex,
    }
    payload.update(overrides)
    return payload


def test_alg_none_rejected(client: TestClient) -> None:
    _, access = _register(client)
    forged = jwt.encode(_claims(sub="1"), key="", algorithm="none")
    response = client.get(ME, headers={"Authorization": f"Bearer {forged}"})
    assert response.status_code == 401
    # 正常令牌仍然可用，说明拒绝原因是算法而不是用户
    assert client.get(ME, headers={"Authorization": f"Bearer {access}"}).status_code == 200


def test_tampered_signature_rejected(client: TestClient) -> None:
    _, access = _register(client)
    header, payload, _signature = access.split(".")
    forged = f"{header}.{payload}.{'a' * 43}"
    assert client.get(ME, headers={"Authorization": f"Bearer {forged}"}).status_code == 401


def test_foreign_issuer_or_audience_rejected(client: TestClient) -> None:
    _, access = _register(client)
    claims = jwt.decode(access, settings.secret_key, algorithms=[ALGORITHM], audience=AUDIENCE, issuer=ISSUER)

    wrong_iss = jwt.encode({**claims, "iss": "other-service"}, settings.secret_key, algorithm=ALGORITHM)
    wrong_aud = jwt.encode({**claims, "aud": "other-api"}, settings.secret_key, algorithm=ALGORITHM)
    missing = {key: value for key, value in claims.items() if key not in ("iss", "aud")}
    missing_both = jwt.encode(missing, settings.secret_key, algorithm=ALGORITHM)

    for token in (wrong_iss, wrong_aud, missing_both):
        assert client.get(ME, headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_expired_access_rejected(client: TestClient) -> None:
    _, access = _register(client)
    claims = jwt.decode(access, settings.secret_key, algorithms=[ALGORITHM], audience=AUDIENCE, issuer=ISSUER)
    expired = jwt.encode(
        {**claims, "exp": int((datetime.now(timezone.utc) - timedelta(minutes=1)).timestamp())},
        settings.secret_key,
        algorithm=ALGORITHM,
    )
    assert client.get(ME, headers={"Authorization": f"Bearer {expired}"}).status_code == 401


def test_access_token_cannot_be_used_as_refresh(client: TestClient) -> None:
    _, access = _register(client)
    response = client.post(REFRESH, cookies={settings.refresh_cookie_name: access})
    assert response.status_code == 401


def test_logout_invalidates_old_access(client: TestClient) -> None:
    _, access = _register(client)
    headers = {"Authorization": f"Bearer {access}"}
    assert client.get(ME, headers=headers).status_code == 200
    assert client.post(LOGOUT, headers=headers).status_code == 204
    # token_version 前进后，同一枚 access 立刻失效
    assert client.get(ME, headers=headers).status_code == 401


def test_refresh_rotation_and_replay_detection(client: TestClient) -> None:
    email, _ = _register(client)
    first = client.cookies.get(settings.refresh_cookie_name)
    assert first

    rotated = client.post(REFRESH, cookies={settings.refresh_cookie_name: first})
    assert rotated.status_code == 200, rotated.text
    second = client.cookies.get(settings.refresh_cookie_name)
    assert second and second != first

    # 再用旧 refresh：视为重放 → 整族作废
    replay = client.post(REFRESH, cookies={settings.refresh_cookie_name: first})
    assert replay.status_code == 401

    # 同族的新 refresh 也一起失效，必须重新登录
    after = client.post(REFRESH, cookies={settings.refresh_cookie_name: second})
    assert after.status_code == 401
    assert client.post(LOGIN, json={"email": email, "password": "Passw0rd123"}).status_code == 200


def test_login_lockout_after_repeated_failures(client: TestClient) -> None:
    email, _ = _register(client)

    for _ in range(settings.login_max_failures):
        assert client.post(LOGIN, json={"email": email, "password": "WrongPass1"}).status_code == 401

    # 锁定期内即使密码正确也拒绝，并给出明确错误码
    locked = client.post(LOGIN, json={"email": email, "password": "Passw0rd123"})
    assert locked.status_code == 429
    assert locked.json()["error"]["code"] == "ACCOUNT_LOCKED"


def test_sessions_endpoint_reports_and_revokes(client: TestClient) -> None:
    _, access = _register(client)
    headers = {"Authorization": f"Bearer {access}"}

    before = client.get("/api/v1/auth/sessions", headers=headers)
    assert before.status_code == 200
    assert before.json()["active_sessions"] >= 1

    revoked = client.delete("/api/v1/auth/sessions", headers=headers)
    assert revoked.status_code == 200
    assert revoked.json()["active_sessions"] == 0
    # 全部设备下线后，这枚 access 也不能再用
    assert client.get(ME, headers=headers).status_code == 401
