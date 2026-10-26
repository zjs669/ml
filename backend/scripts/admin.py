"""运营 CLI：知识审核、技能发布、订单补单、过期清理。

为什么合成一个文件：这四个命令原先各自一个模块（53–135 行），结构完全同构 ——
`argparse` + `SessionLocal()` + 调 repository + 写审计日志 + `print`。
分开维护的代价是每次加命令都要新建文件、改文档、记住模块路径；
合成子命令后入口只有一个，`--help` 能一次看全。

用法：
    python -m scripts.admin approve --list
    python -m scripts.admin approve --id 12 --id 13
    python -m scripts.admin approve --all-pending
    python -m scripts.admin approve --id 12 --reject --reason "来源待核"

    python -m scripts.admin publish-skill --skill-key bazi.overview.v1
    python -m scripts.admin publish-skill --all
    python -m scripts.admin publish-skill --check-only

    python -m scripts.admin mark-paid --order-no XS20261024...
    python -m scripts.admin mark-paid --order-no XS... --dry-run

    python -m scripts.admin cleanup --dry-run
    python -m scripts.admin cleanup --retention-days 30

所有写操作都会落 `audit_logs`，actor 形如 `cli:admin` / `cli:cleanup`。
"""

from __future__ import annotations

import argparse
import sys
from datetime import timedelta

from sqlalchemy import delete, select

from app.core.db import SessionLocal, utcnow
from app.domains.billing import orders as order_service
from app.domains.skills.loader import SkillSpec, load_all
from app.domains.skills.loader import SkillRejected, resolve
from app.models import AuditLog, Order
from app.models import ChartRecord
from app.models import KnowledgeChunk, SkillVersion
from app.models import User


def _audit(session, *, actor: str, action: str, target_type: str, target_id: str, detail: dict) -> None:
    session.add(
        AuditLog(
            actor=actor,
            action=action,
            target_type=target_type,
            target_id=target_id,
            detail_json={**detail, "at": utcnow().isoformat() + "Z"},
        )
    )


# ---------------------------------------------------------------- approve


def cmd_approve(args: argparse.Namespace) -> int:
    with SessionLocal() as session:
        pending = list(
            session.scalars(
                select(KnowledgeChunk).where(KnowledgeChunk.approval_status == "pending")
            )
        )

        if args.list or (not args.id and not args.all_pending):
            if not pending:
                print("没有待审核片段")
                return 0
            print(f"待审核片段 {len(pending)} 条：")
            for chunk in pending:
                print(f"  [{chunk.id}] {chunk.citation_label} · {chunk.topic}：{chunk.content[:40]}…")
            return 0

        targets = pending if args.all_pending else [c for c in pending if c.id in set(args.id)]
        if args.id and not args.all_pending:
            missing = [i for i in args.id if i not in {c.id for c in pending}]
            if missing:
                print(f"以下片段不是 pending 状态：{missing}", file=sys.stderr)

        status = "rejected" if args.reject else "approved"
        for chunk in targets:
            chunk.approval_status = status
            session.add(chunk)
            _audit(
                session,
                actor="cli:admin",
                action="knowledge_chunk.reject" if args.reject else "knowledge_chunk.approve",
                target_type="knowledge_chunk",
                target_id=str(chunk.id),
                detail={"status": status, "reason": args.reason},
            )
        session.commit()
        print(f"已将 {len(targets)} 条片段置为 {status}")
    return 0


# ------------------------------------------------------------ publish-skill


def _run_eval_cases(spec: SkillSpec) -> list[str]:
    """每个 eval_case 都跑一次 resolver，确认技能会被正确选中。"""
    failures: list[str] = []
    for case in spec.eval_cases:
        payload = case.input
        expected = (case.expect or {}).get("skill_key")
        try:
            resolution = resolve(
                domain=spec.domain,
                depth=payload.get("depth", "brief"),
                relation_count=int(payload.get("relation_count", 0)),
                topic=payload.get("topic"),
                convention=payload.get("convention") or {},
            )
        except SkillRejected as exc:
            failures.append(f"{case.case_id}: 被拒绝（{exc.message}）")
            continue
        picked = resolution.spec.skill_key
        if str(picked) != str(payload.get("skill_key") or expected):
            failures.append(f"{case.case_id}: 期望 {expected}，实际 {picked}")
    return failures


def _publish_one(session, spec: SkillSpec) -> str:
    existing = session.scalar(
        select(SkillVersion).where(
            SkillVersion.skill_key == spec.skill_key, SkillVersion.version == spec.version
        )
    )
    checksum = spec.checksum()
    if existing is not None and existing.status == "published":
        if existing.checksum == checksum:
            return "already_published"
        raise SystemExit(
            f"技能 {spec.skill_key}@{spec.version} 已发布且内容不同："
            "请提升 version 后重新发布（禁止覆盖已发布版本）"
        )

    previous = list(
        session.scalars(
            select(SkillVersion).where(
                SkillVersion.skill_key == spec.skill_key, SkillVersion.status == "published"
            )
        )
    )
    for old in previous:
        old.status = "deprecated"
        old.deprecated_at = utcnow()
        session.add(old)

    record = existing or SkillVersion(skill_key=spec.skill_key, version=spec.version)
    record.domain = spec.domain
    record.title = spec.title
    record.spec_json = spec.model_dump()
    record.prompt_template = spec.prompt_text()
    record.status = "published"
    record.checksum = checksum
    record.published_at = utcnow()
    session.add(record)

    _audit(
        session,
        actor="cli:admin",
        action="skill.publish",
        target_type="skill_version",
        target_id=f"{spec.skill_key}@{spec.version}",
        detail={
            "checksum": checksum,
            "deprecated": [f"{item.skill_key}@{item.version}" for item in previous],
            "eval_cases": [case.case_id for case in spec.eval_cases],
        },
    )
    session.commit()
    return "published"


def cmd_publish_skill(args: argparse.Namespace) -> int:
    specs = [
        spec
        for spec in load_all()
        if args.all or not args.skill_key or spec.skill_key in args.skill_key
    ]
    if not specs:
        print("没有匹配的技能包", file=sys.stderr)
        return 2

    failed = False
    with SessionLocal() as session:
        for spec in specs:
            failures = _run_eval_cases(spec)
            if failures:
                failed = True
                print(f"[FAIL] {spec.skill_key}@{spec.version}")
                for item in failures:
                    print("   -", item)
                continue
            if args.check_only:
                print(f"[OK] {spec.skill_key}@{spec.version} 校验与回归通过（未写库）")
                continue
            print(f"[OK] {spec.skill_key}@{spec.version} -> {_publish_one(session, spec)}")
    return 1 if failed else 0


# ---------------------------------------------------------------- mark-paid


def cmd_mark_paid(args: argparse.Namespace) -> int:
    with SessionLocal() as session:
        order = session.scalar(select(Order).where(Order.order_no == args.order_no))
        if order is None:
            print(f"订单不存在：{args.order_no}", file=sys.stderr)
            return 2
        print(
            f"订单 {order.order_no} 当前状态 {order.status}，"
            f"金额 {order.amount_minor} 分，套餐 {order.plan_code}"
        )
        if args.dry_run:
            print("dry-run：未做任何修改")
            return 0
        plan = order_service.mark_paid(session, order, provider="manual")
        _audit(
            session,
            actor=args.actor,
            action="order.mark_paid",
            target_type="order",
            target_id=order.order_no,
            detail={"credits": plan.credits},
        )
        session.commit()
        print(f"已置为 paid，发放 {plan.credits} 次额度")
    return 0


# ----------------------------------------------------------------- cleanup


def cmd_cleanup(args: argparse.Namespace) -> int:
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
            _audit(
                session,
                actor="cli:cleanup",
                action="account.purge",
                target_type="user",
                target_id=str(user.id),
                detail={"deleted_at": user.deleted_at.isoformat() + "Z"},
            )
        session.flush()

        if charts:
            session.execute(delete(ChartRecord).where(ChartRecord.id.in_([c.id for c in charts])))
        if users:
            session.execute(delete(User).where(User.id.in_([u.id for u in users])))
        session.commit()
        print(f"已删除账号 {len(users)} 个、命盘 {len(charts)} 个")
    return 0


# ------------------------------------------------------------------- main


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.admin",
        description="运营 CLI：知识审核 / 技能发布 / 订单补单 / 过期清理",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_approve = sub.add_parser("approve", help="知识片段审核")
    p_approve.add_argument("--id", type=int, action="append", default=[], help="片段 id，可多次指定")
    p_approve.add_argument("--all-pending", action="store_true", help="审核全部 pending 片段")
    p_approve.add_argument("--list", action="store_true", help="列出 pending 片段")
    p_approve.add_argument("--reject", action="store_true", help="置为 rejected 而不是 approved")
    p_approve.add_argument("--reason", default="", help="审核说明，会写入审计日志")
    p_approve.set_defaults(func=cmd_approve)

    p_publish = sub.add_parser("publish-skill", help="技能包发布")
    p_publish.add_argument("--skill-key", action="append", default=[], help="指定技能，可多次使用")
    p_publish.add_argument("--all", action="store_true", help="发布全部技能包")
    p_publish.add_argument("--check-only", action="store_true", help="只跑校验与回归，不写库")
    p_publish.set_defaults(func=cmd_publish_skill)

    p_paid = sub.add_parser("mark-paid", help="人工把订单置为已支付")
    p_paid.add_argument("--order-no", required=True)
    p_paid.add_argument("--actor", default="cli:admin")
    p_paid.add_argument("--dry-run", action="store_true")
    p_paid.set_defaults(func=cmd_mark_paid)

    p_cleanup = sub.add_parser("cleanup", help="过期数据物理清理")
    p_cleanup.add_argument("--retention-days", type=int, default=30)
    p_cleanup.add_argument("--dry-run", action="store_true")
    p_cleanup.set_defaults(func=cmd_cleanup)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
