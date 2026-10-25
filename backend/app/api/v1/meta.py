"""元信息接口：口径选项、算法版本、合规文案版本。

前端 ConventionPanel 与页面脚注都从这里取，避免把口径说明硬编码在 Vue 里。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_session
from app.domains.bazi.constants import DayBoundaryNote
from app.domains.registry import supported_domains
from app.domains.relations.engine import load_rules
from app.domains.skills.loader import load_all
from app.repositories import knowledge_repo, llm_repo
from app.schemas.auth import CURRENT_PRIVACY_VERSION, CURRENT_TERMS_VERSION

router = APIRouter(prefix="/meta", tags=["meta"])

CONVENTION_OPTIONS = {
    "year_boundary": [
        {"value": "lichun", "label": "立春交节时刻（默认）", "note": "以当年立春的精确交节时刻切换年柱。"},
        {"value": "lichun_day", "label": "立春当日 0 点", "note": "以立春所在公历日的 0 点切换，粒度较粗。"},
    ],
    "day_boundary": [
        {
            "value": "zi_hour_policy_a",
            "label": "23:00 起算次日（默认）",
            "note": DayBoundaryNote["zi_hour_policy_a"],
        },
        {
            "value": "zi_hour_policy_b",
            "label": "00:00 换日（夜子时）",
            "note": DayBoundaryNote["zi_hour_policy_b"],
        },
    ],
    "solar_time": [
        {"value": "none", "label": "不校正（默认）", "note": "直接使用输入地点的钟表时间。"},
        {
            "value": "true_solar_time",
            "label": "真太阳时",
            "note": "按经度与均时差校正，需要在表单里填写出生地经度。",
        },
    ],
    "five_element_weight": [
        {"value": "weight-v1", "label": "weight-v1（默认）", "note": "本气 1.0 / 中气 0.5 / 余气 0.3。"}
    ],
    "school": [{"value": "default_v1", "label": "通用（default_v1）", "note": "首版只提供一个体系预设。"}],
}


@router.get("/conventions")
def conventions() -> dict:
    return {
        "options": CONVENTION_OPTIONS,
        "warning": "口径不同会导致四柱结果不同，这是流派差异而不是程序缺陷；结果页会回显本次所用口径。",
    }


@router.get("/about")
def about(session: Session = Depends(get_session)) -> dict:
    rule_version, rules = load_rules()
    skills = load_all()
    return {
        "app_name": settings.app_name,
        "algorithm_version": settings.bazi_algorithm_version,
        "relations_rule_version": rule_version,
        "relations_rule_count": len(rules),
        "prompt_version": settings.prompt_version,
        "llm_mode": settings.llm_mode,
        "llm": _llm_block(session),
        "skills": [{"skill_key": spec.skill_key, "version": spec.version, "title": spec.title} for spec in skills],
        "approved_chunks": knowledge_repo.count_approved(session),
        "legal": {"privacy_version": CURRENT_PRIVACY_VERSION, "terms_version": CURRENT_TERMS_VERSION},
        "ai_notice": (
            "站内 AI 解读由模型生成，已通过服务端事实与引用校验；内容仅供传统文化研习，"
            "不构成医疗、法律、投资等专业建议。"
        ),
        "supported_domains": supported_domains(),
        "planned_domains": [],
    }


def _llm_block(session: Session) -> dict:
    budget = settings.llm_daily_total_budget
    used = llm_repo.count_today(session)
    return {
        "mode": settings.llm_mode,
        "provider": settings.llm_provider,
        "model": settings.llm_model,
        "configured": settings.llm_configured,
        "disclosure": settings.llm_model_disclosure,
        "json_mode": settings.llm_json_mode,
        "budget_used": used,
        "budget_limit": budget,
        "budget_exhausted": budget > 0 and used >= budget,
        "recent": llm_repo.recent_stats(session),
    }


@router.get("/llm-status")
def llm_status(session: Session = Depends(get_session)) -> dict:
    """报告页展示用：是否真的在调大模型、用的哪个、今天还剩多少配额。"""
    return _llm_block(session)
