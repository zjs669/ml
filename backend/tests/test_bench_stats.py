"""题库复盘与蒸馏聚合：错了几次、未作答几次、题库缺多少答案。

这两件事必须可复算，否则「蒸馏」就会退化成「凭印象改提示词」。
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts import bench_stats
from scripts.distill_skills import _aggregate


def _row(case_id: str, *, correct: bool, got: str = "A", error: str = "", domain: str = "bazi") -> dict:
    return {
        "id": case_id,
        "domain": domain,
        "source": "demo",
        "expected": "B",
        "got": got,
        "correct": correct,
        "error": error,
        "question": f"题目 {case_id}",
    }


def test_aggregate_counts_attempts_and_unanswered() -> None:
    records = [
        _row("q1", correct=False, got="A", error="选错"),
        _row("q1", correct=False, got="", error="answer_not_parsed"),
        _row("q1", correct=True, got="B"),
        _row("q2", correct=False, got="C", error="选错"),
    ]
    buckets = bench_stats.aggregate(records)
    assert buckets["q1"]["attempts"] == 3
    assert buckets["q1"]["wrong"] == 2
    assert buckets["q1"]["unanswered"] == 1
    assert buckets["q1"]["last_error"] == ""  # 最后一次是答对，不再记错误
    assert buckets["q2"]["wrong"] == 1


def test_render_reports_gaps_and_wrong_counts(tmp_path: Path, monkeypatch) -> None:
    records = [_row("q1", correct=False, got=""), _row("q1", correct=False, error="选错")]
    buckets = bench_stats.aggregate(records)

    bench_dir = tmp_path / "bench"
    dataset_dir = bench_dir / "mingli_bench"
    dataset_dir.mkdir(parents=True)
    (dataset_dir / "last_load.json").write_text(
        json.dumps({"dataset": "mingli_bench", "used": 8, "skipped": 2, "reasons": ["第 3 行缺少答案"]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(bench_stats, "BENCH_DIR", bench_dir)

    report = bench_stats.render(
        records=records,
        buckets=buckets,
        gaps=bench_stats.bank_gaps(),
        min_wrong=1,
        top=10,
    )
    assert "未作答次数" in report
    assert "题库缺答案/缺字段被跳过 | 2" in report
    assert "`q1`" in report
    assert "2/2" in report
    assert "第 3 行缺少答案" in report


def test_distill_aggregate_counts_wrong_per_question() -> None:
    rows = [
        {"id": "q1", "domain": "bazi", "correct": False, "got": "", "error": "answer_not_parsed"},
        {"id": "q1", "domain": "bazi", "correct": False, "got": "A", "error": ""},
        {"id": "q1", "domain": "bazi", "correct": True, "got": "B"},
        {"id": "q2", "domain": "ziwei", "correct": False, "got": "C", "error": ""},
    ]
    items = {item["id"]: item for item in _aggregate(rows, domain=None)}
    assert items["q1"]["wrong"] == 2
    assert items["q2"]["domain"] == "ziwei"
    # 只按 bazi 过滤时，ziwei 的题不应出现
    assert [item["id"] for item in _aggregate(rows, domain="bazi")] == ["q1"]
