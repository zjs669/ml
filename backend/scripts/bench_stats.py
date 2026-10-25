"""题库复盘：同一道题错了几次、哪一类错误最多、题库本身缺了多少答案。

为什么单独一个脚本：
`bench_eval` 只跑一轮，看到的是一张快照；蒸馏需要的是**跨轮次**证据——
同一道题错 3 次，才值得为它写一张技能卡；只错 1 次可能只是模型抖动。
所以评测默认把每次作答**追加**进 `attempts.jsonl`，本脚本负责把它压成可读的复盘表。

用法：
    python -m scripts.bench_stats                     # 读默认 attempts，写 docs/题库复盘.md
    python -m scripts.bench_stats --min-wrong 2      # 只看错 2 次以上的题
    python -m scripts.bench_stats --source mingli_bench
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from scripts.bench.datasets import read_jsonl

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
DEFAULT_ATTEMPTS = BACKEND_DIR / "data" / "bench" / "attempts.jsonl"
DEFAULT_OUTPUT = REPO_ROOT / "docs" / "题库复盘.md"
BENCH_DIR = BACKEND_DIR / "data" / "bench"


def _blank_bucket() -> dict[str, Any]:
    return {
        "attempts": 0,
        "wrong": 0,
        "unanswered": 0,
        "last_error": "",
        "last_got": "",
        "expected": "",
        "domain": "",
        "question": "",
        "sources": set(),
    }


def aggregate(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """按题号聚合。`unanswered` 指模型没给出可解析答案（got 为空）。"""
    buckets: dict[str, dict[str, Any]] = defaultdict(_blank_bucket)
    for row in records:
        case_id = str(row.get("id") or "").strip()
        if not case_id:
            continue
        bucket = buckets[case_id]
        bucket["attempts"] += 1
        got = str(row.get("got") or "")
        error = str(row.get("error") or "")
        correct = bool(row.get("correct"))
        if not correct:
            bucket["wrong"] += 1
        if not got:
            bucket["unanswered"] += 1
        bucket["last_error"] = error or ("选错" if not correct else "")
        bucket["last_got"] = got
        bucket["expected"] = str(row.get("expected") or bucket["expected"])
        bucket["domain"] = str(row.get("domain") or bucket["domain"])
        bucket["question"] = str(row.get("question") or bucket["question"])
        if row.get("source"):
            bucket["sources"].add(str(row["source"]))
    return dict(buckets)


def _error_signature(record: dict[str, Any]) -> str:
    error = str(record.get("error") or "").strip()
    if error:
        return error[:60]
    return "选错" if not record.get("correct") else "正确"


def bank_gaps() -> list[dict[str, Any]]:
    """读各题库评测时落下的 last_load.json，统计「题库本身缺答案/缺字段」的条数。"""
    gaps: list[dict[str, Any]] = []
    if not BENCH_DIR.is_dir():
        return gaps
    for path in sorted(BENCH_DIR.glob("*/last_load.json")):
        try:
            import json

            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # 解析失败不影响主流程
            continue
        gaps.append(payload)
    return gaps


def render(
    *,
    records: list[dict[str, Any]],
    buckets: dict[str, dict[str, Any]],
    gaps: list[dict[str, Any]],
    min_wrong: int,
    top: int,
) -> str:
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    total_attempts = len(records)
    wrong_attempts = sum(1 for row in records if not row.get("correct"))
    unanswered = sum(1 for row in records if not str(row.get("got") or ""))
    runs = len({row.get("run_id") for row in records if row.get("run_id")})

    lines = [
        "# 题库复盘",
        "",
        f"> 由 `python -m scripts.bench_stats` 生成（{stamp}）。评测记录默认追加，本表跨轮次累计。",
        "",
        "## 1. 总览",
        "",
        "| 指标 | 值 |",
        "|---|---|",
        f"| 评测轮次 | {runs} |",
        f"| 作答总次数 | {total_attempts} |",
        f"| 涉及题目 | {len(buckets)} |",
        f"| 错误次数 | {wrong_attempts}（{wrong_attempts / total_attempts * 100:.1f}%） |" if total_attempts else "| 错误次数 | 0 |",
        f"| 未作答次数（got 为空） | {unanswered} |",
        f"| 题库缺答案/缺字段被跳过 | {sum(int(g.get('skipped') or 0) for g in gaps)} |",
        "",
    ]

    # 按题库来源
    by_source: dict[str, dict[str, int]] = defaultdict(lambda: {"attempts": 0, "wrong": 0, "questions": 0})
    for bucket in buckets.values():
        for source in bucket["sources"] or {"（未知）"}:
            by_source[source]["attempts"] += bucket["attempts"]
            by_source[source]["wrong"] += bucket["wrong"]
            by_source[source]["questions"] += 1
    lines.extend(["## 2. 按题库", "", "| 题库 | 题目数 | 作答 | 错误 | 错误率 |", "|---|---|---|---|---|"])
    if not by_source:
        lines.append("| — | — | — | — | — |")
    for source, stat in sorted(by_source.items()):
        rate = stat["wrong"] / stat["attempts"] * 100 if stat["attempts"] else 0
        lines.append(
            f"| {source} | {stat['questions']} | {stat['attempts']} | {stat['wrong']} | {rate:.1f}% |"
        )
    lines.append("")

    # 错误类型
    by_error: dict[str, int] = defaultdict(int)
    for row in records:
        if row.get("correct"):
            continue
        by_error[_error_signature(row)] += 1
    lines.extend(["## 3. 错误类型", "", "| 类型 | 次数 |", "|---|---|"])
    if not by_error:
        lines.append("| — | — |")
    for signature, count in sorted(by_error.items(), key=lambda item: item[1], reverse=True)[:15]:
        lines.append(f"| {signature.replace('|', '｜')} | {count} |")
    lines.append("")

    # 错题清单
    ranked = sorted(
        (item for item in buckets.items() if item[1]["wrong"] >= min_wrong),
        key=lambda item: (item[1]["wrong"], item[1]["unanswered"]),
        reverse=True,
    )[:top]
    lines.extend(
        [
            f"## 4. 错题清单（按错误次数降序，阈值 {min_wrong} 次，前 {top} 条）",
            "",
            "> 「错/答」是错误次数 / 作答次数。同一道题反复错，才值得为它写技能卡。",
            "",
            "| 题号 | 术数 | 错/答 | 最近答案 | 正确答案 | 最近错误 | 题干 |",
            "|---|---|---|---|---|---|---|",
        ]
    )
    if not ranked:
        lines.append("| — | — | — | — | — | — | — |")
    for case_id, bucket in ranked:
        question = bucket["question"].replace("|", "｜")[:46]
        error = (bucket["last_error"] or "—").replace("|", "｜")[:30]
        lines.append(
            f"| `{case_id}` | {bucket['domain']} | {bucket['wrong']}/{bucket['attempts']} | "
            f"{bucket['last_got'] or '未作答'} | {bucket['expected']} | {error} | {question} |"
        )
    lines.append("")

    # 题库缺口
    lines.extend(["## 5. 题库缺口（评测时被跳过的题目）", ""])
    if not gaps:
        lines.append("还没有 `last_load.json`：跑一次 `scripts.bench_eval` 才会生成。")
    else:
        lines.extend(["| 题库 | 参与 | 跳过 | 最近原因 |", "|---|---|---|---|"])
        for gap in gaps:
            reason = "；".join(gap.get("reasons") or [])[:80].replace("|", "｜") or "—"
            lines.append(
                f"| {gap.get('dataset') or '—'} | {gap.get('used')} | {gap.get('skipped')} | {reason} |"
            )
    lines.extend(
        [
            "",
            "## 6. 下一步",
            "",
            "```bash",
            "# 只看错 2 次以上的题，生成蒸馏草稿（只写 _draft/，不会自动生效）",
            "python -m scripts.distill_skills --min-wrong 2",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="题库复盘：错误次数与题库缺口")
    parser.add_argument("--attempts", default=str(DEFAULT_ATTEMPTS))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--source", default="", help="只统计某个题库来源")
    parser.add_argument("--min-wrong", type=int, default=1)
    parser.add_argument("--top", type=int, default=40)
    args = parser.parse_args(argv)

    records = read_jsonl(Path(args.attempts))
    if args.source:
        records = [
            row
            for row in records
            if str(row.get("source") or "") == args.source
            or str(row.get("run_tag") or "") == args.source
        ]
    if not records:
        print(f"没有作答记录：{args.attempts}（先跑 scripts.bench_eval）")
        return 2

    buckets = aggregate(records)
    gaps = bank_gaps()
    report = render(
        records=records, buckets=buckets, gaps=gaps, min_wrong=args.min_wrong, top=args.top
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding="utf-8")

    wrong_questions = sum(1 for bucket in buckets.values() if bucket["wrong"])
    print(
        f"题目 {len(buckets)}｜作答 {len(records)}｜错题 {wrong_questions} 道｜"
        f"题库缺口 {sum(int(g.get('skipped') or 0) for g in gaps)} 条"
    )
    print(f"复盘：{output}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
