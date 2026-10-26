"""解梦引擎：关键词抽取 + 归类 + 民间通行说法。

固定顺序：
1. 用内置词表在梦境原文里做**最长匹配**（长词优先，避免「水」把「水果」吃掉）；
2. 同一意象只记一次，按出现顺序排列；
3. 超过 `max_keywords` 截断，并记录被截断的数量；
4. 按类别分组，附民间通行说法（可关闭）。

为什么用固定词表而不是分词库：
- 分词库（jieba 等）是额外依赖，且对「梦见」「看到」这类动词的处理不一致；
- 解梦的匹配对象是**意象名词**，词表匹配的召回率足够，且结果可解释
  （用户能看出「为什么命中了这个词」）；
- 词表可增量维护，不需要重训模型。

红线：不解释梦境、不预示事件、不判断吉凶、不做心理诊断。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.config import settings
from app.domains.bazi.schemas import ChartResult
from app.domains.dream.schemas import DreamConvention, DreamInput

# ------------------------------------------------------------ 意象词表
#
# 解梦关键词表。
# 
# **来源声明**：本表为**自编**的常用梦境意象清单，象征说法取民间通行说法
# （公有领域），不复制任何解梦书籍的成段文本，也不引用具体页码。
# 
# 三类条目：
# - `keyword`：意象名（用于在原文中匹配）；
# - `category`：所属类别（自然、动物、人物、场景、行为、物品、身体、情绪）；
# - `traditional`：民间通行的象征说法（一句话，标注为文化背景）。
# 
# 为什么不查表外意象：查不到就说明本表覆盖不足，结果里会显式写进
# `unmatched`，而不是硬套一个近义词 —— 硬套会让用户以为「梦见 X 就是这个意思」。


#: 类别名（用于前端分组）
CATEGORIES: tuple[str, ...] = (
    "自然", "动物", "人物", "场景", "行为", "物品", "身体", "情绪",
)


@dataclass(frozen=True)
class DreamEntry:
    keyword: str
    category: str
    #: 别名（同义写法，用于匹配；不含 keyword 本身）
    aliases: tuple[str, ...] = ()
    #: 民间通行象征说法（文化背景，不是解释结论）
    traditional: str = ""


ENTRIES: tuple[DreamEntry, ...] = (
    # ---- 自然 ----
    DreamEntry("水", "自然", ("河", "湖", "海", "雨"), "民间多以水喻情绪与财物的流动，清浊与缓急各地说法不一。"),
    DreamEntry("火", "自然", ("火焰", "着火", "燃烧"), "民间多以火喻急变与消耗，也有以火为兴旺之说。"),
    DreamEntry("山", "自然", ("登山", "高山"), "民间多以山喻阻隔与目标，登临与否说法不同。"),
    DreamEntry("风", "自然", ("刮风", "大风"), "民间多以风喻变动与消息。"),
    DreamEntry("雪", "自然", ("下雪", "积雪"), "民间多以雪喻覆盖与静默，也有清白之说。"),
    DreamEntry("雷", "自然", ("打雷", "雷声"), "民间多以雷喻惊动与警示。"),
    DreamEntry("月亮", "自然", ("月", "明月"), "民间多以月喻思念与阴晴不定。"),
    DreamEntry("太阳", "自然", ("日出", "烈日"), "民间多以日喻显明与旺盛。"),

    # ---- 动物 ----
    DreamEntry("蛇", "动物", ("小蛇", "蟒蛇"), "民间对蛇的说法分歧最大，既有一说主变，也有说主财。"),
    DreamEntry("鱼", "动物", ("鲤鱼", "鱼群"), "民间多以鱼喻余裕与机会。"),
    DreamEntry("鸟", "动物", ("飞鸟", "小鸟"), "民间多以鸟喻消息与自由。"),
    DreamEntry("狗", "动物", ("小狗", "犬"), "民间多以犬喻守护与忠诚。"),
    DreamEntry("猫", "动物", ("小猫",), "民间说法不一，有说主灵异，也有说主居家安宁。"),
    DreamEntry("马", "动物", ("奔马",), "民间多以马喻行程与动力。"),
    DreamEntry("龙", "动物", ("龙形",), "民间多以龙喻显达与非常之事。"),
    DreamEntry("虎", "动物", ("老虎",), "民间多以虎喻威势与险阻。"),

    # ---- 人物 ----
    DreamEntry("父母", "人物", ("父亲", "母亲", "爸妈"), "民间多以父母喻根基与牵挂。"),
    DreamEntry("孩子", "人物", ("婴儿", "小孩"), "民间多以孩子喻新事与未成之局。"),
    DreamEntry("陌生人", "人物", ("生人",), "民间多以生人喻未知的干扰或助力。"),
    DreamEntry("故人", "人物", ("已故", "去世的人"), "民间多以故人入梦喻未了之事与思念。"),
    DreamEntry("老人", "人物", ("老者",), "民间多以老人喻经验与提醒。"),

    # ---- 场景 ----
    DreamEntry("房子", "场景", ("房屋", "屋子", "家"), "民间多以房舍喻自身状态与家宅。"),
    DreamEntry("学校", "场景", ("教室", "考场"), "民间多以学校喻评量与未完成的功课。"),
    DreamEntry("医院", "场景", ("病房",), "民间多以医院喻修复与停摆。"),
    DreamEntry("桥", "场景", ("过桥",), "民间多以桥喻过渡与转折。"),
    DreamEntry("路", "场景", ("道路", "小路"), "民间多以路喻进程与选择。"),
    DreamEntry("门", "场景", ("大门", "关门"), "民间多以门喻关口与机会。"),
    DreamEntry("楼梯", "场景", ("台阶",), "民间多以楼梯喻进退与层级。"),

    # ---- 行为 ----
    DreamEntry("飞", "行为", ("飞行", "飞翔"), "民间多以飞喻摆脱与轻快。"),
    DreamEntry("坠落", "行为", ("掉下去", "下坠"), "民间多以坠落喻失持与不安。"),
    DreamEntry("追赶", "行为", ("被追", "追我"), "民间多以追赶喻压力与未解之事。"),
    DreamEntry("考试", "行为", ("答题", "交卷"), "民间多以考试喻被评判的焦虑。"),
    DreamEntry("哭泣", "行为", ("哭", "流泪"), "民间多以哭喻情绪释放，也有说主转机。"),
    DreamEntry("结婚", "行为", ("婚礼",), "民间多以婚嫁喻关系变动与承诺。"),
    DreamEntry("死亡", "行为", ("死去", "丧事"), "民间多以死亡喻阶段结束，不作寿命之说。"),
    DreamEntry("迷路", "行为", ("找不到路",), "民间多以迷路喻方向未定。"),
    DreamEntry("游泳", "行为", ("游水",), "民间多以游泳喻在情绪中前行。"),

    # ---- 物品 ----
    DreamEntry("钱", "物品", ("钞票", "现金"), "民间多以钱喻资源与价值感。"),
    DreamEntry("钥匙", "物品", ("开锁",), "民间多以钥匙喻解法与入口。"),
    DreamEntry("镜子", "物品", ("照镜子",), "民间多以镜喻自省与虚实。"),
    DreamEntry("书", "物品", ("书本",), "民间多以书喻知识与未读之事。"),
    DreamEntry("刀", "物品", ("刀子",), "民间多以刀喻决断与割舍。"),
    DreamEntry("绳子", "物品", ("绳索",), "民间多以绳喻牵连与束缚。"),
    DreamEntry("牙齿", "物品", ("掉牙",), "民间对掉牙说法分歧最大，既有主亲人，也有主口舌，均无实证。"),

    # ---- 身体 ----
    DreamEntry("眼睛", "身体", ("双眼",), "民间多以眼喻见地与觉察。"),
    DreamEntry("手", "身体", ("双手",), "民间多以手喻掌控与施为。"),
    DreamEntry("脚", "身体", ("双脚",), "民间多以脚喻立足与行进。"),
    DreamEntry("头发", "身体", ("剪发",), "民间多以头发喻烦扰与仪容。"),

    # ---- 情绪 ----
    DreamEntry("恐惧", "情绪", ("害怕", "恐怖"), "民间多以恐惧喻未备之事。"),
    DreamEntry("愤怒", "情绪", ("生气", "发火"), "民间多以愤怒喻积压的冲突。"),
    DreamEntry("喜悦", "情绪", ("开心", "高兴"), "民间多以喜悦喻顺畅与和合。"),
    DreamEntry("焦虑", "情绪", ("着急", "紧张"), "民间多以焦虑喻未定之局。"),
)

SCHOOL_NOTE = (
    "解梦只做两件事：从梦境描述里抽取意象关键词，列出该意象的民间通行说法。"
    "这些说法属文化背景，不是对梦的解释，也不预示任何事件；"
    "本模块不做心理分析、不做健康判断、不给行动建议。"
)



#: 匹配用的词 → 条目，长词优先
_LOOKUP: dict[str, DreamEntry] = {}
for _entry in ENTRIES:
    _LOOKUP[_entry.keyword] = _entry
    for _alias in _entry.aliases:
        _LOOKUP.setdefault(_alias, _entry)

_SORTED_TERMS: tuple[str, ...] = tuple(sorted(_LOOKUP, key=len, reverse=True))


def _extract(text: str, limit: int) -> tuple[list[dict[str, Any]], int]:
    """返回 (命中的意象列表, 被截断的数量)。同一意象只记一次。"""
    hits: list[dict[str, Any]] = []
    seen: set[str] = set()
    consumed = [False] * len(text)

    for term in _SORTED_TERMS:
        start = 0
        while True:
            index = text.find(term, start)
            if index < 0:
                break
            end = index + len(term)
            if any(consumed[index:end]):
                start = index + 1
                continue
            entry = _LOOKUP[term]
            if entry.keyword not in seen:
                seen.add(entry.keyword)
                hits.append(
                    {
                        "keyword": entry.keyword,
                        "matched": term,
                        "category": entry.category,
                        "position": index,
                        "traditional": entry.traditional,
                    }
                )
            for cursor in range(index, end):
                consumed[cursor] = True
            start = end

    hits.sort(key=lambda item: item["position"])
    truncated = max(len(hits) - limit, 0)
    return hits[:limit], truncated


def calculate(inp: DreamInput, conv: DreamConvention | None = None) -> ChartResult:
    convention = conv or DreamConvention()
    warnings: list[str] = [SCHOOL_NOTE]

    hits, truncated = _extract(inp.text, inp.max_keywords)

    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in hits:
        block = {"keyword": item["keyword"], "matched": item["matched"]}
        if inp.include_traditional:
            block["traditional"] = item["traditional"]
        grouped.setdefault(item["category"], []).append(block)

    categories = [
        {"category": name, "items": grouped[name]}
        for name in CATEGORIES
        if name in grouped
    ]
    unmatched = not hits
    if unmatched:
        warnings.append(
            "原文里没有命中内置词表中的任何意象；这不是「没有含义」，"
            "而是本词表覆盖不足。可以换一种更具体的说法再试。"
        )
    if truncated:
        warnings.append(f"命中的意象超过上限，已截断 {truncated} 个。")

    chart_facts: dict[str, Any] = {
        "text_length": len(inp.text),
        "max_keywords": inp.max_keywords,
        "keywords": [
            {
                "keyword": item["keyword"],
                "matched": item["matched"],
                "category": item["category"],
                **({"traditional": item["traditional"]} if inp.include_traditional else {}),
            }
            for item in hits
        ],
        "categories": categories,
        "matched_count": len(hits),
        "truncated": truncated,
        "unmatched": unmatched,
        "text_recorded": inp.store_text,
    }
    if inp.store_text:
        chart_facts["text"] = inp.text

    input_summary = {
        "text_length": len(inp.text),
        "max_keywords": inp.max_keywords,
        "include_traditional": inp.include_traditional,
        "store_text": inp.store_text,
    }

    convention_dump = convention.model_dump()
    convention_dump["school_note"] = SCHOOL_NOTE
    if not inp.store_text:
        warnings.append("已按你的选择不保存梦境原文，只保留命中的意象。")

    source_refs = [
        {"type": "rule", "id": "dream.lexicon.builtin", "note": f"内置词表 {len(ENTRIES)} 条，自编，长词优先匹配"},
        {"type": "rule", "id": "dream.match.longest_first", "note": "同一段文字优先匹配更长的词，命中后不重复匹配其子串"},
        {"type": "rule", "id": "dream.scope.cultural", "note": "象征说法定位为文化背景，不是对梦的解释"},
    ]

    return ChartResult(
        domain="dream",
        algorithm_version=settings.dream_algorithm_version,
        input_summary=input_summary,
        convention=convention_dump,
        chart_facts=chart_facts,
        triggered_rules=[],
        warnings=warnings,
        source_refs=source_refs,
    )
