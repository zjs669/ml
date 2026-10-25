"""紫微飞星查询测试。

期望值不取引擎输出：
- 三类查询的答案用本命盘的 `palace_transformations` **独立过滤**重算；
- 四化表用 `ziwei.constants.SI_HUA` 独立核对（不复用引擎的落宫推导）；
- 边界：起点=终点、无连接、指定四化、空四化按全部。
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.domains.ziwei import constants as ZC
from app.domains.ziwei.engine import calculate as calculate_ziwei
from app.domains.ziwei.schemas import ZiweiInput
from app.domains.ziwei_flying.engine import calculate
from app.domains.ziwei_flying.schemas import FlyingCalculateIn, FlyingInput

BIRTH = "1990-05-20T12:00:00"
MUTAGENS = ("禄", "权", "科", "忌")


def _natal():
    return calculate_ziwei(
        ZiweiInput.model_validate({"birth_datetime": BIRTH, "gender": "male"})
    ).chart_facts


def _run(**kwargs):
    inp = FlyingInput.model_validate({"birth_datetime": BIRTH, "gender": "male", **kwargs})
    return calculate(inp).chart_facts


def test_full_table_has_48_rows() -> None:
    """十二宫 × 四化 = 48 条，一条不多一条不少。"""
    facts = _run(query_type="flies_from", from_palace="命宫")
    assert len(facts["palace_transformations"]) == 48


def test_full_table_matches_natal() -> None:
    """飞星查询的全表必须与本命盘的宫干四化完全一致（同一份实现）。"""
    facts = _run(query_type="flies_from", from_palace="命宫")
    natal = _natal()
    assert facts["palace_transformations"] == [
        {
            "from_palace": row["from_palace"],
            "stem": row["stem"],
            "type": row["type"],
            "star": row["star"],
            "to_palace": row["to_palace"],
            "to_branch": row["to_branch"],
        }
        for row in natal["palace_transformations"]
    ]


def test_each_palace_has_four_flights() -> None:
    """每宫恰好四条（禄权科忌各一），否则说明四化表有缺口。"""
    facts = _run(query_type="flies_from", from_palace="命宫")
    per_palace: dict[str, int] = {}
    for row in facts["palace_transformations"]:
        per_palace[row["from_palace"]] = per_palace.get(row["from_palace"], 0) + 1
    assert set(per_palace) == set(ZC.PALACES)
    assert all(count == 4 for count in per_palace.values())


def test_sihua_table_consistency() -> None:
    """每宫的四化类型必须与其宫干在 SI_HUA 表里的类型一致。"""
    facts = _run(query_type="flies_from", from_palace="命宫")
    by_palace: dict[str, dict[str, str]] = {}
    for row in facts["palace_transformations"]:
        by_palace.setdefault(row["from_palace"], {})[row["type"]] = row["star"]
    for palace, mapping in by_palace.items():
        stem = next(
            row["stem"] for row in facts["palace_transformations"] if row["from_palace"] == palace
        )
        assert mapping == ZC.SI_HUA[stem], f"{palace}（{stem}）的四化与 SI_HUA 表不符"


def test_flies_from_filters_correctly() -> None:
    facts = _run(query_type="flies_from", from_palace="夫妻")
    natal = _natal()
    expected = [
        {"type": row["type"], "star": row["star"], "to_palace": row["to_palace"], "to_branch": row["to_branch"]}
        for row in natal["palace_transformations"]
        if row["from_palace"] == "夫妻"
    ]
    assert facts["answer"]["flights"] == expected
    assert len(facts["answer"]["flights"]) == 4


def test_flies_into_filters_correctly() -> None:
    facts = _run(query_type="flies_into", to_palace="官禄")
    natal = _natal()
    expected = [
        {
            "from_palace": row["from_palace"],
            "from_stem": row["stem"],
            "type": row["type"],
            "star": row["star"],
        }
        for row in natal["palace_transformations"]
        if row["to_palace"] == "官禄"
    ]
    assert facts["answer"]["sources"] == expected


def test_flies_to_connection() -> None:
    """任选一对宫位：connected 必须等于「该宫的四化里有落到目标宫的」。"""
    natal = _natal()
    for from_palace in ZC.PALACES[:4]:
        for to_palace in ZC.PALACES[:4]:
            facts = _run(
                query_type="flies_to", from_palace=from_palace, to_palace=to_palace
            )
            expected = [
                {"type": row["type"], "star": row["star"]}
                for row in natal["palace_transformations"]
                if row["from_palace"] == from_palace and row["to_palace"] == to_palace
            ]
            assert facts["answer"]["matches"] == expected
            assert facts["answer"]["connected"] is (len(expected) > 0)


def test_self_flight_is_allowed() -> None:
    """起点 = 终点（自化）是合法查询，不应报错也不应自动排除。"""
    facts = _run(query_type="flies_to", from_palace="命宫", to_palace="命宫")
    assert facts["answer"]["connected"] in (True, False)
    assert isinstance(facts["answer"]["matches"], list)


def test_specific_mutagen_filter() -> None:
    """指定只查「忌」时，结果里不得出现其他三化。"""
    facts = _run(query_type="flies_from", from_palace="命宫", mutagens=["忌"])
    assert all(item["type"] == "忌" for item in facts["answer"]["flights"])
    assert len(facts["answer"]["flights"]) == 1


def test_empty_mutagens_means_all() -> None:
    """空四化列表按全部四化处理（convention.empty_means_all 默认 true）。"""
    facts = _run(query_type="flies_from", from_palace="命宫", mutagens=[])
    assert facts["query"]["empty_means_all"] is True
    assert len(facts["answer"]["flights"]) == 4


def test_disconnected_emits_warning() -> None:
    """flies_to 无连接时必须给出明确提示，而不是静默返回空数组。"""
    natal = _natal()
    # 找一对确定没有连接的宫位
    pair = None
    for from_palace in ZC.PALACES:
        for to_palace in ZC.PALACES:
            if not any(
                row["from_palace"] == from_palace and row["to_palace"] == to_palace
                for row in natal["palace_transformations"]
            ):
                pair = (from_palace, to_palace)
                break
        if pair:
            break
    assert pair is not None
    inp = FlyingInput.model_validate(
        {
            "birth_datetime": BIRTH,
            "gender": "male",
            "query_type": "flies_to",
            "from_palace": pair[0],
            "to_palace": pair[1],
        }
    )
    result = calculate(inp)
    assert any("不存在飞化连接" in item for item in result.warnings)


def test_rejects_unknown_palace() -> None:
    with pytest.raises(ValidationError):
        FlyingInput.model_validate(
            {"birth_datetime": BIRTH, "query_type": "flies_from", "from_palace": "事业"}
        )


def test_rejects_unknown_mutagen() -> None:
    with pytest.raises(ValidationError):
        FlyingInput.model_validate(
            {
                "birth_datetime": BIRTH,
                "query_type": "flies_from",
                "from_palace": "命宫",
                "mutagens": ["化禄"],
            }
        )


def test_rejects_missing_required_palace() -> None:
    with pytest.raises(ValidationError):
        FlyingInput.model_validate({"birth_datetime": BIRTH, "query_type": "flies_from"})
    with pytest.raises(ValidationError):
        FlyingInput.model_validate({"birth_datetime": BIRTH, "query_type": "flies_into"})


def test_rejects_unknown_school() -> None:
    with pytest.raises(ValidationError):
        FlyingCalculateIn.model_validate(
            {
                "birth_datetime": BIRTH,
                "query_type": "flies_from",
                "from_palace": "命宫",
                "convention": {"school": "feixing_v1"},
            }
        )


def test_triggered_rules_empty() -> None:
    inp = FlyingInput.model_validate(
        {"birth_datetime": BIRTH, "query_type": "flies_from", "from_palace": "命宫"}
    )
    assert calculate(inp).triggered_rules == []
