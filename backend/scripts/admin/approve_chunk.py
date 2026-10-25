"""知识片段审核：把 pending 片段置为 approved / rejected，并写审计日志。

用法：
    python -m scripts.admin.approve_chunk --list
    python -m scripts.admin.approve_chunk --id 12 --id 13
    python -m scripts.admin.approve_chunk --all-pending
    python -m scripts.admin.approve_chunk --id 12 --reject --reason "来源待核"
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import select

from app.core.db import SessionLocal, utcnow
from app.models.billing import AuditLog
from app.models.knowledge import KnowledgeChunk


def _log(session, action: str, chunk_id: int, detail: dict) -> None:
    session.add(
        AuditLog(
            actor="cli:admin",
            action=action,
            target_type="knowledge_chunk",
            target_id=str(chunk_id),
            detail_json=detail,
        )
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="知识片段审核")
    parser.add_argument("--id", type=int, action="append", default=[], help="片段 id，可多次指定")
    parser.add_argument("--all-pending", action="store_true", help="审核全部 pending 片段")
    parser.add_argument("--list", action="store_true", help="列出 pending 片段")
    parser.add_argument("--reject", action="store_true", help="置为 rejected 而不是 approved")
    parser.add_argument("--reason", default="", help="审核说明，会写入审计日志")
    args = parser.parse_args(argv)

    with SessionLocal() as session:
        pending = list(session.scalars(select(KnowledgeChunk).where(KnowledgeChunk.approval_status == "pending")))

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
            found = {c.id for c in pending}
            missing = [i for i in args.id if i not in found]
            if missing:
                print(f"以下片段不是 pending 状态：{missing}", file=sys.stderr)

        status = "rejected" if args.reject else "approved"
        for chunk in targets:
            chunk.approval_status = status
            session.add(chunk)
            _log(
                session,
                "knowledge_chunk.reject" if args.reject else "knowledge_chunk.approve",
                chunk.id,
                {"status": status, "reason": args.reason, "at": utcnow().isoformat() + "Z"},
            )
        session.commit()
        print(f"已将 {len(targets)} 条片段置为 {status}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
