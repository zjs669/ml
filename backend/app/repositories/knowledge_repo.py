"""知识库查询：ngram 全文检索 + 审核态过滤。

检索只返回 `approval_status='approved'` 的片段；没有命中就返回空数组，
上层（reporting）据此写"知识库依据不足"，绝不允许模型自行补全。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.knowledge import KnowledgeChunk, KnowledgeSource

SNIPPET_LIMIT = 260

#: 派生域 → 知识库父域。知识源按「典籍所属领域」归档，
#: 紫微运限/飞星的知识来自紫微典籍，合盘来自四柱典籍 ——
#: 若严格按 domain 精确匹配，这些派生域永远检索不到任何片段，
#: 报告里的 traditional_interpretations 会永远是空数组。
DOMAIN_KNOWLEDGE_PARENT: dict[str, str] = {
    "ziwei_horoscope": "ziwei",
    "ziwei_flying": "ziwei",
    "hepan": "bazi",
}


def knowledge_domain(domain: str | None) -> str | None:
    """把派生域映射到知识库里的父域；未知域原样返回。"""
    if domain is None:
        return None
    return DOMAIN_KNOWLEDGE_PARENT.get(domain, domain)

_SEARCH_SQL = text(
    """
    SELECT c.id            AS chunk_id,
           c.domain        AS domain,
           c.topic         AS topic,
           c.content       AS content,
           c.citation_label AS citation_label,
           c.location      AS location,
           s.title         AS source_title,
           s.license_status AS license_status,
           MATCH(c.content) AGAINST (:q IN NATURAL LANGUAGE MODE) AS score
    FROM knowledge_chunks c
    JOIN knowledge_sources s ON s.id = c.source_id
    WHERE c.approval_status = 'approved'
      AND (:domain IS NULL OR c.domain = :domain)
      AND MATCH(c.content) AGAINST (:q IN NATURAL LANGUAGE MODE) > 0
    ORDER BY score DESC, c.id ASC
    LIMIT :limit
    """
)

_FALLBACK_SQL = text(
    """
    SELECT c.id            AS chunk_id,
           c.domain        AS domain,
           c.topic         AS topic,
           c.content       AS content,
           c.citation_label AS citation_label,
           c.location      AS location,
           s.title         AS source_title,
           s.license_status AS license_status,
           0               AS score
    FROM knowledge_chunks c
    JOIN knowledge_sources s ON s.id = c.source_id
    WHERE c.approval_status = 'approved'
      AND (:domain IS NULL OR c.domain = :domain)
      AND (c.topic LIKE :like OR c.keywords LIKE :like OR c.content LIKE :like)
    ORDER BY c.id ASC
    LIMIT :limit
    """
)


def _snippet(content: str) -> str:
    text_value = " ".join(content.split())
    return text_value if len(text_value) <= SNIPPET_LIMIT else text_value[:SNIPPET_LIMIT] + "…"


def _row_to_dict(row: Any) -> dict[str, Any]:
    return {
        "chunk_id": int(row.chunk_id),
        "domain": row.domain,
        "topic": row.topic,
        "title": row.source_title,
        "citation_label": row.citation_label,
        "location": row.location,
        "license_status": row.license_status,
        "snippet": _snippet(row.content),
        "score": float(row.score or 0),
    }


def search(session: Session, *, query: str, domain: str | None = None, limit: int = 8) -> list[dict[str, Any]]:
    cleaned = (query or "").strip()
    if not cleaned:
        return []
    scoped = knowledge_domain(domain)
    rows = session.execute(
        _SEARCH_SQL, {"q": cleaned, "domain": scoped, "limit": limit}
    ).all()
    if rows:
        return [_row_to_dict(row) for row in rows]
    # ngram 未命中时退化为关键词兜底，保证短查询也能出结果
    like = f"%{cleaned[:40]}%"
    rows = session.execute(
        _FALLBACK_SQL, {"like": like, "domain": scoped, "limit": limit}
    ).all()
    return [_row_to_dict(row) for row in rows]


def search_topics(session: Session, *, topics: list[str], domain: str = "bazi", limit: int = 6) -> list[dict[str, Any]]:
    """按主题批量取片段（报告上下文用），同一 chunk 只出现一次。"""
    collected: dict[int, dict[str, Any]] = {}
    for topic in topics:
        for item in search(session, query=topic, domain=domain, limit=limit):
            collected.setdefault(item["chunk_id"], item)
        if len(collected) >= limit:
            break
    return list(collected.values())[:limit]


def get_chunk(session: Session, chunk_id: int) -> dict[str, Any] | None:
    chunk = session.get(KnowledgeChunk, chunk_id)
    if chunk is None:
        return None
    source = session.get(KnowledgeSource, chunk.source_id)
    return {
        "chunk_id": chunk.id,
        "domain": chunk.domain,
        "topic": chunk.topic,
        "content": chunk.content,
        "citation_label": chunk.citation_label,
        "location": chunk.location,
        "approval_status": chunk.approval_status,
        "content_hash": chunk.content_hash,
        "source": {
            "id": source.id if source else None,
            "title": source.title if source else None,
            "author": source.author if source else None,
            "edition": source.edition if source else None,
            "license_status": source.license_status if source else None,
            "status": source.status if source else None,
        },
    }


def count_approved(session: Session) -> int:
    return int(
        session.execute(
            text("SELECT COUNT(*) FROM knowledge_chunks WHERE approval_status = 'approved'")
        ).scalar_one()
    )
