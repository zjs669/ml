"""技能包发布：schema 校验 → eval_cases 回归 → 写 checksum → published → 审计日志。

旧版本只置 `deprecated`，绝不覆盖——这是"口径升级后旧报告不被静默改写"的前提。

用法：
    python -m scripts.admin.publish_skill --skill-key bazi.overview.v1
    python -m scripts.admin.publish_skill --all
    python -m scripts.admin.publish_skill --check-only
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import select

from app.core.db import SessionLocal, utcnow
from app.domains.skills.loader import SkillSpec, load_all
from app.domains.skills.resolver import SkillRejected, resolve
from app.models.billing import AuditLog
from app.models.knowledge import SkillVersion


def run_eval_cases(spec: SkillSpec) -> list[str]:
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


def publish(session, spec: SkillSpec) -> str:
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

    session.add(
        AuditLog(
            actor="cli:admin",
            action="skill.publish",
            target_type="skill_version",
            target_id=f"{spec.skill_key}@{spec.version}",
            detail_json={
                "checksum": checksum,
                "deprecated": [f"{item.skill_key}@{item.version}" for item in previous],
                "eval_cases": [case.case_id for case in spec.eval_cases],
                "at": utcnow().isoformat() + "Z",
            },
        )
    )
    session.commit()
    return "published"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="技能包发布")
    parser.add_argument("--skill-key", action="append", default=[], help="指定技能，可多次使用")
    parser.add_argument("--all", action="store_true", help="发布全部技能包")
    parser.add_argument("--check-only", action="store_true", help="只跑校验与回归，不写库")
    args = parser.parse_args(argv)

    specs = [spec for spec in load_all() if args.all or not args.skill_key or spec.skill_key in args.skill_key]
    if not specs:
        print("没有匹配的技能包", file=sys.stderr)
        return 2

    failed = False
    with SessionLocal() as session:
        for spec in specs:
            failures = run_eval_cases(spec)
            if failures:
                failed = True
                print(f"[FAIL] {spec.skill_key}@{spec.version}")
                for item in failures:
                    print("   -", item)
                continue
            if args.check_only:
                print(f"[OK] {spec.skill_key}@{spec.version} 校验与回归通过（未写库）")
                continue
            result = publish(session, spec)
            print(f"[OK] {spec.skill_key}@{spec.version} -> {result}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
