"""技能包加载与校验。

技能包是「可版本化、可回归」的提示词资产：`spec_json` 描述适用条件与检索主题，
`prompt_template` 是实际喂给模型的模板文件。文件是唯一事实来源，
发布 CLI 只负责把它写进 `skill_versions` 并留痕（旧版本只置 deprecated，不覆盖）。
"""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

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
