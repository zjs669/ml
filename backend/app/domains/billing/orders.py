"""订单：创建、查询、置为已支付并发额度。

真实支付网关未接入（合规未核验），这里只提供 Mock 流程：
建单 → `POST /billing/webhooks/mock` 带 HMAC 签名回调 → 幂等发额度。
"""

from __future__ import annotations

import secrets
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.core.errors import Conflict, NotFound
from app.domains.billing import ledger
from app.domains.billing.plans import Plan, get_plan
from app.models.billing import Order


def _order_no() -> str:
    return f"XS{utcnow().strftime('%Y%m%d%H%M%S')}{secrets.token_hex(3).upper()}"


def create_order(session: Session, *, user_id: int, plan_code: str) -> Order:
    plan = get_plan(plan_code)
    if plan is None or not plan.purchasable:
        raise NotFound("PLAN_NOT_FOUND", "套餐不存在或当前不可购买")
    order = Order(
        user_id=user_id,
        order_no=_order_no(),
        plan_code=plan.code,
        amount_minor=plan.amount_minor,
        currency="CNY",
        status="pending",
        provider="mock",
    )
    session.add(order)
    session.flush()
    return order


def get_owned(session: Session, *, order_no: str, user_id: int) -> Order:
    order = session.scalar(
        select(Order).where(Order.order_no == order_no, Order.user_id == user_id)
    )
    if order is None:
        raise NotFound("ORDER_NOT_FOUND", "订单不存在")
    return order


def list_owned(session: Session, *, user_id: int, limit: int = 50) -> list[Order]:
    return list(
        session.scalars(
            select(Order).where(Order.user_id == user_id).order_by(Order.created_at.desc()).limit(limit)
        ).all()
    )


def mark_paid(session: Session, order: Order, *, provider: str = "mock") -> Plan:
    """置为已支付并发放额度。重复调用只发一次（订单状态 + 账本幂等键双保险）。"""
    plan = get_plan(order.plan_code)
    if plan is None:  # pragma: no cover - 套餐下线后的历史订单
        raise NotFound("PLAN_NOT_FOUND", "套餐已下线")
    if order.status == "paid":
        return plan
    if order.status not in {"pending", "paid"}:
        raise Conflict("ORDER_STATE_INVALID", f"订单状态为 {order.status}，无法标记为已支付")

    order.status = "paid"
    order.paid_at = utcnow()
    order.provider = provider
    session.add(order)
    session.flush()

    ledger.grant(
        session,
        user_id=order.user_id,
        units=plan.credits,
        reason=f"购买 {plan.name}",
        idempotency_key=f"order:{order.order_no}:grant",
        reference_type="order",
        reference_id=order.order_no,
    )
    return plan


def summary(order: Order) -> dict:
    plan = get_plan(order.plan_code)
    return {
        "order_no": order.order_no,
        "plan_code": order.plan_code,
        "plan_name": plan.name if plan else order.plan_code,
        "amount_minor": order.amount_minor,
        "amount_text": f"{order.amount_minor / 100:.2f} 元",
        "currency": order.currency,
        "status": order.status,
        "provider": order.provider,
        "created_at": order.created_at.isoformat() + "Z",
        "paid_at": order.paid_at.isoformat() + "Z" if isinstance(order.paid_at, datetime) else None,
    }
