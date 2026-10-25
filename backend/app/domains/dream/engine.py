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

from typing import Any

from app.core.config import settings
from app.domains.bazi.schemas import ChartResult
from app.domains.dream import lexicon as K
from app.domains.dream.schemas import DreamConvention, DreamInput

#: 匹配用的词 → 条目，长词优先
_LOOKUP: dict[str, K.DreamEntry] = {}
for _entry in K.ENTRIES:
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
    warnings: list[str] = [K.SCHOOL_NOTE]

    hits, truncated = _extract(inp.text, inp.max_keywords)

    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in hits:
        block = {"keyword": item["keyword"], "matched": item["matched"]}
        if inp.include_traditional:
            block["traditional"] = item["traditional"]
        grouped.setdefault(item["category"], []).append(block)

    categories = [
        {"category": name, "items": grouped[name]}
        for name in K.CATEGORIES
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
    convention_dump["school_note"] = K.SCHOOL_NOTE
    if not inp.store_text:
        warnings.append("已按你的选择不保存梦境原文，只保留命中的意象。")

    source_refs = [
        {"type": "rule", "id": "dream.lexicon.builtin", "note": f"内置词表 {len(K.ENTRIES)} 条，自编，长词优先匹配"},
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
