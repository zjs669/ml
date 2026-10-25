"""从错例集蒸馏技能卡（只写草稿，绝不自动转正）。

用法：
    python -m scripts.distill_skills                    # 读默认 attempts.jsonl
    python -m scripts.distill_skills --dry-run           # 只打印分组，不调模型
    python -m scripts.distill_skills --min-samples 2 --domain bazi

产物：`app/domains/skills/distilled/_draft/<domain>.<signature>.md`，`status: draft`。

为什么必须人工转正：
模型总结出来的「经验」如果直接生效，就等于让模型自己给自己定规则，
一旦总结错（例如把「三合」写成「三会」），后续每一份报告都会沿用这个错误。
所以脚本只负责把「同一类错误长什么样」摆到人面前，转正由人决定。
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from app.domains.llm.base import LLMRequest, LLMUnavailable
from app.domains.llm.openai_compatible import OpenAICompatibleProvider, get_provider
from app.domains.skills import skillfile

BACKEND_DIR = Path(__file__).resolve().parents[1]
DEFAULT_ATTEMPTS = BACKEND_DIR / "data" / "bench" / "attempts.jsonl"

SYSTEM = "你是命理研习助教。你只总结「检查顺序与常见错误」，绝不创造新的命理规则。"

PROMPT = """下面是同一类做错的题目样本（题目 + 正确答案 + 模型答案 + 错误原因）：

{samples}

请总结这一类题的**审题与自查顺序**，输出一个 JSON：
{{"title": "不超过 20 字的标题",
  "topics": ["overview"],
  "triggers": ["题目里常出现的关键词，最多 8 个"],
  "body": "分条写，每条一句；只写『先看什么、再看什么、最容易错在哪』，
           不得出现任何具体的星曜组合结论，不得编造规则，不得写吉凶判断。"}}

硬要求：
1. 只写方法与检查顺序，不写「某星在某宫就代表什么」这类结论；
2. 不引用任何书籍页码或知识库编号；
3. body 不超过 12 行。
"""


def _load(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(f"错例集不存在：{path}（先跑 scripts.bench_eval）")
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _signature(record: dict[str, Any]) -> str:
    error = (record.get("error") or "").strip()
    if not error:
        return "wrong_answer"
    # 把长错误句压成稳定标签，否则同一类错误会裂成很多组
    if "截断" in error:
        return "output_truncated"
    if error == "answer_not_parsed":
        return "answer_not_parsed"
    return re.sub(r"[^A-Za-z0-9_]+", "_", error)[:24].strip("_") or "other_error"


def _aggregate(rows: list[dict[str, Any]], *, domain: str | None) -> list[dict[str, Any]]:
    """按题号聚合错题：同一道题反复错，才值得写成技能卡。"""
    buckets: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row.get("correct"):
            continue
        case_id = str(row.get("id") or "").strip()
        if not case_id:
            continue
        row_domain = str(row.get("domain") or "bazi")
        if domain and row_domain != domain:
            continue
        item = buckets.setdefault(
            case_id,
            {
                "id": case_id,
                "domain": row_domain,
                "question": str(row.get("question") or ""),
                "expected": str(row.get("expected") or ""),
                "wrong": 0,
                "error": "",
                "got": "",
            },
        )
        item["wrong"] += 1
        item["error"] = str(row.get("error") or "")
        item["got"] = str(row.get("got") or "")
    return list(buckets.values())


def _groups(
    rows: list[dict[str, Any]], *, domain: str | None
) -> dict[tuple[str, str], list[dict[str, Any]]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for item in _aggregate(rows, domain=domain):
        grouped[(item["domain"], _signature(item))].append(item)
    return grouped


def _samples(rows: list[dict[str, Any]], limit: int = 8) -> str:
    lines: list[str] = []
    for index, row in enumerate(rows[:limit], 1):
        lines.append(
            f"{index}. 题目：{row.get('question', '')[:200]}\n"
            f"   正确答案：{row.get('expected', '')}\n"
            f"   模型答案：{row.get('got', '') or '（未作答）'}\n"
            f"   累计答错：{row.get('wrong', 1)} 次；最近错误：{row.get('error', '') or '选错'}"
        )
    return "\n".join(lines)


def _write_draft(domain: str, signature: str, payload: dict[str, Any], rows: list[dict[str, Any]]) -> Path:
    draft_dir = skillfile.SKILLS_DIR / "_draft"
    draft_dir.mkdir(parents=True, exist_ok=True)
    triggers = payload.get("triggers") or []
    if isinstance(triggers, str):
        triggers = [item.strip() for item in triggers.split(",") if item.strip()]
    topics = payload.get("topics") or ["overview"]
    if isinstance(topics, str):
        topics = [item.strip() for item in topics.split(",") if item.strip()]
    body = str(payload.get("body") or "").strip() or "（模型未给出正文，请人工补写）"
    path = draft_dir / f"{domain}.{signature}.md"
    text = (
        "---\n"
        f"id: draft.{domain}.{signature}.v1\n"
        f"domain: {domain}\n"
        f"title: {str(payload.get('title') or signature)[:40]}\n"
        f"topics: [{', '.join(str(item) for item in topics)}]\n"
        f"triggers: [{', '.join(str(item) for item in triggers)}]\n"
        "priority: 40\n"
        "status: draft\n"
        "always: false\n"
        "max_chars: 1800\n"
        f"source: 蒸馏自 {len(rows)} 道错题（共答错 {sum(int(item.get('wrong', 1)) for item in rows)} 次，待人工复核）\n"
        "updated: 2026-10-25\n"
        "---\n\n"
        f"{body}\n\n"
        "<!-- 复核要点：1) 有没有编造规则 2) 触发词是否过宽 3) 是否只讲顺序不讲结论 -->\n"
    )
    path.write_text(text, encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="从错例集蒸馏技能卡草稿")
    parser.add_argument("--attempts", default=str(DEFAULT_ATTEMPTS))
    parser.add_argument("--min-samples", type=int, default=3)
    parser.add_argument("--min-wrong", type=int, default=0, help="该组累计答错次数下限，默认沿用 min-samples")
    parser.add_argument("--limit-groups", type=int, default=6)
    parser.add_argument("--domain", default="")
    parser.add_argument("--model", default="", help="覆盖 LLM_MODEL，建议用输出稳定的模型")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    rows = _load(Path(args.attempts))
    groups = _groups(rows, domain=args.domain or None)
    ranked = sorted(
        groups.items(), key=lambda item: sum(int(x.get("wrong", 1)) for x in item[1]), reverse=True
    )
    threshold = args.min_wrong or args.min_samples

    print(
        f"错题 {sum(len(items) for _, items in ranked)} 道，聚成 {len(groups)} 组"
        f"（阈值：至少答错 {threshold} 次）"
    )
    eligible = [
        (key, items)
        for key, items in ranked
        if sum(int(item.get("wrong", 1)) for item in items) >= threshold
    ][: args.limit_groups]
    for (domain, signature), items in eligible:
        total_wrong = sum(int(item.get("wrong", 1)) for item in items)
        print(f" - {domain:6s} {signature:24s} {len(items)} 道 / 答错 {total_wrong} 次")

    if args.dry_run:
        print("dry-run：不调用模型，不写文件。")
        return 0
    if not eligible:
        print("没有达到阈值的组，先多跑一些题。")
        return 0

    try:
        provider = OpenAICompatibleProvider(model=args.model) if args.model else get_provider()
    except LLMUnavailable as exc:
        print(f"模型不可用：{exc}")
        return 1

    written: list[Path] = []
    for (domain, signature), items in eligible:
        try:
            response = provider.generate_json(
                LLMRequest(
                    task="distill.skill",
                    system_prompt=SYSTEM,
                    user_prompt=PROMPT.format(samples=_samples(items)),
                    context={"domain": domain},
                    max_output_tokens=900,
                )
            )
        except LLMUnavailable as exc:
            print(f"跳过 {domain}/{signature}：{exc}")
            continue
        written.append(_write_draft(domain, signature, response.payload, items))

    for path in written:
        print(f"草稿：{path}")
    print(
        "\n下一步：人工复核 _draft/ 里的内容，确认没有编造规则后，"
        "把 status 改成 approved 并移出 _draft/ 目录。脚本不会自动转正。"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
