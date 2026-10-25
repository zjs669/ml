"""端到端冒烟：注册 → 排盘 → 保存 → 报告（含幂等/额度）→ 下单 → Mock 回调。

直接跑在真实数据库上，用随机邮箱隔离数据：
    python -m scripts.smoke_api
"""

from __future__ import annotations

import sys
import uuid

from fastapi.testclient import TestClient

from app.main import app

PANEL = "=" * 60


def main() -> int:
    client = TestClient(app)
    email = f"smoke_{uuid.uuid4().hex[:10]}@example.com"
    register = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Passw0rd123", "display_name": "冒烟"},
    )
    assert register.status_code == 201, register.text
    token = register.json()["access_token"]
    auth = {"Authorization": f"Bearer {token}"}
    print("注册成功:", email)

    birth = {
        "birth_datetime": "1990-06-15T09:10:00",
        "timezone": "Asia/Shanghai",
        "gender": "female",
        "time_known": True,
        "convention": {},
    }
    calc = client.post("/api/v1/charts/bazi/calculate", json=birth)
    assert calc.status_code == 200, calc.text
    pillars = [calc.json()["chart_facts"]["pillars"][k]["text"] for k in ("year", "month", "day", "hour")]
    print(PANEL)
    print("免登录排盘:", " ".join(pillars), "| 触发规则", len(calc.json()["triggered_rules"]))

    saved = client.post("/api/v1/charts", json={**birth, "title": "冒烟盘"}, headers=auth)
    assert saved.status_code == 201, saved.text
    chart_id = saved.json()["id"]

    first = client.post(
        f"/api/v1/charts/{chart_id}/reports",
        json={"depth": "brief"},
        headers={**auth, "Idempotency-Key": "smoke-repeat-key"},
    )
    assert first.status_code == 201, first.text
    second = client.post(
        f"/api/v1/charts/{chart_id}/reports",
        json={"depth": "brief"},
        headers={**auth, "Idempotency-Key": "smoke-repeat-key"},
    )
    assert second.status_code == 201, second.text
    assert first.json()["id"] == second.json()["id"], "同一幂等键不应重复生成"
    print(PANEL)
    print("报告:", first.json()["status"], "| provider", first.json()["model_provider"],
          "| 观测项", len(first.json()["report"]["observations"]))
    print("幂等重放返回同一报告:", second.json()["id"])

    blocked = client.post(
        f"/api/v1/charts/{chart_id}/reports",
        json={"depth": "detailed"},
        headers={**auth, "Idempotency-Key": "smoke-over-quota"},
    )
    print("超额拦截:", blocked.status_code, blocked.json().get("error", {}).get("code"))

    order = client.post("/api/v1/billing/orders", json={"plan_code": "report_once"}, headers=auth)
    assert order.status_code == 201, order.text
    callback = order.json()["mock_callback"]
    for attempt in range(3):
        reply = client.post(
            callback["url"],
            content=callback["body_raw"].encode("utf-8"),
            headers={"X-Mock-Signature": callback["signature"], "Content-Type": "application/json"},
        )
        print(PANEL)
        print(f"回调第 {attempt + 1} 次:", reply.status_code, reply.json().get("status"))

    usage = client.get("/api/v1/me/usage", headers=auth).json()
    print("购后额度:", usage["paid_balance"], "| 免费剩余", usage["daily_free_remaining"])

    paid = client.post(
        f"/api/v1/charts/{chart_id}/reports",
        json={"depth": "detailed"},
        headers={**auth, "Idempotency-Key": "smoke-paid-key"},
    )
    assert paid.status_code == 201, paid.text
    print(PANEL)
    print("详版报告:", paid.json()["status"], "| 校验", paid.json()["validation"]["ok"])
    usage = client.get("/api/v1/me/usage", headers=auth).json()
    print("用后额度:", usage["paid_balance"])

    bad = client.post(
        "/api/v1/billing/webhooks/mock",
        content=b'{"event_id":"forged","order_no":"x","amount_minor":1,"status":"paid"}',
        headers={"X-Mock-Signature": "sha256=deadbeef"},
    )
    print("伪造回调:", bad.status_code, bad.json().get("error", {}).get("code"))
    print(PANEL)
    print("冒烟通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
