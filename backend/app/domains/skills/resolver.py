"""技能选择。

决策顺序：显式 `skill_key` → 含关系触发且用户要详版 → 依次按 when 条件打分。
口径不匹配时直接拒绝并提示，而不是"猜一个口径"继续生成。
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.errors import AppError
from app.domains.skills.loader import SkillSpec, SkillSpecError, find, load_all


class SkillRejected(AppError):
    def __init__(self, message: str) -> None:
        super().__init__("SKILL_REJECTED", message, status_code=400)


@dataclass
class Resolution:
    spec: SkillSpec
    reason: str


def _score(spec: SkillSpec, *, depth: str, relation_count: int, topic: str | None) -> int:
    score = 0
    if depth in spec.when.depths:
        score += 2
    if spec.when.requires_relations:
        score += 3 if relation_count > 0 else -5
    if relation_count >= spec.when.min_relations:
        score += 1
    if topic and topic in spec.when.topics:
        score += 2
    if topic is None and "overview" in spec.when.topics:
        score += 1
    return score


def _check_convention(spec: SkillSpec, convention: dict) -> None:
    """口径匹配检查。

    只校验**该域自己声明的口径字段**。`day_boundary` / `year_boundary` 是四柱系的
    概念；黄历用 `midnight`、占星根本不用换日、塔罗更没有年界 —— 对这些域强行套
    「换日口径白名单」会让技能永远匹配不上，报错信息还会误导用户去「切换口径」，
    而那个口径在该域根本不存在。

    判定方式：技能包声明了 `accepted_*` 白名单，且**命盘口径里确实带这个字段**时才检查。
    为此这里改为「只要该域的口径里出现该字段，就必须在白名单内」，同时把
    非四柱域的白名单写成「包含该域实际取值」——由技能包自己负责，不在代码里特判域。
    """
    day_boundary = convention.get("day_boundary")
    year_boundary = convention.get("year_boundary")
    if day_boundary and day_boundary not in spec.accepted_day_boundaries:
        raise SkillRejected(
            f"技能 {spec.skill_key} 尚未覆盖换日口径 {day_boundary}，请切换口径或选择其他技能。"
        )
    if year_boundary and year_boundary not in spec.accepted_year_boundaries:
        raise SkillRejected(
            f"技能 {spec.skill_key} 尚未覆盖年柱口径 {year_boundary}，请切换口径或选择其他技能。"
        )


def resolve(
    *,
    domain: str = "bazi",
    depth: str = "brief",
    relation_count: int = 0,
    topic: str | None = None,
    skill_key: str | None = None,
    convention: dict | None = None,
) -> Resolution:
    convention = convention or {}
    if skill_key:
        try:
            spec = find(skill_key)
        except SkillSpecError as exc:
            raise SkillRejected(str(exc)) from exc
        if spec is None:
            raise SkillRejected(f"技能包不存在：{skill_key}")
        if spec.domain != domain:
            raise SkillRejected(f"技能 {skill_key} 属于 {spec.domain} 域，无法用于 {domain}")
        _check_convention(spec, convention)
        return Resolution(spec=spec, reason="user_selected")

    candidates = [spec for spec in load_all() if spec.domain == domain]
    if not candidates:
        raise SkillRejected(f"{domain} 域暂无可用技能包")

    best: SkillSpec | None = None
    best_score = -10**6
    for spec in candidates:
        try:
            _check_convention(spec, convention)
        except SkillRejected:
            continue
        score = _score(spec, depth=depth, relation_count=relation_count, topic=topic)
        if score > best_score:
            best, best_score = spec, score
    if best is None:
        raise SkillRejected("没有与当前口径匹配的技能包，请检查口径设置。")
    return Resolution(spec=best, reason=f"auto_score={best_score}")
