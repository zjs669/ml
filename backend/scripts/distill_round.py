"""一轮蒸馏：train 挖错题 → 生成草稿 → test 测量 → 记录 delta。

为什么 train / test 要分开跑：
在 test 上看错题再改提示词，本质是在测试集上调参，准确率会虚高。
所以固定为「train 挖错、test 只测量」，每一轮的 test 只跑一次。

用法：
    python -m scripts.distill_round --round 2 --model minimax-m3.1-flash
    python -m scripts.distill_round --round 2 --no-distill    # 只测量，不生成草稿

产物：
- `data/bench/train_attempts.jsonl` / `test_attempts.jsonl`（分开的作答历史）
- `docs/题库复盘.md`（train）
- `docs/模型评测-题库.md`（test）
- `docs/蒸馏记录.md`（每轮一行，含带卡/无卡的 delta）
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
DATASET = BACKEND_DIR / "data" / "bench" / "MingLi-Bench"
TRAIN = DATASET / "train.jsonl"
TEST = DATASET / "test.jsonl"
TRAIN_ATTEMPTS = BACKEND_DIR / "data" / "bench" / "train_attempts.jsonl"
TEST_ATTEMPTS = BACKEND_DIR / "data" / "bench" / "test_attempts.jsonl"
REVIEW = REPO_ROOT / "docs" / "题库复盘.md"
REPORT = REPO_ROOT / "docs" / "模型评测-题库.md"
LOG = REPO_ROOT / "docs" / "蒸馏记录.md"
SUMMARY_DIR = BACKEND_DIR / "data" / "bench" / "summaries"


def _run(args: list[str]) -> int:
    print("$", " ".join(args))
    return subprocess.call([sys.executable, "-m", *args], cwd=BACKEND_DIR)


def _summary(name: str) -> dict:
    path = SUMMARY_DIR / name
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _eval(
    name: str,
    *,
    file: Path,
    attempts: Path,
    out: Path,
    model: str,
    tokens: int,
    tag: str,
    no_skills: bool = False,
    extra: list[str] | None = None,
) -> dict:
    summary_path = SUMMARY_DIR / f"{name}.json"
    args = [
        "scripts.bench_eval",
        "--dataset",
        "mingli_bench",
        "--file",
        str(file),
        "--model",
        model,
        "--max-tokens",
        str(tokens),
        "--tag",
        tag,
        "--attempts",
        str(attempts),
        "--output",
        str(out),
        "--summary-json",
        str(summary_path),
        *(extra or []),
    ]
    if no_skills:
        args.append("--no-skills")
    code = _run(args)
    if code != 0:
        raise SystemExit(f"bench_eval 失败：{name}")
    return _summary(f"{name}.json")


def _append_log(row: dict) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    if not LOG.is_file():
        LOG.write_text(
            "# 蒸馏记录\n\n"
            "> 由 `python -m scripts.distill_round` 追加。train 用来挖错题，test 只用来测量。\n\n"
            "| 轮次 | 时间 | 模型 | train | test | test-无卡 | delta | 备注 |\n"
            "|---|---|---|---|---|---|---|---|\n",
            encoding="utf-8",
        )
    line = (
        f"| {row['round']} | {row['time']} | `{row['model']}` | "
        f"{row['train']:.1f}% | {row['test']:.1f}% | {row['test_no_skills']:.1f}% | "
        f"{row['delta']:+.1f}pp | {row['note']} |\n"
    )
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(line)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="跑一轮蒸馏并记录 delta")
    parser.add_argument("--round", type=int, required=True)
    parser.add_argument("--model", default="minimax-m3.1-flash")
    parser.add_argument("--tokens", type=int, default=1600)
    parser.add_argument("--no-distill", action="store_true", help="只评测与记录，不生成草稿")
    parser.add_argument("--min-samples", type=int, default=2)
    parser.add_argument("--limit-groups", type=int, default=2)
    parser.add_argument("--limit", type=int, default=0, help="只跑前 N 题（冒烟用，默认全量）")
    args = parser.parse_args(argv)

    for path in (TRAIN, TEST):
        if not path.is_file():
            print(f"缺少 {path}；先跑 python -m scripts.prepare_bench")
            return 2

    round_tag = f"round{args.round}"
    limit_args = ["--limit", str(args.limit)] if args.limit else []
    train = _eval(
        f"{round_tag}-train",
        file=TRAIN,
        attempts=TRAIN_ATTEMPTS,
        out=REPO_ROOT / "docs" / "模型评测-题库.md",
        model=args.model,
        tokens=args.tokens,
        tag=f"{round_tag}-train",
        extra=limit_args,
    )

    _run(["scripts.bench_stats", "--attempts", str(TRAIN_ATTEMPTS), "--output", str(REVIEW), "--min-wrong", "2"])

    if not args.no_distill:
        _run(
            [
                "scripts.distill_skills",
                "--attempts",
                str(TRAIN_ATTEMPTS),
                "--min-samples",
                str(args.min_samples),
                "--limit-groups",
                str(args.limit_groups),
                "--model",
                args.model,
            ]
        )

    test = _eval(
        f"{round_tag}-test",
        file=TEST,
        attempts=TEST_ATTEMPTS,
        out=REPORT,
        model=args.model,
        tokens=args.tokens,
        tag=f"{round_tag}-test",
        extra=limit_args,
    )
    ablation = _eval(
        f"{round_tag}-test-noskill",
        file=TEST,
        attempts=TEST_ATTEMPTS,
        out=REPO_ROOT / "docs" / "模型评测-题库-无技能.md",
        model=args.model,
        tokens=args.tokens,
        tag=f"{round_tag}-test-noskill",
        no_skills=True,
        extra=limit_args,
    )

    row = {
        "round": args.round,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "model": args.model,
        "train": train.get("accuracy", 0.0) * 100,
        "test": test.get("accuracy", 0.0) * 100,
        "test_no_skills": ablation.get("accuracy", 0.0) * 100,
        "delta": (test.get("accuracy", 0.0) - ablation.get("accuracy", 0.0)) * 100,
        "note": f"distill={'off' if args.no_distill else 'on'}" + (f" limit={args.limit}" if args.limit else ""),
    }
    _append_log(row)

    print(
        f"\n第 {args.round} 轮：train {row['train']:.1f}%｜test {row['test']:.1f}%｜"
        f"无卡 {row['test_no_skills']:.1f}%｜delta {row['delta']:+.1f}pp"
    )
    print(f"记录：{LOG}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
