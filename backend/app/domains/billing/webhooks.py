"""Mock 支付回调。

安全要点（计划 D13）：
1. 先验签再改任何状态——验签失败不写业务数据；
2. `payment_events.event_id` 唯一索引保证重放只处理一次；
3. 金额与订单金额不一致视为伪造，直接拒绝并留痕；
4. 所有分支都写 `processed_status`，便于人工复核。
"""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError
from app.domains.billing import orders as order_service
from app.models.billing import Order, PaymentEvent

PROVIDER = "mock"


class SignatureInvalid(AppError):
    def __init__(self) -> None:
        super().__init__("SIGNATURE_INVALID", "回调签名校验失败", status_code=401)


def sign(raw_body: bytes, secret: str | None = None) -> str:
    key = (secret or settings.mock_payment_secret).encode("utf-8")
    return "sha256=" + hmac.new(key, raw_body, hashlib.sha256).hexdigest()


def verify(raw_body: bytes, signature: str | None, secret: str | None = None) -> bool:
    if not signature:
        return False
    return hmac.compare_digest(sign(raw_body, secret), signature)


def _record_event(
    session: Session, *, event_id: str, order_no: str, payload: dict[str, Any], signature_valid: bool
) -> tuple[PaymentEvent, bool]:
    """返回 (事件, 是否首次处理)。重复 event_id 直接复用旧行。"""
    event = PaymentEvent(
        provider=PROVIDER,
        event_id=event_id,
        order_no=order_no,
        payload_json=payload,
        signature_valid=signature_valid,
        processed_status="received",
    )
    try:
        with session.begin_nested():
            session.add(event)
            session.flush()
        return event, True
    except IntegrityError:
        existing = session.query(PaymentEvent).filter_by(event_id=event_id).one()
        return existing, False


def handle_mock_webhook(
    session: Session, *, raw_body: bytes, signature: str | None
) -> dict[str, Any]:
    signature_valid = verify(raw_body, signature)
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AppError("INVALID_PAYLOAD", "回调内容不是合法 JSON", status_code=400) from exc
    if not isinstance(payload, dict):
        raise AppError("INVALID_PAYLOAD", "回调内容必须是 JSON 对象", status_code=400)

    event_id = str(payload.get("event_id") or "")
    order_no = str(payload.get("order_no") or "")
    if not event_id or not order_no:
        raise AppError("INVALID_PAYLOAD", "回调缺少 event_id 或 order_no", status_code=400)

    event, first_time = _record_event(
        session, event_id=event_id, order_no=order_no, payload=payload, signature_valid=signature_valid
    )
    if not signature_valid:
        event.processed_status = "signature_invalid"
        session.add(event)
        session.commit()
        raise SignatureInvalid()
    if not first_time:
        session.commit()
        return {
            "status": "duplicate",
            "processed_status": event.processed_status,
            "order_no": order_no,
            "message": "该事件已处理，未重复发放权益",
        }

    order = session.query(Order).filter_by(order_no=order_no).one_or_none()
    if order is None:
        event.processed_status = "order_not_found"
        session.add(event)
        session.commit()
        raise AppError("ORDER_NOT_FOUND", "订单不存在", status_code=404)

    expected = order.amount_minor
    actual = payload.get("amount_minor")
    if not isinstance(actual, int) or actual != expected:
        event.processed_status = "amount_mismatch"
        session.add(event)
        session.commit()
        raise AppError("AMOUNT_MISMATCH", "回调金额与订单金额不一致", status_code=400)

    if str(payload.get("status", "paid")) != "paid":
        event.processed_status = "ignored_status"
        session.add(event)
        session.commit()
        return {"status": "ignored", "order_no": order_no, "message": "非支付成功状态，已忽略"}

    plan = order_service.mark_paid(session, order, provider=PROVIDER)
    event.processed_status = "granted"
    session.add(event)
    session.commit()
    return {
        "status": "ok",
        "order_no": order_no,
        "plan_code": plan.code,
        "credits_granted": plan.credits,
    }
