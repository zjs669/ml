"""题库适配器：字段宽容读取，但不猜答案。

这些用例锁的是「格式归一」这一层：选项顺序、答案字母/序号/文本三种写法、
缺字段必须跳过而不是填默认值。
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.bench.datasets import load_cases


def _write(tmp_path: Path, records: list[dict]) -> Path:
    path = tmp_path / "cases.jsonl"
    path.write_text(
        "\n".join(json.dumps(item, ensure_ascii=False) for item in records) + "\n",
        encoding="utf-8",
    )
    return path


def test_options_from_string_list(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        [{"id": "a1", "question": "日主如何取？", "options": ["年干", "月干", "日干", "时干"], "answer": "C"}],
    )
    loaded = load_cases(path, fmt="generic")
    assert loaded.skipped == 0
    case = loaded.cases[0]
    assert [key for key, _ in case.options] == ["A", "B", "C", "D"]
    assert case.answer_key == "C"
    assert case.answer_text == "日干"


def test_options_from_dict_and_text_answer(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        [
            {
                "id": "a2",
                "question": "三合局有哪些？",
                "options": {"A": "申子辰", "B": "寅午戌", "C": "亥卯未", "D": "巳酉丑"},
                "answer": "亥卯未",
            }
        ],
    )
    case = load_cases(path, fmt="fate_bench").cases[0]
    assert case.answer_key == "C"


def test_one_based_numeric_answer(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        [{"id": "a3", "question": "紫微五行局共几种？", "choices": ["三", "四", "五", "六"], "answer": 3}],
    )
    case = load_cases(path, fmt="baziqa").cases[0]
    assert case.answer_key == "C"
    assert case.answer_text == "五"


def test_missing_fields_are_skipped_not_guessed(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        [
            {"id": "ok", "question": "有答案的题", "options": ["甲", "乙"], "answer": "A"},
            {"id": "no-answer", "question": "没有答案的题", "options": ["甲", "乙"]},
            {"id": "no-options", "question": "没有选项的题", "answer": "A"},
        ],
    )
    loaded = load_cases(path, fmt="generic")
    assert [case.id for case in loaded.cases] == ["ok"]
    assert loaded.skipped == 2


def test_limit_stops_early(tmp_path: Path) -> None:
    records = [
        {"id": f"q{i}", "question": f"题 {i}", "options": ["甲", "乙"], "answer": "A"}
        for i in range(5)
    ]
    loaded = load_cases(_write(tmp_path, records), fmt="generic", limit=2)
    assert [case.id for case in loaded.cases] == ["q0", "q1"]


def test_unknown_domain_falls_back_to_bazi(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        [{"id": "d1", "domain": "健康", "question": "题目", "options": ["甲", "乙"], "answer": "A"}],
    )
    assert load_cases(path, fmt="generic").cases[0].domain == "bazi"
