"""塔罗入参 / 口径结构。

塔罗的输入不是时间，而是「牌阵 + 问题 + 可选复现种子」。
三件事会改变结果，因此全部显式化并回显：
- `deck`：全 78 张 / 仅大阿卡纳 22 张 / 仅小阿卡纳 56 张；
- `allow_reversed` 与 `reversed_probability`：是否出现逆位、逆位概率；
- `seed`：给定即完全可复现（同一 seed 同一次抽牌），不给则由当前时刻派生。

红线：只输出牌名、正逆位、位置与传统关键词，不给吉凶结论、不给事件预测。
"""

from __future__ import annotations

from typing import Literal, TypedDict

from pydantic import BaseModel, Field, field_validator, model_validator

MAX_QUESTION_LENGTH = 200
#: 单次牌阵最多位置数（凯尔特十字 10 张已足够，超出说明用错了牌阵）
MAX_POSITIONS = 12


class TarotConvention(BaseModel):
    """塔罗口径。全部字段回显到 `ChartResult.convention`。"""

    #: 本版本只实现 Rider–Waite 体系的牌名结构与关键词
    school: Literal["rider_waite_v1"] = "rider_waite_v1"
    #: 抽牌方式：seeded = 由 seed 决定的确定性伪随机（可复现）；不给 seed 时由时刻派生
    draw_mode: Literal["seeded"] = "seeded"
    #: 正逆位判定与牌序判定使用两个独立随机源，避免同一序列决定两件事
    rng_split: Literal["separate_streams"] = "separate_streams"

    model_config = {"extra": "forbid"}


class TarotInput(BaseModel):
    spread: str = "three"
    deck: Literal["all", "major", "minor"] = "all"
    allow_reversed: bool = True
    reversed_probability: float = Field(default=0.35, ge=0.0, le=1.0)
    #: 自定义位置名；给定时忽略 spread 的预设位置，但仍需 spread 合法
    custom_positions: list[str] | None = None
    question: str | None = None
    store_question: bool = True
    #: 复现种子。不给则由当前时刻派生并在结果里回显
    seed: str | None = None

    @field_validator("custom_positions")
    @classmethod
    def _positions_valid(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        cleaned = [item.strip() for item in value if item and item.strip()]
        if not cleaned:
            raise ValueError("custom_positions 不能为空列表")
        if len(cleaned) > MAX_POSITIONS:
            raise ValueError(f"牌阵位置最多 {MAX_POSITIONS} 个")
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("牌阵位置名不能重复")
        return cleaned

    @field_validator("question")
    @classmethod
    def _question_length(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        if not text:
            return None
        if len(text) > MAX_QUESTION_LENGTH:
            raise ValueError(f"占问原文不超过 {MAX_QUESTION_LENGTH} 字")
        return text

    @field_validator("seed")
    @classmethod
    def _seed_length(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        if not text:
            return None
        if len(text) > 64:
            raise ValueError("seed 不超过 64 字符")
        return text

    @model_validator(mode="after")
    def _spread_known(self) -> "TarotInput":
        
        if self.spread not in SPREADS:
            raise ValueError(f"未知牌阵「{self.spread}」，可用：{'、'.join(SPREADS)}")
        return self

    model_config = {"extra": "forbid"}


class TarotCalculateIn(TarotInput):
    convention: TarotConvention = Field(default_factory=TarotConvention)


# ------------------------------------------------------------ 牌表与牌阵
#
# 塔罗 78 张牌的定义表。
# 
# 只登记「牌是什么」：编号、花色、元素、中英文名、正逆位关键词。
# 不登记牌义长文、不登记吉凶等级、不登记任何事件预测 —— 那是解读层的事，
# 且必须标注为传统说法。
# 
# 牌名与编号是公有领域的标准结构（Rider–Waite 体系），关键词为自行整理的简表，
# 不含任何版权素材。牌面图片不随本仓库分发。


class CardDef(TypedDict):
    id: str
    name: str
    name_cn: str
    suit: str
    number: int | None
    element: str
    upright: tuple[str, ...]
    reversed: tuple[str, ...]


#: 大阿卡纳 22 张：编号 0–21
MAJOR: tuple[CardDef, ...] = (
    {"id": "major-00", "name": "The Fool", "name_cn": "愚者", "suit": "major", "number": 0, "element": "风",
     "upright": ("开始", "冒险", "天真"), "reversed": ("鲁莽", "缺乏计划", "轻率")},
    {"id": "major-01", "name": "The Magician", "name_cn": "魔术师", "suit": "major", "number": 1, "element": "风",
     "upright": ("创造", "技能", "意志"), "reversed": ("操控", "潜力浪费", "分心")},
    {"id": "major-02", "name": "The High Priestess", "name_cn": "女祭司", "suit": "major", "number": 2, "element": "水",
     "upright": ("直觉", "内省", "潜藏"), "reversed": ("忽视直觉", "封闭", "信息不透明")},
    {"id": "major-03", "name": "The Empress", "name_cn": "女皇", "suit": "major", "number": 3, "element": "土",
     "upright": ("丰饶", "滋养", "生长"), "reversed": ("停滞", "过度依赖", "耗竭")},
    {"id": "major-04", "name": "The Emperor", "name_cn": "皇帝", "suit": "major", "number": 4, "element": "火",
     "upright": ("秩序", "权威", "结构"), "reversed": ("僵化", "专断", "失序")},
    {"id": "major-05", "name": "The Hierophant", "name_cn": "教皇", "suit": "major", "number": 5, "element": "土",
     "upright": ("传统", "规范", "师承"), "reversed": ("质疑传统", "教条", "盲从")},
    {"id": "major-06", "name": "The Lovers", "name_cn": "恋人", "suit": "major", "number": 6, "element": "风",
     "upright": ("结合", "选择", "契合"), "reversed": ("失和", "选择困难", "价值冲突")},
    {"id": "major-07", "name": "The Chariot", "name_cn": "战车", "suit": "major", "number": 7, "element": "水",
     "upright": ("推进", "意志", "掌控"), "reversed": ("失控", "方向不明", "内耗")},
    {"id": "major-08", "name": "Strength", "name_cn": "力量", "suit": "major", "number": 8, "element": "火",
     "upright": ("耐力", "柔韧", "自制"), "reversed": ("乏力", "自我怀疑", "情绪失控")},
    {"id": "major-09", "name": "The Hermit", "name_cn": "隐士", "suit": "major", "number": 9, "element": "土",
     "upright": ("独处", "求索", "省察"), "reversed": ("孤立", "回避", "迷失")},
    {"id": "major-10", "name": "Wheel of Fortune", "name_cn": "命运之轮", "suit": "major", "number": 10, "element": "火",
     "upright": ("转折", "周期", "机遇"), "reversed": ("停滞", "抗拒变化", "时机未至")},
    {"id": "major-11", "name": "Justice", "name_cn": "正义", "suit": "major", "number": 11, "element": "风",
     "upright": ("权衡", "因果", "公正"), "reversed": ("失衡", "推责", "标准不一")},
    {"id": "major-12", "name": "The Hanged Man", "name_cn": "倒吊人", "suit": "major", "number": 12, "element": "水",
     "upright": ("悬置", "换位", "等待"), "reversed": ("僵持", "无谓牺牲", "拖延")},
    {"id": "major-13", "name": "Death", "name_cn": "死神", "suit": "major", "number": 13, "element": "水",
     "upright": ("结束", "更替", "收束"), "reversed": ("抗拒结束", "拖延告别", "旧模式回返")},
    {"id": "major-14", "name": "Temperance", "name_cn": "节制", "suit": "major", "number": 14, "element": "火",
     "upright": ("调和", "渐进", "适度"), "reversed": ("失衡", "急躁", "过度")},
    {"id": "major-15", "name": "The Devil", "name_cn": "恶魔", "suit": "major", "number": 15, "element": "土",
     "upright": ("束缚", "执念", "依赖"), "reversed": ("松绑", "觉察", "解除依赖")},
    {"id": "major-16", "name": "The Tower", "name_cn": "塔", "suit": "major", "number": 16, "element": "火",
     "upright": ("突变", "结构松动", "揭穿"), "reversed": ("勉力维持", "延迟的崩解", "回避")},
    {"id": "major-17", "name": "The Star", "name_cn": "星星", "suit": "major", "number": 17, "element": "风",
     "upright": ("希望", "疗愈", "开阔"), "reversed": ("失望", "信心不足", "视野收窄")},
    {"id": "major-18", "name": "The Moon", "name_cn": "月亮", "suit": "major", "number": 18, "element": "水",
     "upright": ("模糊", "潜意", "幻象"), "reversed": ("澄清", "误解消散", "直面")},
    {"id": "major-19", "name": "The Sun", "name_cn": "太阳", "suit": "major", "number": 19, "element": "火",
     "upright": ("明朗", "活力", "显现"), "reversed": ("延迟显现", "过度乐观", "能量不足")},
    {"id": "major-20", "name": "Judgement", "name_cn": "审判", "suit": "major", "number": 20, "element": "火",
     "upright": ("清算", "召唤", "复盘"), "reversed": ("自我苛责", "回避评估", "悬而未决")},
    {"id": "major-21", "name": "The World", "name_cn": "世界", "suit": "major", "number": 21, "element": "土",
     "upright": ("完成", "整合", "闭环"), "reversed": ("未竟", "缺最后一环", "循环未破")},
)

#: 小阿卡纳四花色：权杖火、圣杯水、宝剑风、星币土
SUIT_META: dict[str, dict[str, str]] = {
    "wands": {"name_cn": "权杖", "element": "火", "en": "Wands"},
    "cups": {"name_cn": "圣杯", "element": "水", "en": "Cups"},
    "swords": {"name_cn": "宝剑", "element": "风", "en": "Swords"},
    "pentacles": {"name_cn": "星币", "element": "土", "en": "Pentacles"},
}

#: 小阿卡纳 1–10 的通用主题词（花色只换元素，不改结构）
_NUMBER_THEMES: dict[int, tuple[tuple[str, ...], tuple[str, ...]]] = {
    1: (("萌发", "单点", "起点"), ("迟滞", "未启动", "错失")),
    2: (("对照", "两方", "取舍"), ("失衡", "对立", "犹豫")),
    3: (("成形", "初成", "协作"), ("受阻", "配合不畅", "拆解")),
    4: (("稳固", "停顿", "守成"), ("僵持", "过度固守", "松脱")),
    5: (("摩擦", "消耗", "冲突"), ("回避冲突", "内耗", "和解倾向")),
    6: (("回流", "给予", "认可"), ("失衡的给予", "亏欠", "不被看见")),
    7: (("评估", "对峙", "权衡"), ("自欺", "疲于应对", "放弃")),
    8: (("推进", "加速", "专注"), ("受阻", "分心", "拖慢")),
    9: (("临近完成", "累积", "戒备"), ("虚耗", "过度防备", "力竭")),
    10: (("饱和", "终点", "承担"), ("超载", "难以收束", "重来")),
}

#: 宫廷牌四位阶
_COURT = (
    (1, "Page", "侍从", ("试探", "学习", "消息"), ("不成熟", "拖延", "三心二意")),
    (2, "Knight", "骑士", ("行动", "推进", "奔赴"), ("莽撞", "反复", "半途")),
    (3, "Queen", "王后", ("涵容", "内化的掌握", "照料"), ("过度付出", "情绪化", "失衡")),
    (4, "King", "国王", ("统筹", "外显的掌握", "定夺"), ("专断", "僵化", "失控的掌控")),
)


def _minor_cards() -> tuple[CardDef, ...]:
    """按「花色 × 点数」展开 56 张小阿卡纳，顺序固定：wands → cups → swords → pentacles。"""
    cards: list[CardDef] = []
    for suit, meta in SUIT_META.items():
        for number in range(1, 11):
            upright, reversed_ = _NUMBER_THEMES[number]
            cards.append(
                {
                    "id": f"{suit}-{number:02d}",
                    "name": f"{_RANK_EN[number]} of {meta['en']}",
                    "name_cn": f"{meta['name_cn']}{_RANK_CN[number]}",
                    "suit": suit,
                    "number": number,
                    "element": meta["element"],
                    "upright": upright,
                    "reversed": reversed_,
                }
            )
        for _order, en, cn, upright, reversed_ in _COURT:
            cards.append(
                {
                    "id": f"{suit}-{en.lower()}",
                    "name": f"{en} of {meta['en']}",
                    "name_cn": f"{meta['name_cn']}{cn}",
                    "suit": suit,
                    "number": None,
                    "element": meta["element"],
                    "upright": upright,
                    "reversed": reversed_,
                }
            )
    return tuple(cards)


_RANK_EN: dict[int, str] = {
    1: "Ace", 2: "Two", 3: "Three", 4: "Four", 5: "Five",
    6: "Six", 7: "Seven", 8: "Eight", 9: "Nine", 10: "Ten",
}
_RANK_CN: dict[int, str] = {
    1: "一", 2: "二", 3: "三", 4: "四", 5: "五",
    6: "六", 7: "七", 8: "八", 9: "九", 10: "十",
}

MINOR: tuple[CardDef, ...] = _minor_cards()

#: 完整 78 张
ALL_CARDS: tuple[CardDef, ...] = MAJOR + MINOR

#: 牌阵定义：id → (中文名, 位置名列表)
SPREADS: dict[str, dict[str, object]] = {
    "single": {"name": "单牌", "positions": ("当下",)},
    "three": {"name": "三牌阵", "positions": ("过去", "现在", "未来")},
    "love": {"name": "爱情牌阵", "positions": ("你的状态", "对方状态", "关系走向")},
    "celtic": {
        "name": "凯尔特十字",
        "positions": (
            "现状", "阻碍", "根基", "过去", "目标",
            "近期", "自我", "环境", "希望与恐惧", "结果",
        ),
    },
    "horseshoe": {
        "name": "马蹄牌阵",
        "positions": ("过去", "现在", "隐藏因素", "阻碍", "外部影响", "建议", "结果"),
    },
    "choice": {"name": "抉择牌阵", "positions": ("现状", "选项甲", "选项乙", "建议")},
    "body_mind_spirit": {"name": "身心灵牌阵", "positions": ("身", "心", "灵")},
    "situation": {"name": "情境牌阵", "positions": ("情境", "行动", "结果")},
    "yes_no": {"name": "是与否", "positions": ("倾向",)},
}

#: 数字命理：大阿卡纳编号用于人格牌 / 灵魂牌 / 年份牌
SCHOOL_NOTE = (
    "本版本只做无放回抽牌与牌阵位置分配，输出牌名、正逆位与传统关键词；"
    "不做事件预测、不给吉凶结论、不替代专业咨询。牌面图片不随仓库分发。"
)
