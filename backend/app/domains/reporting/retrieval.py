"""检索主题派生：让检索词跟着盘面事实走，而不是靠技能包里手写的固定词表。

为什么需要这一层
----------------
技能包的 `retrieval.topics` 是**静态**的：`bazi.relations.v1` 写了
六合/三合/三会/六冲/相刑/相害/相破 七个词，全是地支。而四柱的
`triggered_rules` 里天干关系恰恰高频（乙辛相克、乙辛相冲、乙庚五合）。
结果是：盘面明明触发了「天干相冲」，检索却从不召回《渊海子平·天干相冲》，
模型只能照实说「本次提供的片段没有天干条文」，用户看到的就是「答不上来」。

静态词表永远会漏 —— 盘面组合是开放的，而词表是人手写的。所以这里改成
**从 triggered_rules 反查主题**：盘面触发了什么关系，就检索什么关系的条文。

映射表为什么是手写的
--------------------
规则的 `topic` 是「术数概念名」（六冲、相刑、半会），知识库的 `topic`
是「典籍章节名」（地支六冲、地支相刑、地支三会方局）。两者名字不一致，
且知识库的检索是 ngram 全文匹配 —— 词形对不上就召回不到。

解决办法是两层：

1. 检索层先按 `knowledge_chunks.topic`（典籍章节名）匹配，未命中再退回 ngram
   全文检索（见 `knowledge_repo.search(prefer_topic=True)`）。实测加上这一步后，
   短概念词全部精准命中：相刑→地支相刑、六冲→地支六冲、相害→地支六害、
   半会→地支三会方局。没有这一步，两字词在 ngram 下会召回一堆无关条目。

2. 本模块只维护「概念名 → 检索词」的最小映射，处理章节名与概念名不一致的情况
   （典籍叫「地支六害」，盘面叫「相害」）。别名不贪多：每多一个别名，就多一次
   兜底全文检索，反而会把术语词典的泛化条目带进上下文。

关于「天干相克」
----------------
知识库里**没有**独立的「天干相克」条目：《渊海子平·天干相冲》原文写的是
「天干之冲，同阴阳而相克」，相克的判据寄生在相冲条目里。这里如实映射到
「天干相冲」，并在报告里保留「知识库无独立条目」的可能性 —— 不假装有依据。
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

#: 规则 `topic` / `system` / `relation` → 候选检索词（按实测召回效果排序）。
#:
#: 键取「规则里的概念名」，值是「知识库里能召回到对应条目的词形」。
#: 一个概念配多个词是为了兼容不同典籍的措辞差异，检索层按顺序尝试。
CONCEPT_QUERIES: dict[str, tuple[str, ...]] = {
    # ---- 地支 ----
    "六合": ("六合",),
    "三合": ("三合",),
    "三会": ("三会",),
    # 半会是「三会缺一」的形态，典籍里没有独立章节，指向三会条文
    "半会": ("三会",),
    "六冲": ("六冲",),
    "相刑": ("相刑",),
    "三刑": ("相刑",),
    "自刑": ("相刑",),
    "六害": ("六害",),
    "相害": ("六害",),   # 典籍章节名是「地支六害」，概念名是「相害」
    "相破": ("相破",),
    "六破": ("相破",),
    # ---- 天干 ----
    "天干五合": ("天干五合",),
    "天干相冲": ("天干相冲",),
    # 知识库里没有独立的「天干相克」章节：《渊海子平·天干相冲》原文写的是
    # 「天干之冲，同阴阳而相克」，相克判据寄生在相冲条目里。如实指向相冲，
    # 并在 uncertainties 里保留「无独立条目」的可能，不假装有依据。
    "天干相克": ("天干相冲", "五行生克次序"),
    # ---- 综合 ----
    "合冲并见": ("合冲并见",),
    "合化": ("合化",),
}

#: 规则里可能承载「概念名」的字段，按可信度排序。
_TOPIC_FIELDS = ("topic", "relation", "system")

#: 一次报告最多派生多少组候选词。盘面规则可能很多（合盘 25 条），
#: 全部展开会让检索变成几十次查询；这里只取优先级最高的若干组。
MAX_DERIVED_CONCEPTS = 6


def _rule_concepts(rule: dict[str, Any]) -> list[str]:
    """从一条规则里取出它对应的概念名（可能命中多个字段，去重保序）。"""
    found: list[str] = []
    for field in _TOPIC_FIELDS:
        value = rule.get(field)
        if isinstance(value, str) and value in CONCEPT_QUERIES and value not in found:
            found.append(value)
    return found


def derive_topics(rules: Iterable[dict[str, Any]]) -> list[str]:
    """把 `triggered_rules` 翻译成候选检索词，按规则优先级排序、去重。

    排序依据：规则的 `priority` 越大越先检索（引擎里优先级高的关系更"显著"）。
    同优先级保持盘面原始顺序，保证同一份盘的检索结果可复现。

    返回的是**扁平化的候选词序列**，不是「每概念一组」——检索层按顺序尝试，
    命中即止，天然实现了「高优先级概念优先占配额」。
    """
    ordered = sorted(
        (rule for rule in rules if isinstance(rule, dict)),
        key=lambda rule: -int(rule.get("priority") or 0),
    )

    concepts: list[str] = []
    for rule in ordered:
        for concept in _rule_concepts(rule):
            if concept not in concepts:
                concepts.append(concept)
        if len(concepts) >= MAX_DERIVED_CONCEPTS:
            break

    topics: list[str] = []
    for concept in concepts[:MAX_DERIVED_CONCEPTS]:
        for query in CONCEPT_QUERIES.get(concept, (concept,)):
            if query not in topics:
                topics.append(query)
    return topics


def merge_topics(
    declared: Iterable[str],
    derived: Iterable[str],
    extra: Iterable[str] = (),
) -> list[str]:
    """把「技能包声明词」和「盘面派生词」合并成一个检索序列。

    顺序刻意是 **派生 → 声明 → 用户指定**：
    - 派生词来自这份盘真实触发的关系，命中率最高，应优先占配额；
    - 声明词是技能包的通用兜底，防止派生词全落空时报告没有任何依据；
    - 用户显式指定的 topic 放最后，它只是补一个方向，不该挤掉盘面事实。

    任一段为空都不影响其它段，全空时返回空列表（上层据此写「知识库依据不足」）。
    """
    merged: list[str] = []
    for group in (derived, declared, extra):
        for item in group:
            if item and item not in merged:
                merged.append(item)
    return merged
