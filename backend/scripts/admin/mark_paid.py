"""人工把订单置为已支付（Mock 支付失败或线下转账时使用），并写审计日志。

用法：
    python -m scripts.admin.mark_paid --order-no XS20261024...
    python -m scripts.admin.mark_paid --order-no XS... --dry-run
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import select

from app.core.db import SessionLocal, utcnow
from app.domains.billing import orders as order_service
from app.models.billing import AuditLog, Order


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="人工置为已支付")
    parser.add_argument("--order-no", required=True)
    parser.add_argument("--actor", default="cli:admin")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    with SessionLocal() as session:
        order = session.scalar(select(Order).where(Order.order_no == args.order_no))
        if order is None:
            print(f"订单不存在：{args.order_no}", file=sys.stderr)
            return 2
        print(f"订单 {order.order_no} 当前状态 {order.status}，金额 {order.amount_minor} 分，套餐 {order.plan_code}")
        if args.dry_run:
            print("dry-run：未做任何修改")
            return 0
        plan = order_service.mark_paid(session, order, provider="manual")
        session.add(
            AuditLog(
                actor=args.actor,
                action="order.mark_paid",
                target_type="order",
                target_id=order.order_no,
                detail_json={"credits": plan.credits, "at": utcnow().isoformat() + "Z"},
            )
        )
        session.commit()
        print(f"已置为 paid，发放 {plan.credits} 次额度")
    return 0


if __name__ == "__main__":
    sys.exit(main())
