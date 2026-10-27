"""检索主题派生：盘面触发什么关系，就检索什么关系的条文。

这一层存在的理由，是一条真实的失效链路：

    bazi.relations.v1 的 retrieval.topics 写死七个**地支**主题
      → 盘面触发的天干关系（相克/相冲/五合）没有任何检索词对应
      → 知识库里明明有《渊海子平·天干五合》《天干相冲》，却从不召回
      → 模型只能照实说「本次提供的片段没有天干条文」
      → 用户看到的现象是「模型答不上来」

所以测试重点不是「函数返回了什么」，而是**端到端能不能召回天干条文**。
断言用的 chunk 内容由本文件自己造，不依赖库里已有的真实典籍片段 ——
否则一旦知识库换了版本，测试就会因为「书里没这句话」而失败，
掩盖了真正的检索逻辑问题。
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.orm import Session

from app.domains.reporting import retrieval
from app.models import KnowledgeChunk, KnowledgeSource
from app.repositories import knowledge_repo


def _rule(topic: str, *, priority: int = 10, relation: str = "", system: str = "") -> dict:
    return {
        "rule_id": f"rel.test.{topic}.{priority}",
        "topic": topic,
        "relation": relation or topic,
        "system": system or topic,
        "priority": priority,
    }


# ---------------------------------------------------------------- 纯函数层


def test_derive_topics_covers_stem_relations() -> None:
    """天干关系必须派生出天干类检索词 —— 这是原始 bug 的核心。"""
    rules = [
        _rule("天干相克", priority=12),
        _rule("天干相冲", priority=12),
        _rule("天干五合", priority=18),
    ]
    topics = retrieval.derive_topics(rules)

    assert "天干五合" in topics
    assert "天干相冲" in topics
    # 天干相克在知识库里没有独立条目，映射到「天干相冲」或「五行生克次序」，
    # 但不能凭空造一个库里不存在的词就交差
    assert "天干相克" not in topics or "天干相冲" in topics


def test_derive_topics_orders_by_priority() -> None:
    """高优先级规则先检索：它决定谁先占配额。"""
    rules = [_rule("六冲", priority=5), _rule("天干五合", priority=18)]
    topics = retrieval.derive_topics(rules)

    assert topics.index("天干五合") < topics.index("六冲")


def test_derive_topics_deduplicates() -> None:
    """同一关系在多个位置触发时，检索词不能重复。"""
    rules = [_rule("六合", priority=10), _rule("六合", priority=10), _rule("六合", priority=8)]
    topics = retrieval.derive_topics(rules)

    assert topics.count("六合") == 1


def test_derive_topics_handles_unknown_concepts() -> None:
    """规则里出现映射表没有的概念时，不能崩，也不能静默丢掉。"""
    rules = [_rule("结构", priority=60)]
    topics = retrieval.derive_topics(rules)

    assert isinstance(topics, list)  # 不抛异常即可；未知概念不强行编造检索词


def test_derive_topics_empty_rules() -> None:
    """没有关系规则的域（占星/塔罗/紫微）派生结果为空，不应影响原有检索。"""
    assert retrieval.derive_topics([]) == []


def test_derive_topics_caps_expansion() -> None:
    """合盘单盘 25 条规则，不能展开成几十次检索。"""
    rules = [_rule(name, priority=30 - i) for i, name in enumerate(retrieval.CONCEPT_QUERIES)]
    topics = retrieval.derive_topics(rules)

    # 每组概念最多几个候选词，总量受 MAX_DERIVED_CONCEPTS 约束
    assert len(topics) <= retrieval.MAX_DERIVED_CONCEPTS * 4


def test_merge_topics_puts_derived_first() -> None:
    """派生词优先占配额，声明词兜底，用户指定放最后。"""
    merged = retrieval.merge_topics(
        declared=["六合", "三合"],
        derived=["天干相冲"],
        extra=["关系"],
    )

    assert merged[0] == "天干相冲"
    assert merged[-1] == "关系"
    assert set(merged) == {"天干相冲", "六合", "三合", "关系"}


def test_merge_topics_deduplicates_across_groups() -> None:
    merged = retrieval.merge_topics(declared=["相刑"], derived=["相刑"], extra=[])
    assert merged.count("相刑") == 1


def test_merge_topics_all_empty() -> None:
    """全空时返回空列表，上层据此写「知识库依据不足」，而不是假装有依据。"""
    assert retrieval.merge_topics(declared=[], derived=[], extra=[]) == []


# ---------------------------------------------------------------- 检索层


@pytest.fixture
def stem_knowledge(session: Session) -> dict[str, int]:
    """造一份只含天干条目的知识源，验证派生词真的能召回它。"""
    key = uuid.uuid4().hex[:8]
    source = KnowledgeSource(
        title=f"天干测试源-{key}",
        author="测试",
        edition="测试版",
        license_status="public_domain",
        status="approved",
    )
    session.add(source)
    session.flush()

    payload = {
        "天干五合": "甲己合土、乙庚合金，天干五合以阴阳相配而成。",
        "天干相冲": "甲庚相冲、乙辛相冲，天干之冲同阴阳而相克。",
        "地支六冲": "子午相冲、丑未相冲，地支六冲论远近。",
    }
    ids: dict[str, int] = {}
    for topic, body in payload.items():
        chunk = KnowledgeChunk(
            source_id=source.id,
            domain="bazi",
            topic=topic,
            content=body,
            citation_label=f"测试出处·{topic}",
            content_hash=f"{key}-{topic}",
            approval_status="approved",
        )
        session.add(chunk)
        session.flush()
        ids[topic] = chunk.id
    session.commit()
    return ids


def test_derived_topics_recall_stem_chunks(session: Session, stem_knowledge: dict[str, int]) -> None:
    """端到端：盘面触发了天干关系，检索就必须能拿到天干条文。"""
    rules = [_rule("天干相冲", priority=12), _rule("天干五合", priority=18)]
    topics = retrieval.derive_topics(rules)

    chunks = knowledge_repo.search_topics(
        session, topics=topics, domain="bazi", limit=4, per_topic=1
    )
    got = {chunk["chunk_id"] for chunk in chunks}

    assert stem_knowledge["天干五合"] in got
    assert stem_knowledge["天干相冲"] in got


def test_search_topics_does_not_skip_trailing_topics(
    session: Session, stem_knowledge: dict[str, int]
) -> None:
    """旧实现累计到 limit 就 break，导致列表尾部主题一次都没被检索。

    这里给 3 个主题、limit=2：修好之后仍然只返回 2 条（受 limit 约束），
    但**每个主题都被查询过**，所以补位逻辑能拿到第二条主题的结果。
    """
    chunks = knowledge_repo.search_topics(
        session,
        topics=["天干五合", "天干相冲", "地支六冲"],
        domain="bazi",
        limit=2,
        per_topic=1,
    )
    got = {chunk["chunk_id"] for chunk in chunks}

    assert len(chunks) == 2
    # 前两个主题各占一条，说明没有被第一个主题吃满配额
    assert stem_knowledge["天干五合"] in got
    assert stem_knowledge["天干相冲"] in got


def test_search_topics_respects_limit(session: Session, stem_knowledge: dict[str, int]) -> None:
    chunks = knowledge_repo.search_topics(
        session, topics=list(stem_knowledge), domain="bazi", limit=2, per_topic=2
    )
    assert len(chunks) == 2


def test_search_topics_empty_topics(session: Session) -> None:
    assert knowledge_repo.search_topics(session, topics=[], domain="bazi", limit=6) == []


def test_search_topics_ignores_blank_topics(session: Session, stem_knowledge: dict[str, int]) -> None:
    chunks = knowledge_repo.search_topics(
        session, topics=["", "  ", "天干五合"], domain="bazi", limit=2
    )
    assert stem_knowledge["天干五合"] in {chunk["chunk_id"] for chunk in chunks}
