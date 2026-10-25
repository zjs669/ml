"""模型输出「信封」归一化（只修结构，不修事实）。

真实模型（实测 deepseek-v4.1-flash）经常在**外层结构**上跑偏：多出 `skill` / `scope` /
`chart_basis` 这类自造键，`observations` 用 `facts: [str]` + `label` 代替 `fact`，
`uncertainties` 写成对象数组。`ReportPayload` 是 `extra="forbid"`，这些偏差会让一份
内容其实合规的报告被判死，进而降级。

本模块只做**可枚举、可测试**的整形：

1. 顶层只保留 `ReportPayload` 的 7 个键；
2. `observations[].fact` 缺失时，依次退到 `facts`（字符串数组）/ `label`+`relation` / `group`；
3. `traditional_interpretations[].claim` 缺失时，退到 `text`/`content`/`interpretation`/`definition`；
4. `practical_reflections` / `uncertainties` 只保留字符串（对象取其 `fact`/`text`/`claim`）；
5. `citations` 只保留整数（允许 `"12"` 这种数字字符串）；
6. `summary` / `safety_note` 缺失时给中性固定文案。

明确**不做**的事：
- 不推断任何未出现的干支、星曜、门星神；
- 不新增 citation_id，未知 id 仍交给 `validator` 判 `citation_unknown`；
- 不改写任何已有字符串；
- 拿不到 `fact` 就留空，宁可让校验失败，也不编造句子。
"""

from __future__ import annotations

from typing import Any

from app.domains.llm.mock import SAFETY_NOTE

REPORT_KEYS = (
    "summary",
    "observations",
    "traditional_interpretations",
    "practical_reflections",
    "uncertainties",
    "citations",
    "safety_note",
)

FACT_KEYS = ("fact", "text", "statement", "description")
CLAIM_KEYS = ("claim", "text", "content", "interpretation", "definition")
MAX_FACT_CHARS = 800
MAX_TEXT_CHARS = 1200


def _text(value: Any, limit: int = MAX_TEXT_CHARS) -> str:
    if isinstance(value, str):
        return value.strip()[:limit]
    if isinstance(value, list):
        parts = [_text(item, limit) for item in value]
        return "；".join(part for part in parts if part)[:limit]
    if isinstance(value, dict):
        for key in FACT_KEYS + CLAIM_KEYS:
            nested = _text(value.get(key), limit)
            if nested:
                return nested
    return ""


def _first_text(item: dict[str, Any], keys: tuple[str, ...], limit: int) -> str:
    for key in keys:
        text = _text(item.get(key), limit)
        if text:
            return text
    return ""


def _ints(value: Any) -> list[int]:
    if not isinstance(value, list):
        return []
    result: list[int] = []
    for item in value:
        if isinstance(item, bool):
            continue
        if isinstance(item, int):
            result.append(item)
        elif isinstance(item, str) and item.strip().isdigit():
            result.append(int(item.strip()))
    return result


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        text = _text(item, MAX_FACT_CHARS)
        if text:
            result.append(text)
        elif isinstance(item, dict):
            # 形如 {"item": "..."} / {"note": "..."} 的对象，取第一个非空字符串值
            for nested in item.values():
                text = _text(nested, MAX_FACT_CHARS)
                if text:
                    result.append(text)
                    break
    return result


def _observation(item: Any) -> dict[str, Any] | None:
    if isinstance(item, str):
        text = item.strip()[:MAX_FACT_CHARS]
        return {"fact": text, "rule_ids": [], "citation_ids": []} if text else None
    if not isinstance(item, dict):
        return None

    fact = _first_text(item, FACT_KEYS, MAX_FACT_CHARS)
    if not fact:
        fact = _text(item.get("facts"), MAX_FACT_CHARS)
    if not fact:
        label = _text(item.get("label") or item.get("group"), 120)
        relation = _text(item.get("relation"), 60)
        members = _text(item.get("members"), 120)
        pieces = [piece for piece in (label, relation, members) if piece]
        fact = "：".join(pieces)[:MAX_FACT_CHARS]
    if not fact:
        return None

    return {
        "fact": fact,
        "rule_ids": [text for text in _strings(item.get("rule_ids"))],
        "citation_ids": _ints(item.get("citation_ids")),
    }


def _interpretation(item: Any) -> dict[str, Any] | None:
    if isinstance(item, str):
        text = item.strip()[:MAX_TEXT_CHARS]
        return {"claim": text, "citation_ids": [], "school_note": None} if text else None
    if not isinstance(item, dict):
        return None
    claim = _first_text(item, CLAIM_KEYS, MAX_TEXT_CHARS)
    if not claim:
        return None
    school_note = _text(item.get("school_note"), 400) or None
    return {
        "claim": claim,
        "citation_ids": _ints(item.get("citation_ids")),
        "school_note": school_note,
    }


def normalize_payload(
    payload: Any,
    *,
    allowed_chunk_ids: set[int] | None = None,
    allowed_rule_ids: set[str] | None = None,
) -> dict[str, Any]:
    """把模型输出整形成 `ReportPayload` 的形状；无法整形的内容直接丢弃。

    注意：如果既没有 observations 也没有 traditional_interpretations，返回空字典，
    让校验层按「缺少必填字段」判死。否则一个空对象 {} 会被补上默认 summary，
    变成“看起来合格、实际什么都没写”的报告，这是绝对不能接受的。

    `allowed_chunk_ids` 传入本次检索到的片段：模型偶尔会自造 citation_id，
    此时只删引用（并向 `meta_json` 记录），不伪造出处；一条解释如果引用全部无效，
    就连同它一起丢掉——按规则，没有依据的内容不许写成解释。

    `allowed_rule_ids` 传入本次真正触发的规则：模型偶尔会「多写一条关系」
    （例如盘面只有自刑，却宣称三会）。这种情况下**整条观察都丢弃**，而不只是删掉
    rule_id——因为文字本身已经是不可核验的断言。
    """
    if not isinstance(payload, dict):
        return {}

    observations = [
        observation
        for observation in (_observation(item) for item in payload.get("observations") or [])
        if observation
    ]
    interpretations = [
        interpretation
        for interpretation in (
            _interpretation(item) for item in payload.get("traditional_interpretations") or []
        )
        if interpretation
    ]
    if not observations and not interpretations:
        # 空壳或全是无法识别的结构：不补默认值，交给校验层拒绝
        return {}

    if allowed_rule_ids is not None:
        kept_observations: list[dict[str, Any]] = []
        for observation in observations:
            raw_ids = observation["rule_ids"]
            if not raw_ids:
                kept_observations.append(observation)
                continue
            valid = [rid for rid in raw_ids if rid in allowed_rule_ids]
            if not valid:
                # 引用了本次未触发的规则 → 文字也不可信，整条丢掉
                continue
            observation["rule_ids"] = valid
            kept_observations.append(observation)
        observations = kept_observations
        if not observations and not interpretations:
            return {}

    if allowed_chunk_ids is not None:
        for observation in observations:
            observation["citation_ids"] = [
                item for item in observation["citation_ids"] if item in allowed_chunk_ids
            ]
        kept: list[dict[str, Any]] = []
        for item in interpretations:
            item["citation_ids"] = [cid for cid in item["citation_ids"] if cid in allowed_chunk_ids]
            if item["citation_ids"]:
                kept.append(item)
        interpretations = kept
        if not observations and not interpretations:
            return {}

    summary = _text(payload.get("summary"))
    if not summary:
        # 模型把总览写成了 scope/chart_basis 时，取其中最像总览的一段；都没有就复述第一条事实
        summary = _first_text(payload, ("scope", "overview"), MAX_TEXT_CHARS)
    if not summary and observations:
        summary = observations[0]["fact"][:400]
    if not summary:
        summary = "本报告仅复述盘面事实，未生成总览句。"

    citations = _ints(payload.get("citations"))
    if allowed_chunk_ids is not None:
        citations = [item for item in citations if item in allowed_chunk_ids]
    if not citations:
        for item in interpretations:
            citations.extend(item["citation_ids"])
        citations = list(dict.fromkeys(citations))

    return {
        "summary": summary,
        "observations": observations[:40],
        "traditional_interpretations": interpretations[:20],
        "practical_reflections": _strings(payload.get("practical_reflections"))[:20],
        "uncertainties": _strings(payload.get("uncertainties"))[:20],
        "citations": citations[:40],
        "safety_note": _text(payload.get("safety_note"), MAX_FACT_CHARS) or SAFETY_NOTE,
    }


def dropped_keys(payload: Any) -> list[str]:
    """记录被丢弃的顶层自造键，便于观察模型退化趋势（不影响校验结果）。"""
    if not isinstance(payload, dict):
        return []
    return sorted(key for key in payload if key not in REPORT_KEYS)


FOLLOWUP_KEYS = ("answer", "points", "citations", "uncertainties", "safety_note")
ANSWER_KEYS = ("answer", "response", "content", "text", "reply", "解释", "回答")


def normalize_followup(payload: Any) -> dict[str, Any]:
    """整形追问回答的信封；拿不到 answer 就返回空字典交给校验层判死。

    与报告不同：**不过滤 citations**。追问只有一个回答，引用了不存在的 chunk_id
    就是硬错，应当重试或降级，而不是静默删掉引用后当没事发生。
    """
    if not isinstance(payload, dict):
        return {}
    answer = _first_text(payload, ANSWER_KEYS, MAX_TEXT_CHARS)
    if not answer:
        return {}
    points = _strings(payload.get("points") or payload.get("bullets") or payload.get("details"))
    return {
        "answer": answer,
        "points": points[:8],
        "citations": _ints(payload.get("citations") or payload.get("citation_ids"))[:20],
        "uncertainties": _strings(payload.get("uncertainties") or payload.get("caveats"))[:8],
        "safety_note": _text(payload.get("safety_note"), 400) or SAFETY_NOTE,
    }
