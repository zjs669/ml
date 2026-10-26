"""技能包加载与校验。

技能包是「可版本化、可回归」的提示词资产：`spec_json` 描述适用条件与检索主题，
`prompt_template` 是实际喂给模型的模板文件。文件是唯一事实来源，
发布 CLI 只负责把它写进 `skill_versions` 并留痕（旧版本只置 deprecated，不覆盖）。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from app.core.errors import AppError

PACKAGES_DIR = Path(__file__).resolve().parent / "packages"
PROMPTS_DIR = Path(__file__).resolve().parents[1] / "reporting" / "prompts"


class SkillSpecError(RuntimeError):
    pass


class EvalCase(BaseModel):
    case_id: str
    input: dict[str, Any] = Field(default_factory=dict)
    expect: dict[str, Any] = Field(default_factory=dict)


class WhenSpec(BaseModel):
    depths: list[Literal["brief", "detailed"]] = Field(default_factory=lambda: ["brief", "detailed"])
    requires_relations: bool = False
    min_relations: int = 0
    topics: list[str] = Field(default_factory=lambda: ["overview"])


class RetrievalSpec(BaseModel):
    topics: list[str] = Field(default_factory=list)
    top_k: int = 6


class SkillSpec(BaseModel):
    skill_key: str
    version: str
    domain: str
    title: str
    description: str = ""
    when: WhenSpec = Field(default_factory=WhenSpec)
    accepted_day_boundaries: list[str] = Field(default_factory=lambda: ["zi_hour_policy_a", "zi_hour_policy_b"])
    accepted_year_boundaries: list[str] = Field(default_factory=lambda: ["lichun", "lichun_day"])
    retrieval: RetrievalSpec = Field(default_factory=RetrievalSpec)
    output_schema: str = "report_v1"
    prompt_template: str
    max_output_tokens: int = 2600
    eval_cases: list[EvalCase] = Field(default_factory=list)

    model_config = {"extra": "forbid"}

    def checksum(self) -> str:
        canonical = json.dumps(self.model_dump(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def prompt_path(self) -> Path:
        path = PROMPTS_DIR / self.prompt_template
        if not path.is_file():
            raise SkillSpecError(f"技能 {self.skill_key} 的提示词模板缺失：{path}")
        return path

    def prompt_text(self) -> str:
        return self.prompt_path().read_text(encoding="utf-8")


def _load_file(path: Path) -> SkillSpec:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:  # pragma: no cover - 手工编辑错误
        raise SkillSpecError(f"{path.name} 不是合法 JSON：{exc}") from exc
    try:
        spec = SkillSpec.model_validate(payload)
    except ValidationError as exc:
        raise SkillSpecError(f"{path.name} 不符合技能包 Schema：{exc}") from exc
    spec.prompt_path()  # 模板必须存在，加载时就失败而不是等到线上
    return spec


@lru_cache
def load_all() -> tuple[SkillSpec, ...]:
    specs = []
    for path in sorted(PACKAGES_DIR.glob("*.json")):
        specs.append(_load_file(path))
    if not specs:
        raise SkillSpecError("未找到任何技能包")
    keys = [(spec.skill_key, spec.version) for spec in specs]
    if len(keys) != len(set(keys)):
        raise SkillSpecError("技能包 (skill_key, version) 存在重复")
    return tuple(specs)


def find(skill_key: str) -> SkillSpec | None:
    for spec in load_all():
        if spec.skill_key == skill_key:
            return spec
    return None


def get(skill_key: str) -> SkillSpec:
    spec = find(skill_key)
    if spec is None:
        raise SkillSpecError(f"技能包不存在：{skill_key}")
    return spec


# ---------------------------------------------------------------- 技能选择
#
# 技能选择。
# 
# 决策顺序：显式 `skill_key` → 含关系触发且用户要详版 → 依次按 when 条件打分。
# 口径不匹配时直接拒绝并提示，而不是"猜一个口径"继续生成。


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
