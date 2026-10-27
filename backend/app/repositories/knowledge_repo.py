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


# 按 topic 字段匹配（典籍章节名）的查询。
#
# 为什么需要它：ngram 全文检索对短词极不稳定。实测「相刑」两字会命中一堆含
# 「刑」的无关条目，而「天干五合」会连带召回《术语：四柱 / 干支》这类只因含
# 「天干」二字就上分的噪声。knowledge_chunks.topic 存的是典籍章节名，按它匹配
# 等于「先认标题、再看正文」，召回精度高得多。
#
# 用 LIKE 而不是等值：调用方给的是「概念词」（相刑），库里 topic 是「章节名」
# （地支相刑），需要中缀包含匹配才能对上。
_TOPIC_SQL = text(
    """
    SELECT c.id            AS chunk_id,
           c.domain        AS domain,
           c.topic         AS topic,
           c.content       AS content,
           c.citation_label AS citation_label,
           c.location      AS location,
           s.title         AS source_title,
           s.license_status AS license_status,
           1.0             AS score
    FROM knowledge_chunks c
    JOIN knowledge_sources s ON s.id = c.source_id
    WHERE c.approval_status = 'approved'
      AND (:domain IS NULL OR c.domain = :domain)
      AND c.topic LIKE :like
    ORDER BY LENGTH(c.topic) ASC, c.id ASC
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


def search(
    session: Session,
    *,
    query: str,
    domain: str | None = None,
    limit: int = 8,
    prefer_topic: bool = False,
) -> list[dict[str, Any]]:
    """检索片段。`prefer_topic=True` 时先按 topic 字段匹配，未命中再走全文检索。

    `prefer_topic` 默认 False：知识库页面的自由搜索应保持全文语义，
    只有「按主题取片段」的报告链路才需要「先认标题」。
    """
    cleaned = (query or "").strip()
    if not cleaned:
        return []
    scoped = knowledge_domain(domain)
    if prefer_topic:
        rows = session.execute(
            _TOPIC_SQL, {"like": f"%{cleaned}%", "domain": scoped, "limit": limit}
        ).all()
        if rows:
            return [_row_to_dict(row) for row in rows]
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


def search_topics(
    session: Session,
    *,
    topics: list[str],
    domain: str = "bazi",
    limit: int = 6,
    per_topic: int = 2,
) -> list[dict[str, Any]]:
    """按主题批量取片段（报告上下文用），同一 chunk 只出现一次。

    两个曾经踩过的坑，这里都修掉了：

    1. **不要在循环里提前 break**。旧实现是「累计到 limit 就停」，于是
       topics 里排在后面的主题一次都没被检索过 —— 技能包声明 7 个主题、
       top_k=8 时，最后两个主题形同虚设。现在改成全部主题都检索一遍。

    2. **不要让一个主题吃掉全部配额**。旧实现每个主题最多取 limit 条，
       第一个主题就能填满，后续主题即使检索了也进不了最终结果。
       现在每个主题先按 per_topic 均分，余额再按主题顺序补足。

    per_topic 默认 2：一个主题给两条片段，既能覆盖「同义不同书」的表述，
    又不会让某本书的整章挤掉其他主题。
    """
    cleaned = [t.strip() for t in topics if t and t.strip()]
    if not cleaned or limit <= 0:
        return []

    quota = max(1, min(per_topic, limit))
    collected: dict[int, dict[str, Any]] = {}
    overflow: list[dict[str, Any]] = []

    # 第一轮：每个主题最多取 quota 条，保证每个主题都有机会进结果
    for topic in cleaned:
        taken = 0
        for item in search(session, query=topic, domain=domain, limit=quota + 2, prefer_topic=True):
            if item["chunk_id"] in collected:
                continue
            if taken < quota:
                collected[item["chunk_id"]] = item
                taken += 1
            else:
                overflow.append(item)
        if len(collected) >= limit:
            break

    # 第二轮：还没凑满 limit 时，用第一轮剩下的片段按主题顺序补
    if len(collected) < limit:
        for item in overflow:
            if len(collected) >= limit:
                break
            collected.setdefault(item["chunk_id"], item)

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
