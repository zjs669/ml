"""过期数据清理：注销满 30 天的账号物理删除；超期命盘软删转物理删。

删除账号依赖外键 CASCADE / SET NULL 约束，不再手工删子表。
建议用系统计划任务每天跑一次：
    0 4 * * *  cd /srv/xuanshu/backend && python -m scripts.admin.cleanup_deleted

用法：
    python -m scripts.admin.cleanup_deleted --dry-run          # 只统计
    python -m scripts.admin.cleanup_deleted --retention-days 30
"""

from __future__ import annotations

import argparse
import sys
from datetime import timedelta

from sqlalchemy import delete, select

from app.core.db import SessionLocal, utcnow
from app.models.billing import AuditLog
from app.models.chart import ChartRecord
from app.models.user import User


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="过期数据清理")
    parser.add_argument("--retention-days", type=int, default=30)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    cutoff = utcnow() - timedelta(days=args.retention_days)
    with SessionLocal() as session:
        users = list(
            session.scalars(
                select(User).where(User.deleted_at.is_not(None), User.deleted_at <= cutoff)
            )
        )
        charts = list(
            session.scalars(
                select(ChartRecord).where(
                    ChartRecord.deleted_at.is_not(None), ChartRecord.deleted_at <= cutoff
                )
            )
        )
        print(f"待物理删除：账号 {len(users)} 个，命盘 {len(charts)} 个（cutoff={cutoff.isoformat()}Z）")
        if args.dry_run:
            for user in users:
                print(f"  - user#{user.id} 删除请求时间 {user.deleted_at.isoformat()}Z")
            return 0

        for user in users:
            session.add(
                AuditLog(
                    actor="cli:cleanup",
                    action="account.purge",
                    target_type="user",
                    target_id=str(user.id),
                    detail_json={"deleted_at": user.deleted_at.isoformat() + "Z"},
                )
            )
        session.flush()

        if charts:
            session.execute(delete(ChartRecord).where(ChartRecord.id.in_([c.id for c in charts])))
        if users:
            session.execute(delete(User).where(User.id.in_([u.id for u in users])))
        session.commit()
        print(f"已删除账号 {len(users)} 个、命盘 {len(charts)} 个")
    return 0


if __name__ == "__main__":
    sys.exit(main())
