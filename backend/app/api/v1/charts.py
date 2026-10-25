"""命盘接口：计算（免登录）、保存、查询、笔记、分享、导出。"""

from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta

from fastapi import APIRouter, Body, Depends, Query, Response
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_optional_user
from app.core.db import get_session, utcnow
from app.core.errors import AppError, NotFound
from app.domains.bazi.engine import calculate as calculate_bazi
from app.domains.registry import get_engine
from app.models.chart import ChartRecord
from app.models.user import User
from app.repositories import chart_repo
from app.schemas.charts import (
    CalculateIn,
    ChartListItem,
    ChartOut,
    ChartPage,
    ChartPatchIn,
    NoteIn,
    NoteOut,
    SaveChartIn,
    ShareIn,
    ShareOut,
    SharePreview,
)
from app.services.export import build_export_text

router = APIRouter(tags=["charts"])


def _pillars_text(chart_json: dict) -> str:
    facts = chart_json.get("chart_facts", {})
    pillars = facts.get("pillars", {})
    if pillars:
        return " ".join(
            pillars[key]["text"] for key in ("year", "month", "day", "hour") if key in pillars
        )
    # 非四柱术数：用术数自己的摘要字段，列表页不至于空着
    lunar = (facts.get("lunar_date") or {}).get("text")
    bureau = (facts.get("five_element_bureau") or {}).get("name")
    hexagram = (facts.get("original") or {}).get("name")
    return " ".join(part for part in (lunar, bureau, hexagram) if part)


def _to_out(record: ChartRecord) -> ChartOut:
    chart_json = record.chart_json or {}
    return ChartOut(
        id=record.id,
        title=record.title,
        domain=record.domain,
        created_at=record.created_at,
        updated_at=record.updated_at,
        algorithm_version=record.algorithm_version,
        convention=record.convention_json,
        input_summary=chart_json.get("input_summary", {}),
        chart_facts=chart_json.get("chart_facts", {}),
        triggered_rules=chart_json.get("triggered_rules", []),
        warnings=chart_json.get("warnings", []),
        source_refs=chart_json.get("source_refs", []),
    )


@router.post("/charts/bazi/calculate")
def calculate(
    payload: CalculateIn,
    _: User | None = Depends(get_optional_user),
) -> dict:
    """免登录计算：默认不落库，返回结构化盘面与触发规则。"""
    result = calculate_bazi(payload, payload.convention)
    return result.model_dump()


def _calculate_payload(domain: str, payload: dict):
    """按 domain 分派计算，并把 pydantic 校验错误统一成 INVALID_REQUEST。"""
    spec = get_engine(domain)
    try:
        parsed = spec.input_model.model_validate(payload)
    except ValidationError as exc:
        details = [
            {"loc": ".".join(str(part) for part in err.get("loc", [])), "msg": err.get("msg", "")}
            for err in exc.errors()
        ]
        raise AppError("INVALID_REQUEST", "请求参数不合法", status_code=422, details=details) from exc
    return spec.calculate(parsed)


@router.post("/charts/{domain}/calculate")
def calculate_any(
    domain: str,
    payload: dict = Body(...),
    _: User | None = Depends(get_optional_user),
) -> dict:
    """通用排盘入口：按 domain 分派到注册表里的引擎。

    保留 `/charts/bazi/calculate` 不动，避免破坏已验收的前端契约；
    新术数一律走这里，入参模型由引擎自己声明。
    """
    return _calculate_payload(domain, payload).model_dump()


@router.post("/charts", response_model=ChartOut, status_code=201)
def save_chart(
    payload: SaveChartIn,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> ChartOut:
    """服务端重新计算后再入库：客户端提交的盘面数据一律不采信。"""
    result = calculate_bazi(payload, payload.convention)
    delete_after = None
    if payload.delete_after_days:
        delete_after = utcnow() + timedelta(days=payload.delete_after_days)
    record = chart_repo.create_chart(
        session,
        owner_id=user.id,
        domain=result.domain,
        title=payload.title,
        input_json=result.input_summary,
        chart_json=result.model_dump(),
        convention_json=result.convention,
        algorithm_version=result.algorithm_version,
        delete_after=delete_after,
    )
    session.commit()
    return _to_out(record)


def _pop_save_meta(payload: dict) -> tuple[str | None, int | None]:
    """从通用入参里取出保存用字段；它们在引擎入参之外，必须在校验前剔除。"""
    title = payload.pop("title", None)
    if title is not None and (not isinstance(title, str) or len(title) > 120):
        raise AppError("INVALID_REQUEST", "title 必须是不超过 120 字的字符串", status_code=422)
    days = payload.pop("delete_after_days", None)
    if days is not None and (isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= 365):
        raise AppError("INVALID_REQUEST", "delete_after_days 必须是 1-365 的整数", status_code=422)
    return title, days


@router.post("/charts/{domain}", response_model=ChartOut, status_code=201)
def save_chart_any(
    domain: str,
    payload: dict = Body(...),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> ChartOut:
    """通用保存入口（非四柱术数走这里）：同样在服务端重算后再入库。"""
    body = dict(payload)
    title, days = _pop_save_meta(body)
    result = _calculate_payload(domain, body)
    delete_after = utcnow() + timedelta(days=days) if days else None
    record = chart_repo.create_chart(
        session,
        owner_id=user.id,
        domain=result.domain,
        title=title,
        input_json=result.input_summary,
        chart_json=result.model_dump(),
        convention_json=result.convention,
        algorithm_version=result.algorithm_version,
        delete_after=delete_after,
    )
    session.commit()
    return _to_out(record)


@router.get("/charts", response_model=ChartPage)
def list_charts(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    domain: str | None = Query(default=None),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> ChartPage:
    items, total = chart_repo.list_charts(
        session, owner_id=user.id, page=page, size=size, domain=domain
    )
    return ChartPage(
        items=[
            ChartListItem(
                id=item.id,
                title=item.title,
                domain=item.domain,
                created_at=item.created_at,
                algorithm_version=item.algorithm_version,
                day_master=item.chart_json.get("chart_facts", {})
                .get("day_master", {})
                .get("stem"),
                pillars_text=_pillars_text(item.chart_json),
            )
            for item in items
        ],
        total=total,
        page=page,
        size=size,
    )


@router.get("/charts/{chart_id}", response_model=ChartOut)
def get_chart(
    chart_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> ChartOut:
    record = chart_repo.get_owned(session, chart_id=chart_id, owner_id=user.id)
    return _to_out(record)


@router.patch("/charts/{chart_id}", response_model=ChartOut)
def patch_chart(
    chart_id: int,
    payload: ChartPatchIn,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> ChartOut:
    record = chart_repo.get_owned(session, chart_id=chart_id, owner_id=user.id)
    fields: dict = {}
    if payload.title is not None:
        fields["title"] = payload.title
    if payload.visibility is not None:
        fields["visibility"] = payload.visibility
    if payload.delete_after_days is not None:
        fields["delete_after"] = utcnow() + timedelta(days=payload.delete_after_days)
    chart_repo.update_chart(session, record, **fields)
    session.commit()
    return _to_out(record)


@router.delete("/charts/{chart_id}", status_code=204)
def delete_chart(
    chart_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Response:
    record = chart_repo.get_owned(session, chart_id=chart_id, owner_id=user.id)
    chart_repo.soft_delete_chart(session, record)
    session.commit()
    return Response(status_code=204)


# ---- 笔记 ----


@router.get("/charts/{chart_id}/notes", response_model=list[NoteOut])
def get_notes(
    chart_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[NoteOut]:
    chart_repo.get_owned(session, chart_id=chart_id, owner_id=user.id)
    return [NoteOut.model_validate(note) for note in chart_repo.list_notes(session, chart_id=chart_id)]


@router.post("/charts/{chart_id}/notes", response_model=NoteOut, status_code=201)
def add_note(
    chart_id: int,
    payload: NoteIn,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> NoteOut:
    record = chart_repo.get_owned(session, chart_id=chart_id, owner_id=user.id)
    note = chart_repo.add_note(session, chart=record, user_id=user.id, content=payload.content)
    session.commit()
    return NoteOut.model_validate(note)


@router.delete("/charts/{chart_id}/notes/{note_id}", status_code=204)
def delete_note(
    chart_id: int,
    note_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Response:
    record = chart_repo.get_owned(session, chart_id=chart_id, owner_id=user.id)
    chart_repo.delete_note(session, chart=record, note_id=note_id)
    session.commit()
    return Response(status_code=204)


# ---- 导出 ----


@router.get("/charts/{chart_id}/export")
def export_chart(
    chart_id: int,
    format: str = Query(default="md", pattern="^(md|txt)$"),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Response:
    record = chart_repo.get_owned(session, chart_id=chart_id, owner_id=user.id)
    text = build_export_text(record, fmt=format, session=session)
    media = "text/markdown; charset=utf-8" if format == "md" else "text/plain; charset=utf-8"
    filename = f"chart-{record.id}.{format}"
    return Response(
        content=text,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---- 分享 ----


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@router.post("/charts/{chart_id}/share", response_model=ShareOut, status_code=201)
def create_share(
    chart_id: int,
    payload: ShareIn,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> ShareOut:
    record = chart_repo.get_owned(session, chart_id=chart_id, owner_id=user.id)
    token = secrets.token_urlsafe(24)
    expires_at = utcnow() + timedelta(days=payload.expires_in_days)
    chart_repo.create_share(
        session,
        chart_id=record.id,
        token_hash=_hash_token(token),
        expires_at=expires_at,
        redact_level=payload.redact_level,
    )
    chart_repo.update_chart(session, record, visibility="link")
    session.commit()
    return ShareOut(token=token, expires_at=expires_at)


share_router = APIRouter(prefix="/share", tags=["share"])


@share_router.get("/{token}", response_model=SharePreview)
def preview_share(token: str, session: Session = Depends(get_session)) -> SharePreview:
    link = chart_repo.find_share(session, _hash_token(token))
    if link is None:
        raise NotFound("SHARE_NOT_FOUND", "分享链接不存在或已失效")
    if link.revoked_at is not None or link.expires_at < utcnow():
        raise NotFound("SHARE_EXPIRED", "分享链接已过期或被撤销")
    record = session.get(ChartRecord, link.chart_id)
    if record is None or record.deleted_at is not None:
        raise NotFound("SHARE_NOT_FOUND", "分享内容已删除")
    chart_json = record.chart_json or {}
    facts = dict(chart_json.get("chart_facts", {}))
    facts.pop("dayun", None)
    return SharePreview(
        title=record.title,
        domain=record.domain,
        pillars_text=_pillars_text(chart_json),
        chart_facts=facts,
        triggered_rules=chart_json.get("triggered_rules", []),
        warnings=["本页为脱敏预览，不含出生时刻、大运与个人笔记。"],
        algorithm_version=record.algorithm_version,
        convention=record.convention_json,
        expires_at=link.expires_at,
    )


@share_router.delete("/{token}", status_code=204)
def revoke_share(
    token: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Response:
    link = chart_repo.find_share(session, _hash_token(token))
    if link is None:
        raise NotFound("SHARE_NOT_FOUND", "分享链接不存在")
    record = session.get(ChartRecord, link.chart_id)
    if record is None or record.owner_user_id != user.id:
        raise NotFound("SHARE_NOT_FOUND", "分享链接不存在")
    chart_repo.revoke_share(session, link)
    session.commit()
    return Response(status_code=204)
