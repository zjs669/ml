"""SKILL.md 加载与注入的行为约定。

红线：
1. 全局与领域 SKILL.md 每次必注入，不依赖触发词；
2. 只有 `status: approved` 会被加载，`_draft/` 不递归；
3. 预算与单文件截断必须确定，不能随调用次数变化；
4. 技能段只是提示，不得成为事实或引用来源。
"""

from __future__ import annotations

from pathlib import Path

from app.domains.reporting.service import build_user_prompt
from app.domains.skills import loader, skillfile

CARD = """---
id: {id}
domain: {domain}
title: {title}
topics: [overview]
triggers: [三合, 相冲]
priority: {priority}
status: {status}
always: {always}
max_chars: {max_chars}
source: 单元测试
updated: 2026-10-25
---

正文：{body}
"""


def _write(path: Path, **kwargs) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    defaults = dict(
        id="x", domain="bazi", title="占位", priority=10,
        status="approved", always="false", max_chars=1200, body="先看柱位，再看关系。",
    )
    defaults.update(kwargs)
    path.write_text(CARD.format(**defaults), encoding="utf-8")


def _use(tmp_path: Path, monkeypatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(skillfile, "SKILLS_DIR", tmp_path)
    monkeypatch.setattr(settings, "skills_extra_dirs", "")
    monkeypatch.setattr(settings, "skills_external_in_product", False)
    skillfile.reload()


def test_global_and_domain_skill_are_always_injected(tmp_path, monkeypatch) -> None:
    _write(tmp_path / "SKILL.md", id="common.skill", domain="common", title="全局")
    _write(tmp_path / "bazi" / "SKILL.md", id="bazi.skill", domain="bazi", title="四柱")
    _use(tmp_path, monkeypatch)
    try:
        block = skillfile.render("bazi", text="完全无关的句子")
        assert block.ids == ["common.skill", "bazi.skill"]
        assert "【必读技能】" in block.text
        assert "【参考经验】" not in block.text
    finally:
        skillfile.reload()


def test_cards_need_trigger_and_approved(tmp_path, monkeypatch) -> None:
    _write(tmp_path / "bazi" / "SKILL.md", id="bazi.skill", domain="bazi")
    _write(tmp_path / "bazi" / "cards" / "a.md", id="card.a", title="A")
    _write(tmp_path / "bazi" / "cards" / "b.md", id="card.b", title="B", status="draft")
    _use(tmp_path, monkeypatch)
    try:
        assert skillfile.available_ids("bazi") == ["bazi.skill", "card.a"]
        hit = skillfile.render("bazi", text="日支与月支相冲")
        assert "card.a" in hit.ids
        assert "card.b" not in hit.ids
        miss = skillfile.render("bazi", text="今天天气不错")
        assert miss.ids == ["bazi.skill"]
    finally:
        skillfile.reload()


def test_draft_directory_is_never_loaded(tmp_path, monkeypatch) -> None:
    _write(tmp_path / "bazi" / "SKILL.md", id="bazi.skill")
    _write(tmp_path / "_draft" / "draft.md", id="draft.card", status="approved")
    _use(tmp_path, monkeypatch)
    try:
        assert skillfile.available_ids("bazi") == ["bazi.skill"]
    finally:
        skillfile.reload()


def test_budget_and_per_file_truncation(tmp_path, monkeypatch) -> None:
    long_body = "这是一段很长的技能正文。" * 30
    _write(tmp_path / "SKILL.md", id="common.skill", domain="common", max_chars=60, body=long_body)
    _write(tmp_path / "bazi" / "SKILL.md", id="bazi.skill", max_chars=60, body=long_body)
    _use(tmp_path, monkeypatch)
    try:
        block = skillfile.render("bazi", text="", budget=400)
        assert len(block.text) <= 400
        assert "…[截断]" in block.text
    finally:
        skillfile.reload()


def test_cross_domain_is_isolated(tmp_path, monkeypatch) -> None:
    _write(tmp_path / "bazi" / "SKILL.md", id="bazi.skill", domain="bazi")
    _write(tmp_path / "ziwei" / "SKILL.md", id="ziwei.skill", domain="ziwei")
    _use(tmp_path, monkeypatch)
    try:
        assert skillfile.render("bazi", text="").ids == ["bazi.skill"]
    finally:
        skillfile.reload()


def test_bench_profile_does_not_use_product_persona(tmp_path, monkeypatch) -> None:
    _write(tmp_path / "SKILL.md", id="common.skill", domain="common")
    _write(tmp_path / "bazi" / "SKILL.md", id="bazi.skill", domain="bazi")
    _write(tmp_path / "bench" / "SKILL.md", id="bench.skill", domain="bench")
    _write(tmp_path / "bazi" / "cards" / "a.md", id="card.a")
    _use(tmp_path, monkeypatch)
    try:
        block = skillfile.render("bazi", text="三合 相冲", profile="bench")
        assert "bench.skill" in block.ids
        assert "common.skill" not in block.ids
        assert "bazi.skill" not in block.ids
        assert "card.a" in block.ids
    finally:
        skillfile.reload()


def test_external_pack_is_opt_in_and_bench_only(tmp_path, monkeypatch) -> None:
    from app.core.config import settings

    _write(tmp_path / "local" / "bazi" / "SKILL.md", id="bazi.skill", domain="bazi")
    ext = tmp_path / "ext"
    (ext / "interpretation").mkdir(parents=True)
    (ext / "SKILL.md").write_text(
        "---\nname: taibu-divination\ndescription: 外部包\n---\n\n# 太卜\n外部工具说明",
        encoding="utf-8",
    )
    (ext / "interpretation" / "bazi.md").write_text("# 八字解读\n先看日主\n", encoding="utf-8")

    monkeypatch.setattr(skillfile, "SKILLS_DIR", tmp_path / "local")
    monkeypatch.setattr(settings, "skills_extra_dirs", str(ext))
    monkeypatch.setattr(settings, "skills_external_in_product", False)
    skillfile.reload()
    try:
        bench = skillfile.render("bazi", text="四柱 大运", profile="bench")
        assert "taibu-divination.interpretation.bazi" in bench.ids
        product = skillfile.render("bazi", text="四柱 大运", profile="product")
        assert all(not item.startswith("taibu") for item in product.ids)

        settings.skills_external_in_product = True
        allowed = skillfile.render("bazi", text="四柱 大运", profile="product")
        assert "taibu-divination.interpretation.bazi" in allowed.ids
        assert "【外部技能包】" in allowed.text
    finally:
        monkeypatch.setattr(settings, "skills_extra_dirs", "")
        skillfile.reload()


def test_report_prompt_puts_skills_first_and_contract_last() -> None:
    spec = next(item for item in loader.load_all() if item.domain == "bazi")
    block = skillfile.render("bazi", text="三合与相冲")
    prompt = build_user_prompt(
        spec,
        facts={"pillars": {}, "relations": {"conflicts": [], "incomplete": []}},
        rules=[
            {
                "rule_id": "rel.branch.liuhe.zi_chou",
                "relation": "六合",
                "label": "子丑六合",
                "note": "测试",
            }
        ],
        chunks=[],
        depth="brief",
        topic=None,
        skill_text=block.text,
    )
    assert prompt.lstrip().startswith("【必读技能】")
    assert prompt.rstrip().endswith("不确定的内容写进 uncertainties。")
    assert "bazi.relations.order.v1" in prompt
