"""把题库整理成可复用的训练/评测语料（不训练权重，只做蒸馏与评测的输入）。

产物（全部在 `backend/data/bench/`，已 gitignore）：

| 文件 | 用途 |
|---|---|
| `MingLi-Bench/cases.jsonl` | 归一化后的 160 题（含 `chart_input`，可直接被 bench_eval 读取） |
| `MingLi-Bench/train.jsonl` | 按**命例**切分的训练/蒸馏集（约 75%） |
| `MingLi-Bench/test.jsonl` | 按**命例**切分的留出集（约 25%） |
| `MingLi-Bench/dataset_card.md` | 数据来源、许可证、字段说明、已知偏差 |

关键约束：**按命例切分**，同一命例的 5 道题不会同时出现在 train 和 test 里。
按题目随机切会造成记忆泄漏——模型见过同一张盘的其他题，准确率会虚高。

用法：
    python -m scripts.prepare_bench
    python -m scripts.prepare_bench --ratio 0.7
"""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

from scripts.bench import mingli

BACKEND_DIR = Path(__file__).resolve().parents[1]
DATASET_DIR = BACKEND_DIR / "data" / "bench" / "MingLi-Bench"
DATA_JSON = DATASET_DIR / "data" / "data.json"


def _row(case) -> dict:
    return {
        "id": case.id,
        "domain": case.domain,
        "question": case.question,
        "options": [{"key": key, "text": text} for key, text in case.options],
        "answer": case.answer_key,
        "chart_input": case.chart_input,
        "source": case.source,
        "split": case.split,
        "meta": case.raw,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="整理 MingLi-Bench 为训练/评测语料")
    parser.add_argument("--data", default=str(DATA_JSON))
    parser.add_argument("--ratio", type=float, default=0.75, help="训练集命例占比")
    parser.add_argument("--seed", type=int, default=20261025)
    args = parser.parse_args(argv)

    path = Path(args.data)
    if not path.is_file():
        print(f"找不到 {path}；先按 docs/题库与蒸馏.md 的说明取数据")
        return 2

    loaded = mingli.load(path)
    cases = loaded.cases
    if not cases:
        print("没有可用题目")
        return 2

    by_case: dict[str, list] = defaultdict(list)
    for case in cases:
        by_case[str((case.raw or {}).get("case_id") or case.id)].append(case)

    case_ids = sorted(by_case)
    rng = random.Random(args.seed)
    rng.shuffle(case_ids)
    cut = max(int(len(case_ids) * args.ratio), 1)
    train_ids = set(case_ids[:cut])

    train = [case for cid in case_ids if cid in train_ids for case in by_case[cid]]
    test = [case for cid in case_ids if cid not in train_ids for case in by_case[cid]]

    def dump(name: str, rows: list) -> int:
        target = DATASET_DIR / name
        with target.open("w", encoding="utf-8") as handle:
            for case in rows:
                handle.write(json.dumps(_row(case), ensure_ascii=False) + "\n")
        return len(rows)

    counts = {
        "cases.jsonl": dump("cases.jsonl", cases),
        "train.jsonl": dump("train.jsonl", train),
        "test.jsonl": dump("test.jsonl", test),
    }

    categories = Counter(case.split for case in cases)
    notes = Counter(
        note for case in cases for note in ((case.raw or {}).get("notes") or [])
    )
    card = [
        "# MingLi-Bench 数据集卡片",
        "",
        f"- 来源：`https://github.com/DestinyLinker/MingLi-Bench`（MIT，数据源自 2022–2025 全球算命师大赛）",
        f"- 题目：{len(cases)} 道四选一，覆盖 {len(by_case)} 个命例",
        f"- 切分：按命例 {args.ratio:.0%} / {1 - args.ratio:.0%}，seed={args.seed}",
        f"- 归一化：`scripts/bench/mingli.py`；评测：`scripts/bench_eval.py --dataset mingli_bench`",
        "",
        "## 字段",
        "",
        "`id / domain / question / options[{key,text}] / answer(字母) / chart_input / source / split(类目) / meta`",
        "",
        "`chart_input` 由 `birth_info` 转换而来，评测时先由本仓库引擎算出盘面再交给模型。",
        "",
        "## 已知偏差",
        "",
        "- 原数据只有「出生地点：usa」这类文字，没有时区；适配器按国家映射近似，并记 `tz_assumed`。",
        "- 类别以婚姻/事业/家庭为主，健康、灾劫样本很少，分科准确率波动大。",
        "- 这些题问的是**具体事件**（哪年结婚、发生何事），属于传统断法；本项目对用户不做此类断言，",
        "  这里仅用于内部评测与蒸馏，不作为产品话术。",
        "",
        "## 类目分布",
        "",
        "| 类目 | 题数 |",
        "|---|---|",
        *[f"| {key} | {value} |" for key, value in categories.most_common()],
        "",
        f"## 排盘假设统计：{dict(notes) or '无'}",
        "",
    ]
    (DATASET_DIR / "dataset_card.md").write_text("\n".join(card), encoding="utf-8")

    print("写出：", ", ".join(f"{name}={count}" for name, count in counts.items()))
    print(f"训练命例 {len(train_ids)} 个 / 留出命例 {len(case_ids) - len(train_ids)} 个")
    print(f"数据卡：{DATASET_DIR / 'dataset_card.md'}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
