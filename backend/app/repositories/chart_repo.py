"""命盘、笔记、分享链接的数据访问层。

硬规则：任何按 id 的读取都必须同时带 owner_user_id，
查不到就抛 NotFound（404），不区分"不存在"与"不是你的"，避免探测。
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import NotFound
from app.models.chart import ChartNote, ChartRecord, ShareLink


def snapshot_hash(chart_json: dict[str, Any]) -> str:
    import json

    canonical = json.dumps(chart_json, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def create_chart(
    session: Session,
    *,
    owner_id: int,
    domain: str,
    title: str | None,
    input_json: dict[str, Any],
    chart_json: dict[str, Any],
    convention_json: dict[str, Any],
    algorithm_version: str,
    delete_after: datetime | None,
) -> ChartRecord:
    record = ChartRecord(
        owner_user_id=owner_id,
        domain=domain,
        title=(title or "未命名命盘")[:120],
        input_json=input_json,
        chart_json=chart_json,
        convention_json=convention_json,
        algorithm_version=algorithm_version,
        snapshot_hash=snapshot_hash(chart_json),
        visibility="private",
        delete_after=delete_after,
    )
    session.add(record)
    session.flush()
    return record


def list_charts(
    session: Session, *, owner_id: int, page: int, size: int, domain: str | None
) -> tuple[list[ChartRecord], int]:
    conditions = [ChartRecord.owner_user_id == owner_id, ChartRecord.deleted_at.is_(None)]
    if domain:
        conditions.append(ChartRecord.domain == domain)
    total = session.scalar(select(func.count()).select_from(ChartRecord).where(*conditions)) or 0
    rows = session.scalars(
        select(ChartRecord)
        .where(*conditions)
        .order_by(ChartRecord.created_at.desc(), ChartRecord.id.desc())
        .offset((page - 1) * size)
        .limit(size)
    ).all()
    return list(rows), int(total)


def get_owned(session: Session, *, chart_id: int, owner_id: int) -> ChartRecord:
    record = session.scalar(
        select(ChartRecord).where(
            ChartRecord.id == chart_id,
            ChartRecord.owner_user_id == owner_id,
            ChartRecord.deleted_at.is_(None),
        )
    )
    if record is None:
        raise NotFound("CHART_NOT_FOUND", "命盘不存在或无权访问")
    return record


def update_chart(session: Session, record: ChartRecord, **fields: Any) -> ChartRecord:
    for key, value in fields.items():
        if hasattr(record, key) and value is not None:
            setattr(record, key, value)
    session.add(record)
    return record


def soft_delete_chart(session: Session, record: ChartRecord) -> None:
    from app.core.db import utcnow

    record.deleted_at = utcnow()
    session.add(record)


# ---- 笔记 ----


def add_note(session: Session, *, chart: ChartRecord, user_id: int, content: str) -> ChartNote:
    note = ChartNote(chart_id=chart.id, user_id=user_id, content=content[:4000])
    session.add(note)
    session.flush()
    return note


def list_notes(session: Session, *, chart_id: int) -> list[ChartNote]:
    return list(
        session.scalars(
            select(ChartNote)
            .where(ChartNote.chart_id == chart_id, ChartNote.deleted_at.is_(None))
            .order_by(ChartNote.created_at.desc())
        ).all()
    )


def delete_note(session: Session, *, chart: ChartRecord, note_id: int) -> None:
    from app.core.db import utcnow

    note = session.scalar(select(ChartNote).where(ChartNote.id == note_id, ChartNote.chart_id == chart.id))
    if note is None:
        raise NotFound("NOTE_NOT_FOUND", "笔记不存在")
    note.deleted_at = utcnow()
    session.add(note)


# ---- 分享链接 ----


def create_share(
    session: Session, *, chart_id: int, token_hash: str, expires_at: datetime, redact_level: str
) -> ShareLink:
    link = ShareLink(
        chart_id=chart_id,
        token_hash=token_hash,
        expires_at=expires_at,
        redact_level=redact_level,
    )
    session.add(link)
    session.flush()
    return link


def find_share(session: Session, token_hash: str) -> ShareLink | None:
    return session.scalar(select(ShareLink).where(ShareLink.token_hash == token_hash))


def revoke_share(session: Session, link: ShareLink) -> None:
    from app.core.db import utcnow

    link.revoked_at = utcnow()
    session.add(link)
