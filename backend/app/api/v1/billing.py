"""计费接口：套餐、下单、Mock 回调。

真实支付网关未接入，`/webhooks/mock` 仅用于内测联通验证：
即便在 Mock 下也走完整的 HMAC 验签 + 金额校验 + 事件去重流程，
将来替换成真实网关时，处理链路不需要重写。
"""

from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.db import get_session
from app.domains.billing import orders as order_service
from app.domains.billing import webhooks
from app.domains.billing.orders import PLAN_VERSION, list_plans
from app.models import User

class OrderIn(BaseModel):
    """下单请求体。只收 plan_code，金额一律由服务端按套餐表算。"""

    plan_code: str = Field(min_length=1, max_length=40)


router = APIRouter(prefix="/billing", tags=["billing"])

REFUND_POLICY = (
    "内测期间为 Mock 支付，不会产生真实扣款。正式上线后：额度未使用的订单可在 7 日内申请全额退款；"
    "已消耗额度的订单按未使用部分退款；退款原路退回，1–7 个工作日到账。"
)


@router.get("/plans")
def get_plans() -> dict:
    return {
        "plan_version": PLAN_VERSION,
        "currency": "CNY",
        "plans": [plan.to_dict() for plan in list_plans()],
        "refund_policy": REFUND_POLICY,
        "billing_note": "当前为内测版本，支付通道为 Mock，仅用于功能验证。",
    }


@router.get("/config")
def get_config() -> dict:
    """支付配置：给前端展示「当前能不能真付款、支持哪些通道」。

    只返回可公开的信息，**不返回任何密钥**；`secret_rotated` 只是个布尔，
    用来提醒运维「MOCK_PAYMENT_SECRET 还是默认值」。
    将来接真实网关时，在这里增加 `providers` 里对应通道的 `available`，
    前端无需改结构。
    """
    secret = settings.mock_payment_secret or ""
    secret_rotated = bool(secret) and ("change-me" not in secret)
    methods = [
        {
            "code": "mock",
            "label": "内测通道（Mock）",
            "available": not settings.is_production,
            "note": "走完整 HMAC 验签与金额校验，但不产生真实扣款；生产环境禁用。",
        },
        {
            "code": "wechat",
            "label": "微信支付",
            "available": False,
            "note": "未接入：需商户号、API v3 证书与回调验签。",
        },
        {
            "code": "alipay",
            "label": "支付宝",
            "available": False,
            "note": "未接入：需应用私钥、支付宝公钥与异步通知验签。",
        },
    ]
    return {
        "mode": "live" if settings.is_production else "mock",
        "currency": "CNY",
        "plan_version": PLAN_VERSION,
        "methods": methods,
        "default_method": "mock" if not settings.is_production else None,
        "callback_signature": "HMAC-SHA256(X-Mock-Signature)" if not settings.is_production else "provider-native",
        "secret_rotated": secret_rotated,
        "refund_window_days": 7,
        "notice": (
            "当前为内测 Mock 通道，付款仅用于验证计费链路，不会真实扣款。"
            if not settings.is_production
            else "线上环境未接入真实支付通道，下单接口应关闭或降级为人工开通。"
        ),
    }


@router.post("/orders", status_code=201)
def create_order(
    payload: OrderIn,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    order = order_service.create_order(session, user_id=user.id, plan_code=payload.plan_code)
    session.commit()
    result: dict = {"order": order_service.summary(order)}
    if not settings.is_production:
        # 内测专用：把回调报文与签名一并返回，方便自测；生产环境绝不返回
        body = {
            "event_id": f"evt_{uuid.uuid4().hex[:16]}",
            "order_no": order.order_no,
            "amount_minor": order.amount_minor,
            "status": "paid",
        }
        body_raw = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
        result["mock_callback"] = {
            "url": f"{settings.api_prefix}/billing/webhooks/mock",
            "header": "X-Mock-Signature",
            "body_raw": body_raw,
            "signature": webhooks.sign(body_raw.encode("utf-8")),
            "warning": "仅开发环境返回，用于验证回调链路。",
        }
    return result


@router.post("/webhooks/mock")
async def mock_webhook(request: Request, session: Session = Depends(get_session)) -> dict:
    raw_body = await request.body()
    signature = request.headers.get("x-mock-signature")
    return webhooks.handle_mock_webhook(session, raw_body=raw_body, signature=signature)
