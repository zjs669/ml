"""报告校验链（计划 D11）。

顺序固定，任一步出现 fatal 就交给上层重试/降级：
1. pydantic Schema（7 个字段齐全、长度受限、禁止多余字段）
2. `citations` 与各处 `citation_ids` 必须真的来自本次检索结果
3. `observations[].rule_ids` 必须是本次真实触发的规则
4. 盘面一致性：按 domain 分派——四柱扫干支、紫微扫星曜与宫位、
   六爻扫卦名与爻位、奇门扫九宫与门星神（防"模型改写盘面"）
5. 禁词与绝对化表述扫描（防宿命论与专业越界）——四个术数共用
6. 软问题：无引用的解释、空解释、缺安全说明
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from pydantic import ValidationError

from app.schemas.report import FollowupPayload, ReportPayload

GANZHI_PAIR = re.compile(r"[甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥]")

# 紫微：十四主星在每张盘里都全部存在，只查「这个星在不在盘上」没有意义，
# 真正要防的是模型把星曜安错宫（“紫微坐命”但本盘紫微在迁移）。
# 因此只校验「星 + 动词 + 宫」这一种显式断言，宁可漏报也不误伤。
ZIWEI_PLACEMENT = re.compile(
    r"(紫微|天机|太阳|武曲|天同|廉贞|天府|太阴|贪狼|巨门|天相|天梁|七杀|破军)"
    r"(?:星)?(?:坐守|坐|守|入|临|居|在|落)"
    r"(命宫|兄弟|夫妻|子女|财帛|疾厄|迁移|交友|奴仆|官禄|事业|田宅|福德|父母)"
)
PALACE_ALIAS = {"奴仆": "交友", "事业": "官禄"}
# 六爻/奇门的卦名、门名是专有名词，用专有名词表比对而不是模糊正则：
# 「上卦」「下卦」「八纯卦」这类普通表述不能当成卦名去查，否则会大面积误伤。
LIUYAO_TRIGRAM_HINTS = ("乾", "坤", "震", "巽", "坎", "离", "艮", "兑")
QIMEN_DOORS = ("休门", "生门", "伤门", "杜门", "景门", "死门", "惊门", "开门")
QIMEN_STARS = ("天蓬", "天任", "天冲", "天辅", "天英", "天芮", "天柱", "天心", "天禽")
# 只认「X落Y宫」「X临Y宫」这类显式断言；「天蓬本位在坎一宫」属于本宫描述，不算落宫，不参与比对。
# 天禽必须入选：它寄坤二随天芮同行，是奇门正文里出现频率最高的星之一，
# 不查它等于把最容易被写错的断言放过去（比对基准取它实际所在宫）。
QIMEN_PALACE_NAME = r"(?:坎一|坤二|震三|巽四|乾六|兑七|艮八|离九)宫"
QIMEN_MOVE = re.compile(
    r"(" + "|".join(QIMEN_DOORS + QIMEN_STARS) + r")" + r"(?:落|临)" + r"(" + QIMEN_PALACE_NAME + r")"
)

ABSOLUTE_TERMS = (
    "必定",
    "一定会",
    "必然会",
    "注定",
    "百分之百",
    "100%",
    "绝对会",
    "铁定",
    "毫无疑问会",
)
DISASTER_TERMS = (
    "血光之灾",
    "绝症",
    "必死",
    "短命",
    "克死",
    "家破人亡",
    "离婚收场",
    "必定破财",
)
PROFESSIONAL_TERMS = (
    "建议停药",
    "可以停药",
    "确诊为",
    "建议买入",
    "建议卖出",
    "满仓",
    "保证收益",
    "保证盈利",
    "官司必输",
    "必然胜诉",
)

FATAL = "fatal"
WARN = "warn"


@dataclass
class Issue:
    code: str
    severity: str
    detail: str
    path: str | None = None


@dataclass
class ValidationResult:
    ok: bool
    issues: list[Issue] = field(default_factory=list)
    payload: ReportPayload | None = None

    @property
    def fatal_codes(self) -> list[str]:
        return [issue.code for issue in self.issues if issue.severity == FATAL]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "fatal_codes": self.fatal_codes,
            "issues": [asdict(issue) for issue in self.issues],
        }


def _allowed_pillars(chart_facts: dict[str, Any]) -> set[str]:
    allowed: set[str] = set()
    for pillar in chart_facts.get("pillars", {}).values():
        text = pillar.get("text")
        if text:
            allowed.add(text)
    for item in chart_facts.get("dayun", {}).get("list", []) or []:
        if item.get("pillar"):
            allowed.add(item["pillar"])
    # 奇门：旬首与符头都是盘面事实，允许在正文中出现（否则「甲子旬」「己巳日」会被误判为编造干支）
    xun_head = (chart_facts.get("xun_kong") or {}).get("xun_head")
    if xun_head:
        allowed.add(xun_head)
    fu_tou = (chart_facts.get("fu_tou") or {}).get("pillar")
    if fu_tou:
        allowed.add(fu_tou)
    return allowed


def _allowed_vocabulary(chart_facts: dict[str, Any]) -> set[str]:
    """把整个 chart_facts 里出现的字符串收成词表，供非四柱术数比对。"""
    vocab: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for value in node.values():
                walk(value)
        elif isinstance(node, (list, tuple)):
            for value in node:
                walk(value)
        elif isinstance(node, str):
            vocab.add(node)

    walk(chart_facts)
    return vocab


FactTexts = list[tuple[str, str]]


def _check_bazi_facts(chart_facts: dict[str, Any], texts: FactTexts, issues: list[Issue]) -> None:
    allowed = _allowed_pillars(chart_facts)
    for path, text in texts:
        _scan_ganzhi(text, allowed, path, issues)


def _check_ziwei_facts(chart_facts: dict[str, Any], texts: FactTexts, issues: list[Issue]) -> None:
    """校验「星坐宫」类显式断言：星曜必须在正文声称的那个宫里。"""
    star_palaces: dict[str, set[str]] = {}
    for palace in chart_facts.get("palaces", []) or []:
        name = palace.get("name")
        for star in palace.get("stars", []) or []:
            star_palaces.setdefault(star, set()).add(name)
    if not star_palaces:  # 盘面数据缺失时不做断言，交给其他校验
        return
    for path, text in texts:
        for star, palace in ZIWEI_PLACEMENT.findall(text):
            target = PALACE_ALIAS.get(palace, palace)
            actual = star_palaces.get(star)
            if actual and target not in actual:
                issues.append(
                    Issue(
                        code="fact_mismatch",
                        severity=FATAL,
                        detail=(
                            f"正文称「{star}在{target}」，但本盘{star}落"
                            f"{'、'.join(sorted(actual))}，疑似模型改写盘面"
                        ),
                        path=path,
                    )
                )


def _check_liuyao_facts(chart_facts: dict[str, Any], texts: FactTexts, issues: list[Issue]) -> None:
    """校验卦名与八卦名：正文提到的卦必须是本盘上真正出现的卦。"""
    from app.domains.liuyao.hexagrams import NAME_TO_INFO  # 避免导入期循环依赖

    vocab = _allowed_vocabulary(chart_facts)
    present = {name for name in NAME_TO_INFO if name in vocab}
    palaces = {
        (chart_facts.get(key) or {}).get("palace")
        for key in ("original", "changed")
        if (chart_facts.get(key) or {}).get("palace")
    }
    for path, text in texts:
        for name in NAME_TO_INFO:
            if name in text and name not in present:
                issues.append(
                    Issue(
                        code="fact_mismatch",
                        severity=FATAL,
                        detail=f"正文提到本盘未出现的卦「{name}」，疑似模型改写盘面",
                        path=path,
                    )
                )
        # 只查「X宫」这种显式断言，避免把「乾坤」一类普通用词当成宫位
        for palace in LIUYAO_TRIGRAM_HINTS:
            if f"{palace}宫" in text and palace not in palaces:
                issues.append(
                    Issue(
                        code="fact_mismatch",
                        severity=FATAL,
                        detail=f"正文称「{palace}宫」，但本盘卦宫为{'、'.join(sorted(palaces)) or '未记录'}",
                        path=path,
                    )
                )


def _check_qimen_facts(chart_facts: dict[str, Any], texts: FactTexts, issues: list[Issue]) -> None:
    """奇门：干支必须与四柱一致；星、门若声明了落宫，必须与盘面相符。"""
    _check_bazi_facts(chart_facts, texts, issues)
    palaces = chart_facts.get("palaces") or []
    if not palaces:
        return
    door_palaces = {item["door"]: item["name"] for item in palaces if item.get("door")}
    star_palaces: dict[str, str] = {}
    for item in palaces:
        if item.get("is_center"):
            continue
        for name in (item.get("star"), item.get("extra_star")):
            if name:
                star_palaces.setdefault(name, item["name"])
    actual = {**door_palaces, **star_palaces}
    for path, text in texts:
        for name, palace in QIMEN_MOVE.findall(text):
            real = actual.get(name)
            if real and real != palace:
                issues.append(
                    Issue(
                        code="fact_mismatch",
                        severity=FATAL,
                        detail=f"正文称「{name}落{palace}」，但本盘{name}落{real}，疑似模型改写盘面",
                        path=path,
                    )
                )


DOMAIN_FACT_CHECKS: dict[str, Any] = {
    "bazi": _check_bazi_facts,
    "ziwei": _check_ziwei_facts,
    "liuyao": _check_liuyao_facts,
    "qimen": _check_qimen_facts,
}


def _scan_ganzhi(text: str, allowed: set[str], path: str, issues: list[Issue]) -> None:
    for match in GANZHI_PAIR.findall(text):
        if match not in allowed:
            issues.append(
                Issue(
                    code="fact_mismatch",
                    severity=FATAL,
                    detail=f"正文出现盘面中不存在的干支「{match}」，疑似模型改写事实",
                    path=path,
                )
            )


def _scan_terms(text: str, path: str, issues: list[Issue]) -> None:
    for term in ABSOLUTE_TERMS:
        if term in text:
            issues.append(
                Issue(
                    code="forbidden_wording",
                    severity=FATAL,
                    detail=f"出现绝对化表述「{term}」，违反不可作宿命断言的要求",
                    path=path,
                )
            )
    for term in DISASTER_TERMS:
        if term in text:
            issues.append(
                Issue(
                    code="forbidden_wording",
                    severity=FATAL,
                    detail=f"出现灾祸类断言「{term}」",
                    path=path,
                )
            )
    for term in PROFESSIONAL_TERMS:
        if term in text:
            issues.append(
                Issue(
                    code="professional_overreach",
                    severity=FATAL,
                    detail=f"出现专业越界表述「{term}」（医疗/投资/法律结论）",
                    path=path,
                )
            )


def validate(
    raw: dict[str, Any],
    *,
    triggered_rule_ids: set[str],
    chunk_ids: set[int],
    chart_facts: dict[str, Any],
    domain: str = "bazi",
) -> ValidationResult:
    issues: list[Issue] = []

    # 1. Schema
    try:
        payload = ReportPayload.model_validate(raw)
    except ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(str(part) for part in err['loc'])}: {err['msg']}" for err in exc.errors()[:6]
        )
        return ValidationResult(
            ok=False,
            issues=[Issue(code="schema_invalid", severity=FATAL, detail=details)],
            payload=None,
        )

    # 2. 引用必须真实存在
    cited = set(payload.citations)
    for observation in payload.observations:
        cited.update(observation.citation_ids)
    for item in payload.traditional_interpretations:
        cited.update(item.citation_ids)
    unknown = sorted(cited - chunk_ids)
    if unknown:
        issues.append(
            Issue(
                code="citation_unknown",
                severity=FATAL,
                detail=f"引用了本次检索结果中不存在的 chunk_id：{unknown}",
                path="citations",
            )
        )

    # 3. rule_ids 必须是真实触发的规则
    used_rules: set[str] = set()
    for observation in payload.observations:
        used_rules.update(observation.rule_ids)
    unknown_rules = sorted(used_rules - triggered_rule_ids)
    if unknown_rules:
        issues.append(
            Issue(
                code="rule_unknown",
                severity=FATAL,
                detail=f"引用了未触发的规则：{unknown_rules}",
                path="observations",
            )
        )

    # 4. 盘面一致性：按 domain 分派（bazi 扫干支，其他术数扫各自的专有名词）
    fact_texts: FactTexts = [("summary", payload.summary)]
    for index, observation in enumerate(payload.observations):
        fact_texts.append((f"observations[{index}].fact", observation.fact))
    for index, item in enumerate(payload.traditional_interpretations):
        if not item.citation_ids:
            # 无引用的解释等同于模型自述，必须与盘面一致
            fact_texts.append((f"traditional_interpretations[{index}].claim", item.claim))
    for index, text in enumerate(payload.practical_reflections):
        fact_texts.append((f"practical_reflections[{index}]", text))
    for index, text in enumerate(payload.uncertainties):
        fact_texts.append((f"uncertainties[{index}]", text))

    check = DOMAIN_FACT_CHECKS.get(domain)
    if check is not None:
        check(chart_facts, fact_texts, issues)

    # 5. 禁词扫描
    _scan_terms(payload.summary, "summary", issues)
    _scan_terms(payload.safety_note, "safety_note", issues)
    for index, observation in enumerate(payload.observations):
        _scan_terms(observation.fact, f"observations[{index}].fact", issues)
    for index, item in enumerate(payload.traditional_interpretations):
        _scan_terms(item.claim, f"traditional_interpretations[{index}].claim", issues)
    for index, text in enumerate(payload.practical_reflections):
        _scan_terms(text, f"practical_reflections[{index}]", issues)

    # 6. 软问题
    uncited = [
        index for index, item in enumerate(payload.traditional_interpretations) if not item.citation_ids
    ]
    if uncited:
        issues.append(
            Issue(
                code="uncited_claim",
                severity=WARN,
                detail=f"以下解释缺少知识库引用，已并入不确定项：{uncited}",
                path="traditional_interpretations",
            )
        )
    if not payload.traditional_interpretations:
        issues.append(
            Issue(
                code="knowledge_insufficient",
                severity=WARN,
                detail="没有可用的传统解释（知识库未命中），报告中已明示依据不足",
                path="traditional_interpretations",
            )
        )
    if not payload.observations:
        issues.append(
            Issue(
                code="no_observations",
                severity=WARN,
                detail="报告未复述任何盘面事实",
                path="observations",
            )
        )

    ok = not any(issue.severity == FATAL for issue in issues)
    return ValidationResult(ok=ok, issues=issues, payload=payload)


@dataclass
class FollowupValidation:
    ok: bool
    issues: list[Issue] = field(default_factory=list)
    payload: FollowupPayload | None = None

    @property
    def fatal_codes(self) -> list[str]:
        return [issue.code for issue in self.issues if issue.severity == FATAL]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "fatal_codes": self.fatal_codes,
            "issues": [asdict(issue) for issue in self.issues],
        }


def validate_followup(
    raw: dict[str, Any],
    *,
    chunk_ids: set[int],
    chart_facts: dict[str, Any],
    domain: str = "bazi",
) -> FollowupValidation:
    """追问校验：Schema → 引用 → 盘面 → 禁词，与报告同一套顺序，但更窄。"""
    issues: list[Issue] = []
    try:
        payload = FollowupPayload.model_validate(raw)
    except ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(str(part) for part in err['loc'])}: {err['msg']}" for err in exc.errors()[:6]
        )
        return FollowupValidation(
            ok=False,
            issues=[Issue(code="schema_invalid", severity=FATAL, detail=details)],
        )

    unknown = sorted(set(payload.citations) - chunk_ids)
    if unknown:
        issues.append(
            Issue(
                code="citation_unknown",
                severity=FATAL,
                detail=f"引用了原报告未检索到的 chunk_id：{unknown}",
                path="citations",
            )
        )

    fact_texts: FactTexts = [("answer", payload.answer)]
    for index, text in enumerate(payload.points):
        fact_texts.append((f"points[{index}]", text))

    check = DOMAIN_FACT_CHECKS.get(domain)
    if check is not None:
        check(chart_facts, fact_texts, issues)

    _scan_terms(payload.answer, "answer", issues)
    for index, text in enumerate(payload.points):
        _scan_terms(text, f"points[{index}]", issues)
    _scan_terms(payload.safety_note, "safety_note", issues)

    if not payload.citations:
        issues.append(
            Issue(
                code="uncited_answer",
                severity=WARN,
                detail="追问回答未引用任何知识片段，应视为复述盘面而非有据解释",
                path="citations",
            )
        )

    ok = not any(issue.severity == FATAL for issue in issues)
    return FollowupValidation(ok=ok, issues=issues, payload=payload)
