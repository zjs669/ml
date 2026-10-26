"""订单：创建、查询、置为已支付并发额度。

真实支付网关未接入（合规未核验），这里只提供 Mock 流程：
建单 → `POST /billing/webhooks/mock` 带 HMAC 签名回调 → 幂等发额度。
"""

from __future__ import annotations

from dataclasses import dataclass, field

import secrets
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.core.errors import Conflict, NotFound
from app.domains.billing import ledger
from app.models import Order


# ---------------------------------------------------------------- 套餐
#
# 套餐定义。
# 
# MVP 只有三档：免费日额度、单次详版、月度会员（额度池）。
# 价格一律用「分」存储，避免浮点误差；文案与权益集中在这里，前端只做渲染。


PLAN_VERSION = "plans-2026-01"


@dataclass(frozen=True)
class Plan:
    code: str
    name: str
    amount_minor: int
    credits: int
    duration_days: int
    tagline: str
    features: tuple[str, ...] = field(default_factory=tuple)
    purchasable: bool = True

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "name": self.name,
            "amount_minor": self.amount_minor,
            "amount_text": f"{self.amount_minor / 100:.2f} 元",
            "credits": self.credits,
            "duration_days": self.duration_days,
            "tagline": self.tagline,
            "features": list(self.features),
            "purchasable": self.purchasable,
            "plan_version": PLAN_VERSION,
        }


PLANS: dict[str, Plan] = {
    "free": Plan(
        code="free",
        name="免费体验",
        amount_minor=0,
        credits=0,
        duration_days=0,
        tagline="每天 1 次简版 AI 解读，排盘与关系判定不限次",
        features=(
            "完整四柱、藏干、十神、五行加权",
            "刑冲合害关系判定（含 rule_id 与出处）",
            "每天 1 次简版 AI 解读",
            "命盘保存、笔记、文本导出",
        ),
        purchasable=False,
    ),
    "report_once": Plan(
        code="report_once",
        name="单次详版解读",
        amount_minor=1900,
        credits=1,
        duration_days=0,
        tagline="1 次详版解读，额度长期有效",
        features=(
            "详版报告：盘面事实 + 传统解释 + 现实建议分段",
            "逐条引用知识库出处，缺依据处明确标注",
            "额度不过期，随时使用",
        ),
    ),
    "member_month": Plan(
        code="member_month",
        name="月度会员",
        amount_minor=4900,
        credits=30,
        duration_days=30,
        tagline="30 天内 30 次详版解读",
        features=(
            "30 次详版解读额度",
            "优先使用最新技能版本",
            "知识库全文检索与出处详情",
            "报告历史与多格式导出",
        ),
    ),
}


def get_plan(code: str) -> Plan | None:
    return PLANS.get(code)


def list_plans() -> list[Plan]:
    return [PLANS["free"], PLANS["report_once"], PLANS["member_month"]]


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
