"""知识库检索的域映射测试。

知识源按「典籍所属领域」归档，但注册表里有派生域（紫微运限/飞星、合盘）。
若严格按 domain 精确匹配，这些派生域永远检索不到片段，
报告里的 traditional_interpretations 会永远是空数组 —— 看起来「正常」，实际是哑火。
"""

from __future__ import annotations

import pytest

from app.repositories.knowledge_repo import DOMAIN_KNOWLEDGE_PARENT, knowledge_domain


def test_derived_domains_map_to_parent() -> None:
    assert knowledge_domain("ziwei_horoscope") == "ziwei"
    assert knowledge_domain("ziwei_flying") == "ziwei"
    assert knowledge_domain("hepan") == "bazi"


def test_primary_domains_unchanged() -> None:
    for domain in ("bazi", "ziwei", "liuyao", "qimen", "almanac", "tarot", "dream", "mbti"):
        assert knowledge_domain(domain) == domain


def test_none_passes_through() -> None:
    assert knowledge_domain(None) is None


def test_mapping_targets_are_primary_domains() -> None:
    """映射目标不能又是另一个派生域，否则会形成链式解析。"""
    for derived, parent in DOMAIN_KNOWLEDGE_PARENT.items():
        assert parent not in DOMAIN_KNOWLEDGE_PARENT, f"{derived} → {parent} 指向了另一个派生域"
        assert parent != derived


def test_every_registered_domain_resolves() -> None:
    from app.domains.registry import supported_domains

    for domain in supported_domains():
        resolved = knowledge_domain(domain)
        assert resolved and isinstance(resolved, str)
