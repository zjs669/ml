"""知识库接口：检索与出处详情。只暴露已审核片段。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.errors import NotFound
from app.repositories import knowledge_repo

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


@router.get("/search")
def search_knowledge(
    q: str = Query(min_length=1, max_length=60),
    domain: str | None = Query(default=None, max_length=20),
    limit: int = Query(default=8, ge=1, le=30),
    session: Session = Depends(get_session),
) -> dict:
    items = knowledge_repo.search(session, query=q, domain=domain, limit=limit)
    return {
        "query": q,
        "domain": domain,
        "count": len(items),
        "items": items,
        "note": "仅返回已审核条目；无命中表示知识库暂无依据，不会由模型补全。",
    }


@router.get("/chunks/{chunk_id}")
def get_chunk(chunk_id: int, session: Session = Depends(get_session)) -> dict:
    chunk = knowledge_repo.get_chunk(session, chunk_id)
    if chunk is None or chunk["approval_status"] != "approved":
        raise NotFound("CHUNK_NOT_FOUND", "知识条目不存在或尚未审核通过")
    return chunk


@router.get("/stats")
def stats(session: Session = Depends(get_session)) -> dict:
    return {
        "approved_chunks": knowledge_repo.count_approved(session),
        "retrieval": "MySQL FULLTEXT ngram (natural language mode) + keyword fallback",
    }
