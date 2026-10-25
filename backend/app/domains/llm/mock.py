"""Mock Provider：完全确定性地把盘面事实渲染成合规报告。

刻意不生成任何"看起来在预测"的句子——它存在的意义是让前端联调、
校验链与回归测试可以离线跑，而不是伪造准确率。
真实模型接入后，本文件仍在测试里作为基准输出使用。

按 domain 分派：四柱读 pillars / 五行计数，紫微读农历日期 / 五行局 / 宫位，
其他术数暂用通用扇面。新增术数只需加一个 `_xxx_observations` 并在 `_OBSERVERS` 登记。
"""

from __future__ import annotations

from typing import Any

from app.domains.llm.base import LLMProvider, LLMRequest, LLMResponse

POSITION_LABELS = {"year": "年柱", "month": "月柱", "day": "日柱", "hour": "时柱"}
ELEMENTS = ("木", "火", "土", "金", "水")

SAFETY_NOTE = (
    "以上内容为传统命理框架下的文化解释，不构成医疗、法律、投资、婚姻等任何专业建议，"
    "也不能用于预测具体事件。请以现实证据与专业意见为准。"
)


def pillar_sentence(key: str, pillar: dict[str, Any]) -> str:
    hidden = "、".join(f"{item['stem']}({item['level']})" for item in pillar.get("hidden_stems", []))
    text = (
        f"{POSITION_LABELS[key]}为{pillar['text']}：天干{pillar['stem']}"
        f"（{pillar['stem_polarity']}{pillar['stem_element']}），"
        f"地支{pillar['branch']}（{pillar['branch_element']}），十神为{pillar['ten_god']}"
    )
    if hidden:
        text += f"，藏干{hidden}"
    if pillar.get("uncertain"):
        text += "（时辰未知，此项为占位结果）"
    return text


def _rule_observations(rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "fact": f"触发关系规则「{rule['relation']}」：{rule['label']}（{rule['note']}）",
            "rule_ids": [rule["rule_id"]],
            "citation_ids": [],
        }
        for rule in rules
    ]


def _bazi_observations(facts: dict[str, Any], rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    for key in ("year", "month", "day", "hour"):
        pillar = facts.get("pillars", {}).get(key)
        if pillar:
            observations.append(
                {"fact": pillar_sentence(key, pillar), "rule_ids": [], "citation_ids": []}
            )

    counts = facts.get("five_elements_count", {})
    raw = counts.get("raw", {})
    weighted = counts.get("weighted", {})
    if raw:
        detail = "，".join(
            f"{element} {raw.get(element, 0):g}（加权 {weighted.get(element, 0):g}）"
            for element in ELEMENTS
        )
        missing = counts.get("missing") or []
        missing_text = f"；原值缺失：{'、'.join(missing)}" if missing else ""
        observations.append(
            {
                "fact": f"五行计数（口径 {counts.get('weight_rule', 'weight-v1')}）：{detail}{missing_text}",
                "rule_ids": [],
                "citation_ids": [],
            }
        )
    observations.extend(_rule_observations(rules))
    return observations


def _bazi_summary(facts: dict[str, Any], rules: list[dict[str, Any]]) -> str:
    day_master = facts.get("day_master", {})
    return (
        f"本盘日主为{day_master.get('stem', '')}"
        f"（{day_master.get('polarity', '')}{day_master.get('element', '')}），"
        f"共触发 {len(rules)} 条关系规则。以下仅陈述盘面事实与可查证的典籍条目，不作吉凶推断。"
    )


def _ziwei_observations(facts: dict[str, Any], rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []

    def emit(fact: str) -> None:
        observations.append({"fact": fact, "rule_ids": [], "citation_ids": []})

    lunar = facts.get("lunar_date") or {}
    if lunar.get("text"):
        suffix = "" if facts.get("hour_known", True) else "（时辰未知，时支为占位值）"
        emit(
            f"农历为{lunar['text']}（{facts.get('year_ganzhi', '')}年，属{facts.get('year_zodiac', '')}），"
            f"时支为{facts.get('hour_branch', '')}{suffix}"
        )

    bureau = facts.get("five_element_bureau") or {}
    life = facts.get("life_palace") or {}
    if bureau.get("name"):
        emit(
            f"命宫为{life.get('text', '')}（{life.get('branch', '')}宫），"
            f"纳音{bureau.get('life_palace_nayin', '')}，五行局为{bureau['name']}"
        )

    life_palace = next(
        (item for item in facts.get("palaces") or [] if item.get("order") == 0), None
    )
    if life_palace:
        main = "、".join(life_palace.get("main_stars") or []) or "无十四主星（空宫）"
        text = f"命宫主星为{main}"
        aux = "、".join(life_palace.get("aux_stars") or [])
        if aux:
            text += f"，同宫辅星为{aux}"
        emit(text)

    body = facts.get("body_palace") or {}
    if body.get("branch"):
        emit(f"身宫落在{body.get('palace', '')}（{body['branch']}宫）")

    transformations = facts.get("transformations") or []
    if transformations:
        detail = "、".join(
            f"{item['star']}化{item['type']}（{item['palace']}）" for item in transformations
        )
        emit(f"生年四化：{detail}")

    dayun = facts.get("dayun") or []
    if isinstance(dayun, list) and dayun:
        first = dayun[0]
        emit(
            f"大限{'顺行' if facts.get('dayun_forward') else '逆行'}，"
            f"第一限起于{first.get('palace', '')}（{first.get('start_age')}–{first.get('end_age')} 岁）"
        )

    observations.extend(_rule_observations(rules))
    return observations


def _ziwei_summary(facts: dict[str, Any], rules: list[dict[str, Any]]) -> str:
    bureau = (facts.get("five_element_bureau") or {}).get("name", "")
    life = (facts.get("life_palace") or {}).get("text", "")
    return (
        f"本盘命宫为{life}，五行局为{bureau}，共标记 {len(rules)} 条结构规则。"
        "以下仅陈述盘面事实与可查证的典籍条目，不作吉凶推断，也不做流年推演。"
    )


def _liuyao_observations(facts: dict[str, Any], rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []

    def emit(fact: str) -> None:
        observations.append({"fact": fact, "rule_ids": [], "citation_ids": []})

    day = facts.get("day_pillar") or {}
    month = facts.get("month_build") or {}
    lunar = facts.get("lunar_date") or {}
    if facts.get("method_label"):
        emit(
            f"起卦方式为{facts['method_label']}，起卦时刻{facts.get('cast_at', '')}"
            f"（农历{lunar.get('text', '')}），时支为{facts.get('hour_branch', '')}"
        )
    if day.get("text"):
        emit(
            f"日辰为{day['text']}，月建为{month.get('text', '')}"
            f"（{month.get('jie', '')}之后），本旬空亡为{'、'.join(facts.get('xun_kong') or [])}"
        )

    original = facts.get("original") or {}
    if original.get("name"):
        emit(
            f"本卦为{original['name']}，卦宫为{original.get('palace', '')}"
            f"（{original.get('palace_element', '')}），属{original.get('phase', '')}之位，"
            f"世在{original.get('shi')}爻、应在{original.get('ying')}爻"
        )
        shi_line = next((line for line in original.get("lines", []) if line.get("shi")), None)
        if shi_line:
            emit(
                f"世爻为第{shi_line['position']}爻，纳甲{shi_line['najia']}"
                f"（{shi_line['element']}），六亲为{shi_line['six_relation']}，六神为{shi_line['liu_shen']}"
            )

    moving = facts.get("moving_lines") or []
    changed = facts.get("changed") or {}
    if moving:
        positions = "、".join(f"第{item}爻" for item in moving)
        emit(
            f"动爻为{positions}，变卦为{changed.get('name', '')}，"
            f"变卦卦宫为{changed.get('palace', '')}（{changed.get('palace_element', '')}）"
        )
    elif original:
        emit("六爻全无动爻，本盘为静盘，无变卦")

    mutual = facts.get("mutual") or {}
    if mutual.get("name"):
        emit(f"互卦为{mutual['name']}（取本卦二三四爻为下、三四五爻为上）")

    observations.extend(_rule_observations(rules))
    return observations


def _liuyao_summary(facts: dict[str, Any], rules: list[dict[str, Any]]) -> str:
    original = facts.get("original") or {}
    return (
        f"本卦为{original.get('name', '')}，卦宫为{original.get('palace', '')}"
        f"（{original.get('palace_element', '')}），共标记 {len(rules)} 条结构规则。"
        "以下仅陈述盘面事实与可查证的典籍条目，不作吉凶推断，也不给应期。"
    )


def _qimen_observations(facts: dict[str, Any], rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []

    def emit(fact: str) -> None:
        observations.append({"fact": fact, "rule_ids": [], "citation_ids": []})

    term = facts.get("term") or {}
    dun = facts.get("dun") or {}
    fu_tou = facts.get("fu_tou") or {}
    if term.get("name") and dun.get("text"):
        emit(
            f"起局时刻{facts.get('cast_at', '')}在节气「{term['name']}」之后，"
            f"符头为{fu_tou.get('pillar', '')}（地支{fu_tou.get('branch', '')}）定{fu_tou.get('yuan', '')}，"
            f"排{dun['text']}"
        )

    pillars = facts.get("pillars") or {}
    if pillars:
        detail = "、".join(
            f"{POSITION_LABELS[key]}为{pillars[key]['text']}"
            for key in ("year", "month", "day", "hour")
            if pillars.get(key)
        )
        emit(f"四柱：{detail}")

    palaces = facts.get("palaces") or []
    if palaces:
        earth = "、".join(f"{item['name']}{item['earth_stem']}" for item in palaces)
        emit(f"地盘三奇六仪：{earth}")

    zhifu = facts.get("zhifu") or {}
    if zhifu.get("star"):
        emit(
            f"值符为{zhifu['star']}，本位在{zhifu.get('palace_name', '')}，"
            f"随时干落{zhifu.get('landing_name', '')}"
        )
    zhishi = facts.get("zhishi") or {}
    if zhishi.get("door"):
        emit(
            f"值使为{zhishi['door']}，按旬内第 {zhishi.get('steps')} 步在八宫环上移动，"
            f"落{zhishi.get('palace_name', '')}"
        )

    kong = facts.get("xun_kong") or {}
    ma_star = facts.get("ma_star") or {}
    if kong.get("xun_head"):
        emit(
            f"时柱属{kong['xun_head']}旬，旬空为{'、'.join(kong.get('branches') or [])}；"
            f"马星在{ma_star.get('branch', '')}，对应{ma_star.get('palace_name', '')}"
        )

    observations.extend(_rule_observations(rules))
    return observations


def _qimen_summary(facts: dict[str, Any], rules: list[dict[str, Any]]) -> str:
    dun = facts.get("dun") or {}
    zhifu = facts.get("zhifu") or {}
    zhishi = facts.get("zhishi") or {}
    return (
        f"本盘为{dun.get('text', '')}（{dun.get('yuan', '')}），值符{zhifu.get('star', '')}、"
        f"值使{zhishi.get('door', '')}，共标记 {len(rules)} 条结构规则。"
        "以下仅陈述盘面事实与可查证的典籍条目，不作吉凶推断，也不取用神。"
    )


def _generic_observations(facts: dict[str, Any], rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _rule_observations(rules)


def _generic_summary(facts: dict[str, Any], rules: list[dict[str, Any]]) -> str:
    return f"本盘共标记 {len(rules)} 条结构规则。以下仅陈述盘面事实，不作吉凶推断。"


def _reflections(facts: dict[str, Any], domain: str) -> list[str]:
    reflections: list[str] = []
    if domain == "ziwei":
        dayun = facts.get("dayun") or []
        if isinstance(dayun, list) and dayun:
            first = dayun[0]
            reflections.append(
                f"大限按{facts.get('dayun_forward') and '顺行' or '逆行'}排布，"
                f"第一限 {first.get('start_age')}–{first.get('end_age')} 岁，"
                "可用于对照人生阶段的公开经历做自我复核。"
            )
    else:
        dayun = facts.get("dayun") or {}
        if isinstance(dayun, dict) and dayun.get("computed"):
            reflections.append(
                f"大运{'顺排' if dayun.get('forward') else '逆排'}，"
                f"起运约 {dayun.get('start_age', {}).get('text', '')}，"
                "可用于对照人生阶段的公开经历做自我复核。"
            )
    reflections.append("把盘面当作自我观察的提纲：先记录可验证的行为倾向，再判断解释是否成立。")
    reflections.append("遇到健康、法律、投资类具体决策时，请咨询相应专业人士，本报告不提供结论。")
    return reflections


_OBSERVERS = {
    "bazi": _bazi_observations,
    "ziwei": _ziwei_observations,
    "liuyao": _liuyao_observations,
    "qimen": _qimen_observations,
}
_SUMMARIES = {
    "bazi": _bazi_summary,
    "ziwei": _ziwei_summary,
    "liuyao": _liuyao_summary,
    "qimen": _qimen_summary,
}


class MockProvider(LLMProvider):
    name = "mock"
    model = "mock-deterministic-v1"

    def _followup(self, request: LLMRequest) -> LLMResponse:
        """追问的确定性回答：只复述盘面事实，引用第一枚可用片段。

        它不会真的回答「为什么」——mock 的存在意义是让接口、校验链与前端
        可以离线跑通，而不是伪装成会推理的模型。
        """
        ctx = request.context
        facts = ctx.get("chart_facts", {})
        domain = ctx.get("domain", "bazi")
        chunks = [item for item in (ctx.get("chunks") or []) if item.get("chunk_id") is not None]
        observations = _OBSERVERS.get(domain, _generic_observations)(facts, [])
        points = [item["fact"] for item in observations[:6] if item.get("fact")]
        lead = points[0] if points else "本盘暂无可复述的盘面事实。"
        payload = {
            "answer": "按本盘盘面事实，可核对的内容如下：" + lead,
            "points": points[1:6],
            "citations": [chunks[0]["chunk_id"]] if chunks else [],
            "uncertainties": (
                []
                if chunks
                else ["本次追问未命中已审核的知识库条目，只复述盘面事实。"]
            ) + ["演示模型不做推理，本条只用于接口联调。"],
            "safety_note": SAFETY_NOTE,
        }
        return LLMResponse(payload=payload, provider=self.name, model=self.model)

    def generate_json(self, request: LLMRequest) -> LLMResponse:
        if request.task == "followup":
            return self._followup(request)
        ctx = request.context
        facts = ctx.get("chart_facts", {})
        rules = ctx.get("triggered_rules", [])
        chunks = ctx.get("chunks", [])
        depth = ctx.get("depth", "brief")
        domain = ctx.get("domain", "bazi")

        observer = _OBSERVERS.get(domain, _generic_observations)
        observations = observer(facts, rules)
        summary = _SUMMARIES.get(domain, _generic_summary)(facts, rules)

        interpretations: list[dict[str, Any]] = []
        usable = [chunk for chunk in chunks if chunk.get("chunk_id") is not None][:6]
        for chunk in usable:
            interpretations.append(
                {
                    "claim": (
                        f"{chunk.get('title') or chunk.get('citation_label', '知识库条目')}："
                        f"{chunk.get('snippet', '')}"
                    ),
                    "citation_ids": [chunk["chunk_id"]],
                    "school_note": chunk.get("location") or None,
                }
            )

        uncertainties: list[str] = []
        for warning in ctx.get("warnings", []):
            uncertainties.append(str(warning))
        if not usable:
            uncertainties.append(
                "本次检索未命中已审核的知识库条目，因此不给出传统解释，仅有盘面事实。"
            )
        if depth == "brief":
            uncertainties.append("当前为简版解读，未展开大运与流年层级的讨论。")
        if domain == "ziwei":
            uncertainties.append(
                "紫微斗数各派在庚干四化、闰月取法、子时换日上做法不同，本报告只按三合派单一口径输出。"
            )
        elif domain == "liuyao":
            uncertainties.append(
                "六爻各派在六亲对照、伏神、旺衰与用神取法上做法不同，本报告只输出京房纳甲的盘面事实，不做旺衰与应期推断。"
            )
        elif domain == "qimen":
            uncertainties.append(
                "奇门各派在置闰与拆补、转盘与飞盘、中宫寄宫上做法不同，本报告只输出时家转盘拆补法的盘面事实，"
                "不取用神、不判旺衰、不择日、不给应期。"
            )
        else:
            uncertainties.append(
                "不同流派对合冲刑害的优先级、藏干权重与换日口径存在差异，本报告按已声明的口径输出。"
            )

        reflections = _reflections(facts, domain)

        payload = {
            "summary": summary,
            "observations": observations,
            "traditional_interpretations": interpretations,
            "practical_reflections": reflections,
            "uncertainties": uncertainties,
            "citations": [chunk["chunk_id"] for chunk in usable],
            "safety_note": SAFETY_NOTE,
        }
        return LLMResponse(
            payload=payload,
            provider=self.name,
            model=self.model,
            input_tokens=0,
            output_tokens=0,
            raw_text="",
        )


def _cli() -> None:  # pragma: no cover - 手工调试入口
    import json

    demo = MockProvider().generate_json(
        LLMRequest(
            task="bazi.overview",
            system_prompt="",
            user_prompt="",
            context={"chart_facts": {"pillars": {}, "day_master": {}}, "triggered_rules": [], "chunks": []},
        )
    )
    print(json.dumps(demo.payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":  # pragma: no cover
    _cli()
