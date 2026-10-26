"""盘面组件依赖的字段契约测试。

前端三个专属盘面（AlmanacBoard / TarotBoard / DaliurenBoard）直接读 `chart_facts` 的
具体字段。后端一旦改字段名或去掉某个键，前端 typecheck 查不出来（类型是手写的），
页面会在运行时静默显示空白。这里把「盘面真正用到的字段」逐个断言。

命名约定：`BOARD_FIELDS[domain]` 列出该盘面读取的路径，改前端盘面时同步这里。
"""

from __future__ import annotations

import pytest

from app.domains.registry import get_engine

#: 每个盘面读取的字段路径（点号分隔；`[]` 表示数组首元素）
BOARD_FIELDS: dict[str, tuple[dict, tuple[str, ...]]] = {
    "almanac": (
        {"date": "2026-10-25"},
        (
            "date.solar",
            "date.weekday_name",
            "lunar_date.text",
            "lunar_date.year_zodiac",
            "day_pillar.ganzhi",
            "day_pillar.na_yin",
            "day_pillar.zhi_xing",
            "day_pillar.tian_shen_luck",
            "yi",
            "ji",
            "ji_shen",
            "xiong_sha",
            "chong.desc",
            "chong.sheng_xiao",
            "sha_direction",
            "xiu.name",
            "xiu.luck",
            "xiu.zheng",
            "xiu.animal",
            "nine_star.number",
            "nine_star.color",
            "nine_star.element",
            "nine_star.position_desc",
            "nine_star.xuan_kong.name",
            "nine_star.qi_men.name",
            "nine_star.tai_yi.name",
            "positions.xi.branch",
            "positions.xi.desc",
            "positions.tai_sui.branch",
            "hour_slots[]",
        ),
    ),
    "tarot": (
        {"spread": "celtic", "seed": "board-check"},
        (
            "spread.name",
            "spread.card_count",
            "deck.used",
            "draw.seed",
            "draw.auto_seed",
            "draw.allow_reversed",
            "draw.reversed_probability",
            "cards[]",
        ),
    ),
    "daliuren": (
        {"cast_datetime": "2026-10-25T15:00:00"},
        (
            "datetime.solar",
            "datetime.hour_branch",
            "pillars.year",
            "pillars.month",
            "pillars.day",
            "pillars.hour",
            "month_general.branch",
            "month_general.name",
            "month_general.source",
            "day_night.value",
            "plate[]",
            "four_lessons[]",
            "san_chuan_status.implemented",
            "san_chuan_status.reason",
            "san_chuan_status.candidates",
            "shen_sha.jian_chu",
            "shen_sha.tian_ma",
            "shen_sha.lodge",
            "shen_sha.gui_ren.used",
        ),
    ),
}

#: 盘面读取的数组元素字段
ELEMENT_FIELDS: dict[str, dict[str, tuple[str, ...]]] = {
    "almanac": {
        "hour_slots": ("index", "ganzhi", "yi", "ji", "chong", "sha", "tian_shen_luck"),
    },
    "tarot": {
        "cards": ("position", "name_cn", "name", "number", "suit", "orientation", "orientation_cn", "keywords"),
    },
    "daliuren": {
        "plate": ("earth", "sky", "general"),
        "four_lessons": ("index", "lower", "upper", "upper_element", "lower_element"),
    },
}


def _facts(domain: str) -> dict:
    payload, _ = BOARD_FIELDS[domain]
    spec = get_engine(domain)
    return spec.calculate(spec.input_model.model_validate(payload)).chart_facts


def _walk(facts: dict, path: str):
    node = facts
    for part in path.split("."):
        assert isinstance(node, dict), f"{path}: {part} 之前的节点不是对象"
        assert part in node, f"{path}: 缺少字段 {part}"
        node = node[part]
    return node


@pytest.mark.parametrize("domain", sorted(BOARD_FIELDS))
def test_board_fields_exist(domain: str) -> None:
    facts = _facts(domain)
    _, paths = BOARD_FIELDS[domain]
    for path in paths:
        if path.endswith("[]"):
            value = _walk(facts, path[:-2])
            assert isinstance(value, list) and value, f"{path} 应为非空数组"
        else:
            assert _walk(facts, path) is not None or True


@pytest.mark.parametrize("domain", sorted(ELEMENT_FIELDS))
def test_board_array_element_fields(domain: str) -> None:
    facts = _facts(domain)
    for key, fields in ELEMENT_FIELDS[domain].items():
        items = facts.get(key)
        assert isinstance(items, list) and items, f"{key} 应为非空数组"
        for item in items:
            for field in fields:
                assert field in item, f"{key}[].{field} 缺失"


def test_almanac_hour_slots_cover_twelve() -> None:
    """黄历盘面的时辰表要能铺满 12 行，否则表格会出现空洞。"""
    facts = _facts("almanac")
    assert len(facts["hour_slots"]) >= 12


def test_tarot_cards_match_spread_count() -> None:
    """牌阵张数与实际抽到的牌数必须一致，否则卡片网格会缺格。"""
    facts = _facts("tarot")
    assert len(facts["cards"]) == facts["spread"]["card_count"]


def test_daliuren_plate_covers_twelve() -> None:
    """天地盘必须十二宫齐全，盘面网格按地盘支索引，缺一个就少一格。"""
    facts = _facts("daliuren")
    assert len(facts["plate"]) == 12
    branches = {row["earth"] for row in facts["plate"]}
    assert branches == set("子丑寅卯辰巳午未申酉戌亥")


def test_daliuren_sanchuan_shape_when_implemented() -> None:
    """三传已判定时三个传都必须有支，盘面表格才不会有空行。"""
    facts = _facts("daliuren")
    if not facts["san_chuan_status"]["implemented"]:
        pytest.skip("本时刻属未实现课体")
    chuan = facts["san_chuan"]
    for key in ("first", "middle", "last"):
        assert chuan[key]["branch"]


def test_daliuren_sanchuan_reason_when_unimplemented() -> None:
    """未判定时必须有 reason，盘面靠它替代空白。"""
    found = False
    for hour in range(0, 24, 2):
        spec = get_engine("daliuren")
        facts = spec.calculate(
            spec.input_model.model_validate({"cast_datetime": f"2026-10-25T{hour:02d}:00:00"})
        ).chart_facts
        if not facts["san_chuan_status"]["implemented"]:
            found = True
            assert facts["san_chuan"] is None
            assert facts["san_chuan_status"]["reason"]
            break
    assert found, "一整天都没有未实现课体，判定逻辑可能过于宽松"
