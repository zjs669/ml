"""邮箱验证码：生成、投递、校验、限次。

不真的连 SMTP：`MAIL_MODE=console` 下邮件写到 `var/mail_outbox.log`，
测试从那里读出验证码，与真实链路走同一套代码路径（只是最后一跳换成落盘）。
"""

from __future__ import annotations

import re
import uuid

from fastapi.testclient import TestClient

PASSWORD = "Passw0rd123"


def _register(client: TestClient) -> tuple[str, str]:
    email = f"code_{uuid.uuid4().hex[:10]}@example.com"
    response = client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
    assert response.status_code == 201, response.text
    return email, response.json()["access_token"]


def _latest_code(email: str) -> str | None:
    """从发信箱里取该邮箱最近一封邮件的验证码。"""
    from app.core import mailer

    for item in reversed(mailer.read_outbox(limit=50)):
        if item.get("to") != email:
            continue
        match = re.search(r"\b(\d{6})\b", item.get("body") or "")
        if match:
            return match.group(1)
    return None


def test_code_is_six_digits() -> None:
    from app.core import mailer

    for _ in range(50):
        code = mailer.generate_verification_code()
        assert len(code) == 6 and code.isdigit()


def test_send_code_does_not_leak_existence(client: TestClient) -> None:
    """已注册与未注册邮箱的响应必须完全一致（除 debug_code）。"""
    email, _ = _register(client)
    known = client.post("/api/v1/auth/code/send", json={"email": email}).json()
    unknown = client.post(
        "/api/v1/auth/code/send", json={"email": f"nobody_{uuid.uuid4().hex[:8]}@example.com"}
    ).json()
    assert known["message"] == unknown["message"]
    assert known["expires_in_minutes"] == unknown["expires_in_minutes"]


def test_reset_password_by_code(client: TestClient) -> None:
    email, _ = _register(client)
    sent = client.post("/api/v1/auth/code/send", json={"email": email})
    assert sent.status_code == 200, sent.text

    code = _latest_code(email)
    assert code, "发信箱里没有该邮箱的验证码"

    new_password = "NewPassw0rd456"
    reset = client.post(
        "/api/v1/auth/password/reset-by-code",
        json={"email": email, "code": code, "password": new_password},
    )
    assert reset.status_code == 200, reset.text

    # 新密码可登录，旧密码不行
    ok = client.post("/api/v1/auth/login", json={"email": email, "password": new_password})
    assert ok.status_code == 200, ok.text
    bad = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert bad.status_code == 401


def test_code_is_single_use(client: TestClient) -> None:
    email, _ = _register(client)
    client.post("/api/v1/auth/code/send", json={"email": email})
    code = _latest_code(email)
    assert code

    first = client.post(
        "/api/v1/auth/password/reset-by-code",
        json={"email": email, "code": code, "password": "NewPassw0rd456"},
    )
    assert first.status_code == 200
    # 同一码再用一次必须失败
    second = client.post(
        "/api/v1/auth/password/reset-by-code",
        json={"email": email, "code": code, "password": "AnotherPassw0rd789"},
    )
    assert second.status_code == 401


def test_wrong_code_rejected(client: TestClient) -> None:
    email, _ = _register(client)
    client.post("/api/v1/auth/code/send", json={"email": email})
    response = client.post(
        "/api/v1/auth/password/reset-by-code",
        json={"email": email, "code": "000000", "password": "NewPassw0rd456"},
    )
    assert response.status_code == 401


def test_too_many_attempts_invalidates(client: TestClient) -> None:
    """连续输错到上限后，即使给出正确码也不再接受。"""
    from app.core.config import settings

    email, _ = _register(client)
    client.post("/api/v1/auth/code/send", json={"email": email})
    code = _latest_code(email)
    assert code

    for _ in range(settings.verification_code_max_attempts + 1):
        client.post(
            "/api/v1/auth/password/reset-by-code",
            json={"email": email, "code": "111111", "password": "NewPassw0rd456"},
        )

    # 错误次数超限后，正确码也失效。
    # 401 = 验证码已作废；429 = 触发接口限流（每邮箱 5 次/10 分钟）。
    # 两者都表示「不再接受」，具体命中哪一道取决于限流阈值与 attempts 阈值的先后。
    response = client.post(
        "/api/v1/auth/password/reset-by-code",
        json={"email": email, "code": code, "password": "NewPassw0rd456"},
    )
    assert response.status_code in (401, 429), response.text


def test_code_rejects_bad_format(client: TestClient) -> None:
    email, _ = _register(client)
    for bad in ("12345", "abcdef", "1234567"):
        response = client.post(
            "/api/v1/auth/password/reset-by-code",
            json={"email": email, "code": bad, "password": "NewPassw0rd456"},
        )
        assert response.status_code == 422, bad
