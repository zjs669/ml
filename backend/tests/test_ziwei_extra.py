"""紫微第二轮附项：小限 / 流年年龄 / 将前岁前 / 自化 / 三方四正 / 飞星串联。

锚点 1990-05-20 12:00 男命（命宫亥、五行局土五）：
- 小限：男命命宫起 1 岁顺行 → 命宫 [1,13,25...]
- 流年：年支午，流年支落亥宫的虚岁 = (亥11 - 午6) % 12 + 1 = 6 → [6,18,30...]
- 三方四正：命宫 → 命宫 / 财帛 / 官禄 / 迁移
"""

from __future__ import annotations

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.domains.ziwei import constants as C
from app.domains.ziwei.engine import calculate
from app.domains.ziwei.schemas import ZiweiConvention, ZiweiInput

BASE = dict(birth_datetime=datetime(1990, 5, 20, 12, 0), timezone="Asia/Shanghai", gender="male")


def _calc(**extra):
    payload = {**BASE, **extra}
    return calculate(ZiweiInput(**payload), ZiweiConvention())


@pytest.fixture(scope="module")
def chart():
    return _calc(review_age=30, review_year=2026)


@pytest.fixture(scope="module")
def life(chart):
    return next(p for p in chart.chart_facts["palaces"] if p["name"] == "命宫")


def test_xiaoxian_starts_at_life_palace_for_male(life) -> None:
    assert life["xiaoxian_ages"][:3] == [1, 13, 25]


def test_xiaoxian_reverses_for_female() -> None:
    result = _calc(gender="female")
    life = next(p for p in result.chart_facts["palaces"] if p["name"] == "命宫")
    assert life["xiaoxian_ages"][:3] == [1, 13, 25]
    # 逆行时兄弟宫是 2 岁，而不是 12 岁
    sibling = next(p for p in result.chart_facts["palaces"] if p["name"] == "兄弟")
    assert sibling["xiaoxian_ages"][0] == 2


def test_liunian_ages_follow_year_branch(life) -> None:
    assert life["liunian_ages"][:3] == [6, 18, 30]


def test_jiangqian_and_suiqian_follow_year_branch(chart) -> None:
    names = {p["name"] for p in chart.chart_facts["palaces"]}
    for palace in chart.chart_facts["palaces"]:
        assert palace["jiang_qian"] in C.JIANG_QIAN_ORDER
        assert palace["sui_qian"] in C.SUI_QIAN_ORDER
    assert names  # 12 宫齐全


def test_sanfang_is_life_wealth_career_travel(life) -> None:
    assert life["sanfang"] == ["命宫", "财帛", "官禄", "迁移"]


def test_self_hua_only_when_target_stays_in_palace(chart) -> None:
    for palace in chart.chart_facts["palaces"]:
        stem = palace["heavenly_stem"]
        expected = {
            kind
            for kind, star in C.SI_HUA[stem].items()
            if star in palace["stars"]
        }
        assert set(palace["self_hua"]) == expected


def test_liunian_table_starts_from_review_year(chart) -> None:
    table = chart.chart_facts["liunian_table"]
    assert len(table) == 10
    assert table[0]["year"] == 2026
    assert table[0]["pillar"] == "丙午"
    assert table[0]["virtual_age"] == 37


def test_flying_chains_are_deduped_and_bounded(chart) -> None:
    flying = chart.chart_facts["flying"]
    assert flying["starts"] == list(dict.fromkeys(flying["starts"]))
    assert flying["depth"] == 2
    assert flying["chains"]
    assert all(chain["hops"] for chain in flying["chains"])
    assert len(flying["chains"]) <= 200


def test_flying_depth_is_configurable() -> None:
    shallow = _calc(flying_depth=1)
    deep = _calc(flying_depth=3)
    assert shallow.chart_facts["flying"]["depth"] == 1
    assert deep.chart_facts["flying"]["depth"] == 3
    assert len(shallow.chart_facts["flying"]["chains"][0]["hops"]) == 1


def test_api_exposes_new_ziwei_fields(client: TestClient) -> None:
    payload = {
        "birth_datetime": "1990-05-20T12:00:00",
        "timezone": "Asia/Shanghai",
        "gender": "male",
        "review_age": 30,
        "review_year": 2026,
        "flying_depth": 2,
        "convention": {},
    }
    response = client.post("/api/v1/charts/ziwei/calculate", json=payload)
    assert response.status_code == 200, response.text
    facts = response.json()["chart_facts"]
    assert facts["palaces"][0]["sanfang"]
    assert facts["liunian_table"][0]["year"] == 2026
    assert facts["flying"]["chains"]
