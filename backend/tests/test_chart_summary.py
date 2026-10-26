"""列表摘要的跨域安全性测试。

`_pillars_text` 是列表页唯一的「每行一行字」，必须对**所有域**安全。
早期实现假定 `chart_facts.pillars` 一定是四柱结构，大六壬的字符串字典
会让 `GET /charts` 直接 500 —— 这类错误只有真的存过一张该域的盘才会暴露，
所以这里按「各域真实形状」逐项锁死。
"""

from __future__ import annotations

import pytest

from app.api.v1.charts import _pillars_text

#: 各域 chart_facts 的真实形状（取自各引擎输出，不是手编的理想结构）
SHAPES: dict[str, tuple[dict, str]] = {
    "bazi": (
        {"chart_facts": {"pillars": {"year": {"text": "庚午"}, "month": {"text": "壬午"}, "day": {"text": "辛亥"}, "hour": {"text": "癸巳"}}}},
        "庚午 壬午 辛亥 癸巳",
    ),
    "ziwei": (
        {
            "chart_facts": {
                "lunar_date": {"text": "1990年四月廿六"},
                "five_element_bureau": {"name": "土五局"},
                "life_palace": {"text": "丁亥"},
            }
        },
        "1990年四月廿六 土五局 丁亥",
    ),
    "liuyao": (
        {"chart_facts": {"lunar_date": {"text": "2026年九月十六"}, "original": {"name": "乾为天"}}},
        "2026年九月十六 乾为天",
    ),
    "qimen": (
        {"chart_facts": {"lunar_date": {"text": "2026年九月十六"}}},
        "2026年九月十六",
    ),
    "almanac": (
        {"chart_facts": {"lunar_date": {"text": "2026年九月十六"}, "day_pillar": {"ganzhi": "壬申"}}},
        "2026年九月十六 壬申",
    ),
    "xiaoliuren": (
        {"chart_facts": {"lunar_date": {"text": "2026年九月十六"}, "result_palace": {"name": "留连"}}},
        "2026年九月十六 留连",
    ),
    "meihua": (
        {"chart_facts": {"original": {"name": "地天泰"}, "changed": {"name": "水天需"}}},
        "地天泰",
    ),
    "tarot": (
        {"chart_facts": {"spread": {"name": "三牌阵", "card_count": 3}}},
        "三牌阵",
    ),
    "taiyi": (
        {"chart_facts": {"primary": {"taiyi_name": "太乙", "element": "水"}}},
        "太乙",
    ),
    # 大六壬：pillars 是字符串字典，早期实现就是在这里崩的
    "daliuren": (
        {"chart_facts": {"pillars": {"year": "丙午", "month": "己亥"}, "month_general": {"name": "太冲"}}},
        "太冲",
    ),
    "astrology": (
        {"chart_facts": {"planets": {"sun": {"sign": "双子"}, "moon": {"sign": "双鱼"}}}},
        "日双子 月双鱼",
    ),
    "ziwei_horoscope": (
        {"chart_facts": {"layers": [{"layer": "大限", "palace": "田宅"}, {"layer": "流年", "palace": "疾厄"}]}},
        "大限田宅 流年疾厄",
    ),
    "ziwei_flying": (
        {"chart_facts": {"answer": {"query_type": "flies_from"}}},
        "flies_from",
    ),
    "hepan": (
        {"chart_facts": {"summary": {"cross_count": 17, "internal_count": 8}}},
        "跨盘17条 盘内8条",
    ),
    "mbti": (
        {"chart_facts": {"code": "ESTJ"}},
        "ESTJ",
    ),
    "dream": (
        {"chart_facts": {"keywords": [{"keyword": "蛇"}, {"keyword": "水"}]}},
        "意象：蛇、水",
    ),
}


@pytest.mark.parametrize("domain", sorted(SHAPES))
def test_summary_is_safe_and_readable(domain: str) -> None:
    chart_json, expected = SHAPES[domain]
    assert _pillars_text(chart_json) == expected


def test_empty_facts_returns_empty_string() -> None:
    assert _pillars_text({"chart_facts": {}}) == ""


def test_missing_facts_key_does_not_raise() -> None:
    assert _pillars_text({}) == ""


def test_broken_pillar_struct_is_skipped() -> None:
    """四柱结构不完整（缺 text 或不是 dict）时跳过，不抛异常。"""
    chart_json = {"chart_facts": {"pillars": {"year": {"stem": "庚"}, "month": "壬午"}}}
    assert _pillars_text(chart_json) == ""


def test_none_values_do_not_break() -> None:
    chart_json = {
        "chart_facts": {
            "pillars": None,
            "lunar_date": None,
            "original": {"name": None},
            "code": None,
            "keywords": [],
        }
    }
    assert _pillars_text(chart_json) == ""


def test_multiple_candidates_are_joined() -> None:
    """多个候选都有值时按顺序拼接，不互相覆盖。"""
    chart_json = {
        "chart_facts": {
            "lunar_date": {"text": "九月十六"},
            "original": {"name": "乾为天"},
            "spread": {"name": "三牌阵"},
        }
    }
    text = _pillars_text(chart_json)
    assert "九月十六" in text and "乾为天" in text and "三牌阵" in text


def test_dream_keywords_are_capped() -> None:
    """意象过多时截断，避免列表行被撑爆。"""
    keywords = [{"keyword": f"词{i}"} for i in range(20)]
    text = _pillars_text({"chart_facts": {"keywords": keywords}})
    assert text.count("词") == 6
