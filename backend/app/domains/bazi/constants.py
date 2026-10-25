"""四柱常量表：藏干、五行权重、口径枚举。

藏干按「本气 / 中气 / 余气」三级存储，权重口径 weight-v1：
本气 1.0、中气 0.5、余气 0.3。权重写进 convention，随命盘一起存档。
"""

from __future__ import annotations

from typing import Literal, TypedDict


class HiddenStem(TypedDict):
    stem: str
    level: str
    weight: float


LEVEL_WEIGHT: dict[str, float] = {"本气": 1.0, "中气": 0.5, "余气": 0.3}

# 地支藏干（本气在前）
HIDDEN_STEMS: dict[str, tuple[tuple[str, str], ...]] = {
    "子": (("癸", "本气"),),
    "丑": (("己", "本气"), ("癸", "中气"), ("辛", "余气")),
    "寅": (("甲", "本气"), ("丙", "中气"), ("戊", "余气")),
    "卯": (("乙", "本气"),),
    "辰": (("戊", "本气"), ("乙", "中气"), ("癸", "余气")),
    "巳": (("丙", "本气"), ("戊", "中气"), ("庚", "余气")),
    "午": (("丁", "本气"), ("己", "中气")),
    "未": (("己", "本气"), ("丁", "中气"), ("乙", "余气")),
    "申": (("庚", "本气"), ("壬", "中气"), ("戊", "余气")),
    "酉": (("辛", "本气"),),
    "戌": (("戊", "本气"), ("辛", "中气"), ("丁", "余气")),
    "亥": (("壬", "本气"), ("甲", "中气")),
}

YearBoundary = Literal["lichun", "lichun_day"]
DayBoundary = Literal["zi_hour_policy_a", "zi_hour_policy_b"]
SolarTimeMethod = Literal["none", "true_solar_time"]
DayBoundaryNote = {
    "zi_hour_policy_a": "23:00 起算次日（子时统属次日）",
    "zi_hour_policy_b": "00:00 换日，23:00-23:59 为夜子时，时柱取次日子时干支",
}
