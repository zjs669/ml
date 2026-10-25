"""刑冲合害关系引擎。

原则（产品文档 §6.2）：
- 规则以 YAML 声明，程序只回答「哪些规则被触发、由哪些位置触发」；
- 不输出任何吉凶、灾祸或事件结论，一切解释留给带引用的技能库；
- 规则可单独测试：每条规则都有 rule_id、来源、优先级、版本。
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from itertools import combinations
from pathlib import Path
from typing import Any, Iterable

import yaml

RULES_DIR = Path(__file__).resolve().parent / "rules"
POSITION_NAMES = {"year": "年", "month": "月", "day": "日", "hour": "时"}


@dataclass(frozen=True)
class RelationRule:
    rule_id: str
    system: str
    kind: str
    members: tuple[str, ...]
    relation: str
    topic: str
    priority: int
    note: str
    source_ref: str
    version: str
    scope: str  # branch / stem

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "system": self.system,
            "kind": self.kind,
            "relation": self.relation,
            "members": list(self.members),
            "topic": self.topic,
            "priority": self.priority,
            "note": self.note,
            "source_ref": self.source_ref,
            "version": self.version,
            "scope": self.scope,
        }


@lru_cache
def load_rules() -> tuple[str, tuple[RelationRule, ...]]:
    rules: list[RelationRule] = []
    versions: set[str] = set()
    for path in sorted(RULES_DIR.glob("*.yaml")):
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        versions.add(payload.get("version", "unknown"))
        scope = "stem" if path.stem.startswith("stem") else "branch"
        for item in payload.get("rules", []):
            rules.append(
                RelationRule(
                    rule_id=item["rule_id"],
                    system=item["system"],
                    kind=item["kind"],
                    members=tuple(item["members"]),
                    relation=item["relation"],
                    topic=item.get("topic", item["relation"]),
                    priority=int(item.get("priority", 0)),
                    note=item.get("note", ""),
                    source_ref=item.get("source_ref", ""),
                    version=str(payload.get("version", "unknown")),
                    scope=scope,
                )
            )
    ids = [rule.rule_id for rule in rules]
    if len(ids) != len(set(ids)):
        raise RuntimeError("关系规则 rule_id 存在重复，拒绝加载")
    return "+".join(sorted(versions)), tuple(rules)


def _positions_map(pillars: dict[str, dict], field: str) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {}
    for position in ("year", "month", "day", "hour"):
        value = pillars.get(position, {}).get(field)
        if value:
            mapping.setdefault(value, []).append(position)
    return mapping


def _label(positions: Iterable[str], suffix: str = "支") -> str:
    return "-".join(f"{POSITION_NAMES.get(p, p)}{suffix}" for p in positions)


def _emit(rule: RelationRule, positions: list[str], mapping: dict[str, list[str]]) -> dict[str, Any]:
    payload = rule.to_dict()
    payload["positions"] = positions
    payload["label"] = _label(positions, "干" if rule.scope == "stem" else "支")
    extra = {
        member: mapping[member] for member in rule.members if len(mapping.get(member, [])) > 1
    }
    payload["duplicated_branches"] = extra
    return payload


def detect_relations(pillars: dict[str, dict]) -> dict[str, Any]:
    """输入 chart_facts["pillars"]，输出触发结果；纯函数，无 IO。"""
    _, rules = load_rules()
    branch_positions = _positions_map(pillars, "branch")
    stem_positions = _positions_map(pillars, "stem")

    triggered: list[dict[str, Any]] = []
    incomplete: list[dict[str, Any]] = []

    for rule in rules:
        mapping = stem_positions if rule.scope == "stem" else branch_positions
        present = [member for member in rule.members if member in mapping]

        if rule.kind == "pair" and len(present) == 2:
            for left in mapping[rule.members[0]]:
                for right in mapping[rule.members[1]]:
                    if left == right:
                        continue
                    triggered.append(_emit(rule, [left, right], mapping))
        elif rule.kind == "triple":
            if len(present) == 3:
                positions = [mapping[member][0] for member in rule.members]
                triggered.append(_emit(rule, positions, mapping))
            elif len(present) == 2:
                incomplete.append(
                    {
                        "rule_id": rule.rule_id,
                        "relation": rule.relation,
                        "members_present": present,
                        "positions": [mapping[member][0] for member in present],
                        "note": "三合/三会缺一，仅为提示，不构成完整关系",
                        "source_ref": rule.source_ref,
                    }
                )
        elif rule.kind == "self" and len(mapping.get(rule.members[0], [])) >= 2:
            for left, right in combinations(mapping[rule.members[0]], 2):
                triggered.append(_emit(rule, [left, right], mapping))

    triggered.sort(key=lambda item: (-item["priority"], item["rule_id"]))

    conflicts = _detect_conflicts(triggered)
    summary: dict[str, Any] = {}
    for item in triggered:
        summary[item["relation"]] = summary.get(item["relation"], 0) + 1

    return {
        "rules": triggered,
        "incomplete": incomplete,
        "conflicts": conflicts,
        "summary": summary,
        "count": len(triggered),
    }


_COMPETING = {
    "六合", "六冲", "相刑", "三刑", "自刑", "相害", "相破",
    "天干五合", "天干相冲", "天干相克", "半会",
}


def _detect_conflicts(triggered: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """同一对位置同时命中「合」与「冲/刑/害/破」时给出并列提示。"""
    by_pair: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    for item in triggered:
        key = tuple(sorted(item["positions"]))
        by_pair.setdefault(key, []).append(item)

    conflicts: list[dict[str, Any]] = []
    for key, items in by_pair.items():
        relations = {item["relation"] for item in items}
        if len(relations) < 2:
            continue
        he = relations & {"六合", "三合", "三会", "天干五合", "半会"}
        ke = relations & (_COMPETING - {"六合", "三合", "三会", "天干五合", "半会"})
        if he and ke:
            conflicts.append(
                {
                    "type": "合克并见",
                    "positions": list(key),
                    "relations": sorted(relations),
                    "rule_ids": [item["rule_id"] for item in items],
                    "note": "同一位置组合同时命中合类与冲刑害破类规则，属并列事实，解释需说明流派处理差异。",
                }
            )
    return conflicts


def attach_to_chart(chart_facts: dict[str, Any]) -> dict[str, Any]:
    """把关系结果并入 chart_facts，并返回可直接放进 ChartResult 的结构。"""
    analysis = detect_relations(chart_facts.get("pillars", {}))
    chart_facts["relations"] = analysis
    return analysis
