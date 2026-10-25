"""塔罗引擎：无放回抽牌 + 牌阵位置分配，只出牌面事实。

固定顺序：
1. 由 deck 选项确定牌池（78 / 22 / 56）；
2. 由 seed 派生**两个独立**随机源：一个决定牌序，一个决定正逆位；
3. 无放回抽 N 张（N = 牌阵位置数）；
4. 逐位绑定位置名与牌面事实。

为什么两个随机源：如果同一序列同时决定牌序与正逆位，抽 1 张时牌序恒为池首，
正逆位就会退化成「序列第一个值是否小于阈值」，可复现但分布偏斜。分开之后，
同一 seed 依然完全可复现，且两张随机表互不干扰。

红线：不输出事件预测、不输出吉凶结论、不把关键词串成断语。
"""

from __future__ import annotations

import hashlib
import random
from datetime import datetime
from typing import Any

from app.core.config import settings
from app.domains.bazi.schemas import ChartResult
from app.domains.tarot import cards as K
from app.domains.tarot.schemas import TarotConvention, TarotInput


def _resolve_seed(seed: str | None) -> tuple[str, bool]:
    """返回 (实际使用的 seed, 是否为自动派生)。"""
    if seed:
        return seed, False
    stamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
    return f"auto-{stamp}", True


def _streams(seed: str) -> tuple[random.Random, random.Random]:
    """由 seed 派生两个互不相关的随机源（不同盐值 → 不同摘要）。"""
    order_digest = hashlib.sha256(f"order::{seed}".encode("utf-8")).hexdigest()
    flip_digest = hashlib.sha256(f"flip::{seed}".encode("utf-8")).hexdigest()
    return random.Random(int(order_digest[:16], 16)), random.Random(int(flip_digest[:16], 16))


def _pool(deck: str) -> tuple[K.CardDef, ...]:
    if deck == "major":
        return K.MAJOR
    if deck == "minor":
        return K.MINOR
    return K.ALL_CARDS


def calculate(inp: TarotInput, conv: TarotConvention | None = None) -> ChartResult:
    convention = conv or TarotConvention()
    warnings: list[str] = []

    pool = _pool(inp.deck)
    spread_meta = K.SPREADS[inp.spread]
    if inp.custom_positions:
        positions = tuple(inp.custom_positions)
        spread_name = f"自定义（{len(positions)} 位）"
    else:
        positions = tuple(spread_meta["positions"])  # type: ignore[arg-type]
        spread_name = str(spread_meta["name"])

    if len(positions) > len(pool):
        raise ValueError(f"牌阵需要 {len(positions)} 张，但当前牌池只有 {len(pool)} 张")

    seed_used, auto_seed = _resolve_seed(inp.seed)
    order_rng, flip_rng = _streams(seed_used)

    indices = list(range(len(pool)))
    order_rng.shuffle(indices)
    drawn = [pool[index] for index in indices[: len(positions)]]

    dealt: list[dict[str, Any]] = []
    for position, card in zip(positions, drawn):
        reversed_ = inp.allow_reversed and flip_rng.random() < inp.reversed_probability
        keywords = card["reversed"] if reversed_ else card["upright"]
        dealt.append(
            {
                "position": position,
                "card_id": card["id"],
                "name": card["name"],
                "name_cn": card["name_cn"],
                "suit": card["suit"],
                "number": card["number"],
                "element": card["element"],
                "orientation": "reversed" if reversed_ else "upright",
                "orientation_cn": "逆位" if reversed_ else "正位",
                "keywords": list(keywords),
            }
        )

    chart_facts: dict[str, Any] = {
        "spread": {
            "id": inp.spread,
            "name": spread_name,
            "positions": list(positions),
            "card_count": len(dealt),
        },
        "deck": {
            "mode": inp.deck,
            "pool_size": len(pool),
            "used": "全 78 张" if inp.deck == "all" else ("大阿卡纳 22 张" if inp.deck == "major" else "小阿卡纳 56 张"),
        },
        "draw": {
            "seed": seed_used,
            "auto_seed": auto_seed,
            "allow_reversed": inp.allow_reversed,
            "reversed_probability": inp.reversed_probability,
            "replacement": False,
        },
        "cards": dealt,
    }

    input_summary = {
        "spread": inp.spread,
        "deck": inp.deck,
        "card_count": len(dealt),
        "seed": seed_used,
        "question": inp.question if inp.store_question else None,
    }

    convention_dump = convention.model_dump()
    convention_dump["school_note"] = K.SCHOOL_NOTE
    warnings.append(K.SCHOOL_NOTE)
    if auto_seed:
        warnings.append(f"未提供 seed，已由当前时刻派生「{seed_used}」；如需复现同一次抽牌，请保存该值。")
    if inp.question and not inp.store_question:
        warnings.append("已按你的选择丢弃占问原文，命盘只保存牌阵与抽牌结果。")
    if not inp.allow_reversed:
        warnings.append("已关闭逆位：本次全部按正位解读，不做逆位关键词对照。")

    source_refs = [
        {"type": "rule", "id": "tarot.deck.no_replacement", "note": "无放回抽牌，同一牌阵内不会重复出现同一张牌"},
        {"type": "rule", "id": "tarot.rng.split", "note": "牌序与正逆位使用两个独立随机源，同一 seed 可完整复现"},
        {"type": "rule", "id": "tarot.spread.positions", "note": "位置名由牌阵定义，抽牌结果按位置顺序绑定"},
        {"type": "structure", "id": "tarot.rider_waite", "note": "牌名与编号为 Rider–Waite 体系公有结构；牌面图片不随仓库分发"},
    ]

    return ChartResult(
        domain="tarot",
        algorithm_version=settings.tarot_algorithm_version,
        input_summary=input_summary,
        convention=convention_dump,
        chart_facts=chart_facts,
        triggered_rules=[],
        warnings=warnings,
        source_refs=source_refs,
    )
