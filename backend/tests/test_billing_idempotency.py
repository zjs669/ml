"""计费测试：额度三态、支付回调幂等与重放、并发下唯一扣费。"""

from __future__ import annotations

import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session, sessionmaker

from app.core.security import hash_password
from app.domains.billing import ledger
from app.models.billing import Order, PaymentEvent, UsageLedger
from app.models.user import User

PASSWORD = "Passw0rd123"


def _signup(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": f"bill_{uuid.uuid4().hex[:10]}@example.com", "password": PASSWORD},
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _buy(client: TestClient, headers: dict[str, str], plan_code: str = "report_once") -> dict[str, Any]:
    response = client.post("/api/v1/billing/orders", json={"plan_code": plan_code}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def _callback(client: TestClient, order: dict[str, Any]) -> Any:
    callback = order["mock_callback"]
    return client.post(
        callback["url"],
        content=callback["body_raw"].encode("utf-8"),
        headers={callback["header"]: callback["signature"]},
    )


def test_plans_are_listed(client: TestClient) -> None:
    response = client.get("/api/v1/billing/plans")
    assert response.status_code == 200
    body = response.json()
    codes = {plan["code"] for plan in body["plans"]}
    assert codes == {"free", "report_once", "member_month"}
    assert body["refund_policy"]
    assert "Mock" in body["billing_note"]


def test_order_requires_login(client: TestClient) -> None:
    assert client.post("/api/v1/billing/orders", json={"plan_code": "report_once"}).status_code == 401


def test_unknown_plan_is_rejected(client: TestClient) -> None:
    headers = _signup(client)
    response = client.post("/api/v1/billing/orders", json={"plan_code": "free"}, headers=headers)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PLAN_NOT_FOUND"


def test_paid_callback_grants_credits(client: TestClient) -> None:
    headers = _signup(client)
    order = _buy(client, headers)
    assert order["order"]["amount_minor"] == 1900

    paid = _callback(client, order)
    assert paid.status_code == 200, paid.text
    assert paid.json()["status"] == "ok"
    assert paid.json()["credits_granted"] == 1

    usage = client.get("/api/v1/me/usage", headers=headers).json()
    assert usage["paid_balance"] == 1
    orders = client.get("/api/v1/me/orders", headers=headers).json()
    assert orders["items"][0]["status"] == "paid"


def test_callback_replay_grants_once(client: TestClient) -> None:
    headers = _signup(client)
    order = _buy(client, headers)

    statuses = [_callback(client, order).json()["status"] for _ in range(3)]
    assert statuses[0] == "ok"
    assert statuses[1:] == ["duplicate", "duplicate"]

    usage = client.get("/api/v1/me/usage", headers=headers).json()
    assert usage["paid_balance"] == 1  # 重放 3 次只发 1 次权益


def test_forged_signature_is_rejected(client: TestClient) -> None:
    headers = _signup(client)
    order = _buy(client, headers)
    callback = order["mock_callback"]

    response = client.post(
        callback["url"],
        content=callback["body_raw"].encode("utf-8"),
        headers={callback["header"]: "sha256=deadbeef"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "SIGNATURE_INVALID"
    usage = client.get("/api/v1/me/usage", headers=headers).json()
    assert usage["paid_balance"] == 0


def test_unsigned_callback_is_rejected(client: TestClient) -> None:
    headers = _signup(client)
    order = _buy(client, headers)
    response = client.post(order["mock_callback"]["url"], content=order["mock_callback"]["body_raw"])
    assert response.status_code == 401


def test_amount_mismatch_is_rejected(client: TestClient) -> None:
    headers = _signup(client)
    order = _buy(client, headers)
    callback = order["mock_callback"]

    import json

    body = json.loads(callback["body_raw"])
    body["amount_minor"] = 1
    raw = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    from app.domains.billing.webhooks import sign

    response = client.post(
        callback["url"], content=raw, headers={callback["header"]: sign(raw)}
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "AMOUNT_MISMATCH"
    assert client.get("/api/v1/me/usage", headers=headers).json()["paid_balance"] == 0


def test_unknown_order_callback_is_404(client: TestClient) -> None:
    import json

    from app.domains.billing.webhooks import sign

    body = {"event_id": f"evt_{uuid.uuid4().hex[:12]}", "order_no": "XS-NOPE", "amount_minor": 1900, "status": "paid"}
    raw = json.dumps(body, separators=(",", ":")).encode("utf-8")
    response = client.post(
        "/api/v1/billing/webhooks/mock", content=raw, headers={"X-Mock-Signature": sign(raw)}
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ORDER_NOT_FOUND"


def test_member_plan_grants_thirty_credits(client: TestClient) -> None:
    headers = _signup(client)
    order = _buy(client, headers, plan_code="member_month")
    assert order["order"]["amount_minor"] == 4900
    assert _callback(client, order).json()["credits_granted"] == 30
    assert client.get("/api/v1/me/usage", headers=headers).json()["paid_balance"] == 30


def test_ledger_three_states(session: Session) -> None:
    """reserve → settle → refund 的净额必须等于实际消耗。"""
    user = User(
        email=f"ledger_{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password(PASSWORD),
        status="active",
        token_version=0,
    )
    session.add(user)
    session.flush()

    ledger.grant(
        session, user_id=user.id, units=3, reason="测试发放", idempotency_key=f"g:{user.id}"
    )
    assert ledger.paid_balance(session, user.id) == 3

    first = ledger.reserve(
        session,
        user_id=user.id,
        reference_type="report",
        reference_id="1:detailed",
        idempotency_key=f"r1:{user.id}",
    )
    assert (first.source, first.units) == ("paid", 1)
    assert ledger.paid_balance(session, user.id) == 2

    ledger.settle(session, first)  # 实扣 1，差额 0
    assert ledger.paid_balance(session, user.id) == 2

    second = ledger.reserve(
        session,
        user_id=user.id,
        reference_type="report",
        reference_id="2:detailed",
        idempotency_key=f"r2:{user.id}",
    )
    ledger.refund(session, second, reason="upstream_failed")
    assert ledger.paid_balance(session, user.id) == 2  # 失败全额退回

    # 幂等：同一 key 重复 reserve 不会再扣
    again = ledger.reserve(
        session,
        user_id=user.id,
        reference_type="report",
        reference_id="1:detailed",
        idempotency_key=f"r1:{user.id}",
    )
    assert again.ledger_id == first.ledger_id
    assert ledger.paid_balance(session, user.id) == 2


def test_free_quota_counts_per_day(session: Session) -> None:
    user = User(
        email=f"free_{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password(PASSWORD),
        status="active",
        token_version=0,
    )
    session.add(user)
    session.flush()

    first = ledger.reserve(
        session,
        user_id=user.id,
        reference_type="report",
        reference_id="1:brief",
        idempotency_key=f"f1:{user.id}",
    )
    assert first.source == "free" and first.units == 0

    snapshot = ledger.snapshot(session, user.id)
    assert snapshot["daily_free_used"] == 1
    assert snapshot["daily_free_remaining"] == 0
    assert snapshot["paid_balance"] == 0

    from app.core.errors import QuotaExceeded

    with pytest.raises(QuotaExceeded):
        ledger.reserve(
            session,
            user_id=user.id,
            reference_type="report",
            reference_id="2:brief",
            idempotency_key=f"f2:{user.id}",
        )


def test_concurrent_same_key_charges_once(engine) -> None:  # noqa: ANN001
    """10 个并发请求同一个幂等键 → 只写 1 行账本、只扣 1 次额度。"""
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    key = f"conc:{uuid.uuid4().hex[:8]}"

    seed = factory()
    user = User(
        email=f"conc_{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password(PASSWORD),
        status="active",
        token_version=0,
    )
    seed.add(user)
    seed.flush()
    ledger.grant(seed, user_id=user.id, units=5, reason="并发测试", idempotency_key=f"{key}:grant")
    seed.commit()
    user_id = user.id
    seed.close()

    def worker() -> str:
        session = factory()
        try:
            # 并发下两种错误都会出现：
            # - OperationalError：1213 死锁 / 1205 锁等待超时（事务被回滚）；
            # - IntegrityError：两个线程同时 INSERT 同一个幂等键，唯一约束只放行一个。
            # 两者都是“下次再查就能拿到同一行”，重试即可，不影响幂等语义。
            for attempt in range(5):
                try:
                    ledger.reserve(
                        session,
                        user_id=user_id,
                        reference_type="report",
                        reference_id="1:detailed",
                        idempotency_key=key,
                        units=1,
                        allow_free=False,
                    )
                    session.commit()
                    return "ok"
                except (OperationalError, IntegrityError):
                    session.rollback()
                    time.sleep(0.02 * (attempt + 1))
            return "error"
        except Exception as exc:  # noqa: BLE001 - 失败原因要带回断言里
            session.rollback()
            return f"error:{exc.__class__.__name__}"
        finally:
            session.close()

    try:
        with ThreadPoolExecutor(max_workers=10) as pool:
            results = list(pool.map(lambda _: worker(), range(10)))
        assert results.count("ok") == 10, results  # 退避重试后应全部当作成功（幂等键相同）

        check = factory()
        rows = check.scalars(
            select(UsageLedger).where(UsageLedger.idempotency_key == key)
        ).all()
        assert len(rows) == 1, "同一幂等键只允许一行账本"
        assert rows[0].units == -1
        assert ledger.paid_balance(check, user_id) == 4, "只扣 1 次额度"
        check.close()
    finally:
        cleanup = factory()
        cleanup.execute(delete(UsageLedger).where(UsageLedger.user_id == user_id))
        cleanup.execute(delete(User).where(User.id == user_id))
        cleanup.commit()
        cleanup.close()


def test_order_and_payment_event_rows(client: TestClient, session: Session) -> None:
    headers = _signup(client)
    order = _buy(client, headers)
    _callback(client, order)

    order_row = session.scalar(select(Order).where(Order.order_no == order["order"]["order_no"]))
    assert order_row is not None and order_row.status == "paid" and order_row.paid_at is not None

    event = session.scalar(select(PaymentEvent).where(PaymentEvent.order_no == order_row.order_no))
    assert event is not None
    assert event.signature_valid is True
    assert event.processed_status == "granted"


def test_usage_snapshot_shape(client: TestClient) -> None:
    headers = _signup(client)
    usage = client.get("/api/v1/me/usage", headers=headers).json()
    assert usage["daily_free_remaining"] == usage["daily_free_limit"]
    assert usage["can_generate"] is True
    assert usage["daily_free_reset_at"].endswith("Z")
