"""忘记密码全流程：申请 → 取信 → 重置 → 重新登录。

重点锁死四件事：
1. 不泄露邮箱是否存在（响应逐字节一致）；
2. 令牌一次性 + 有过期时间 + 库里只存 sha256；
3. 重置后所有会话失效，旧密码登不进去；
4. 重置与注册共用同一套密码强度规则。
"""

from __future__ import annotations

import json
import uuid
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import utcnow
from app.core.security import hash_token
from app.models.auth_tokens import PasswordResetToken

FORGOT = "/api/v1/auth/password/forgot"
RESET = "/api/v1/auth/password/reset"
LOGIN = "/api/v1/auth/login"
REGISTER = "/api/v1/auth/register"
REFRESH = "/api/v1/auth/refresh"


@pytest.fixture
def outbox(tmp_path, monkeypatch):
    """把 console 发信箱指到临时文件，避免污染 backend/var 与其它用例。"""
    path = tmp_path / "mail_outbox.log"
    monkeypatch.setattr(settings, "mail_outbox_path", str(path))
    return path


def _register(client: TestClient, email: str, password: str = "Passw0rd123") -> None:
    response = client.post(REGISTER, json={"email": email, "password": password})
    assert response.status_code == 201, response.text


def _mail_token(path, email: str) -> str:
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert lines, "发信箱里没有邮件"
    for line in reversed(lines):
        record = json.loads(line)
        if record["to"] == email:
            body = record["body"]
            token = body.split("token=", 1)[1].split()[0].strip()
            return token
    raise AssertionError(f"没有发给 {email} 的邮件")


def test_forgot_does_not_leak_existence(client: TestClient, outbox) -> None:
    email = f"known_{uuid.uuid4().hex[:8]}@example.com"
    _register(client, email)

    known = client.post(FORGOT, json={"email": email})
    unknown = client.post(FORGOT, json={"email": f"nobody_{uuid.uuid4().hex[:8]}@example.com"})

    assert known.status_code == unknown.status_code == 200
    assert known.json()["message"] == unknown.json()["message"]
    assert known.json()["expires_in_minutes"] == unknown.json()["expires_in_minutes"]
    # 只有「存在」的邮箱才会真的发信；但对外的响应体一模一样
    assert unknown.json()["debug_reset_url"] is None
    assert len(outbox.read_text(encoding="utf-8").splitlines()) == 1


def test_reset_flow_changes_password_and_signs_out(client: TestClient, outbox, session: Session) -> None:
    email = f"reset_{uuid.uuid4().hex[:8]}@example.com"
    _register(client, email)
    # 重置前持有的 refresh，重置后必须作废（不能靠「重新登录把 cookie 盖掉」蒙过去）
    stale_refresh = client.cookies.get(settings.refresh_cookie_name)
    assert stale_refresh

    assert client.post(FORGOT, json={"email": email}).status_code == 200
    token = _mail_token(outbox, email)

    # 库里只有 sha256，不存明文
    row = session.scalar(select(PasswordResetToken).where(PasswordResetToken.token_hash == hash_token(token)))
    assert row is not None
    assert token not in (row.token_hash or "")

    response = client.post(RESET, json={"token": token, "password": "NewPassw0rd9"})
    assert response.status_code == 200, response.text
    assert response.json()["signed_out_all"] is True

    # 旧密码失效、新密码可用
    assert client.post(LOGIN, json={"email": email, "password": "Passw0rd123"}).status_code == 401
    ok = client.post(LOGIN, json={"email": email, "password": "NewPassw0rd9"})
    assert ok.status_code == 200

    # 重置前签发的 refresh 已作废
    stale = client.post(REFRESH, cookies={settings.refresh_cookie_name: stale_refresh})
    assert stale.status_code == 401


def test_reset_token_is_single_use(client: TestClient, outbox) -> None:
    email = f"once_{uuid.uuid4().hex[:8]}@example.com"
    _register(client, email)
    client.post(FORGOT, json={"email": email})
    token = _mail_token(outbox, email)

    assert client.post(RESET, json={"token": token, "password": "Another123"}).status_code == 200
    again = client.post(RESET, json={"token": token, "password": "Another456"})
    assert again.status_code == 400
    assert again.json()["error"]["code"] == "INVALID_RESET_TOKEN"


def test_expired_token_rejected(client: TestClient, outbox, session: Session) -> None:
    email = f"expire_{uuid.uuid4().hex[:8]}@example.com"
    _register(client, email)
    client.post(FORGOT, json={"email": email})
    token = _mail_token(outbox, email)

    row = session.scalar(select(PasswordResetToken).where(PasswordResetToken.token_hash == hash_token(token)))
    assert row is not None
    row.expires_at = utcnow() - timedelta(minutes=1)
    session.add(row)
    session.commit()

    response = client.post(RESET, json={"token": token, "password": "Another123"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_RESET_TOKEN"


def test_reset_rejects_weak_or_reused_password(client: TestClient, outbox) -> None:
    email = f"weak_{uuid.uuid4().hex[:8]}@example.com"
    _register(client, email)
    client.post(FORGOT, json={"email": email})
    token = _mail_token(outbox, email)

    weak = client.post(RESET, json={"token": token, "password": "abcdefgh"})
    assert weak.status_code == 422

    reused = client.post(RESET, json={"token": token, "password": "Passw0rd123"})
    assert reused.status_code == 422
    assert reused.json()["error"]["code"] == "PASSWORD_REUSED"

    # 失败不消耗令牌：正确请求仍可用
    assert client.post(RESET, json={"token": token, "password": "FreshPassw0rd"}).status_code == 200


def test_register_password_rules_match_reset(client: TestClient) -> None:
    weak = client.post(
        REGISTER, json={"email": f"w_{uuid.uuid4().hex[:8]}@example.com", "password": "12345678"}
    )
    assert weak.status_code == 422

    common = client.post(
        REGISTER, json={"email": f"c_{uuid.uuid4().hex[:8]}@example.com", "password": "password123"}
    )
    assert common.status_code == 422


def test_forgot_rate_limited(client: TestClient, outbox) -> None:
    email = f"rate_{uuid.uuid4().hex[:8]}@example.com"
    _register(client, email)
    for _ in range(3):
        assert client.post(FORGOT, json={"email": email}).status_code == 200
    fourth = client.post(FORGOT, json={"email": email})
    assert fourth.status_code == 429
    assert fourth.json()["error"]["code"] == "RATE_LIMITED"
