"""MingLi-Bench 适配与「预计算盘面」的行为约定。

不依赖外部数据集：只测字段映射、归一化 JSONL 读取，以及引擎管线是否能
把 birth_info 变成一段可放进 prompt 的盘面摘要。
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.bench import charts, mingli

BIRTH = {
    "raw": "男命：1974年4月28日下午4:40分 出生地点：usa",
    "gender": "男",
    "year": 1974,
    "month": 4,
    "day": 28,
    "hour": 16,
    "minute": 40,
    "country": "usa",
    "calendar_type": "solar",
}


def test_chart_input_maps_timezone_gender_and_liunian() -> None:
    payload, notes = mingli._chart_input(BIRTH, [1996, 2008])
    assert payload["birth_datetime"] == "1974-04-28T16:40:00"
    assert payload["timezone"] == "America/New_York"
    assert payload["gender"] == "male"
    # 题干里出现两个年份 → 流年窗口覆盖到最大年份
    assert payload["liunian_start_year"] == 1996
    assert payload["liunian_years"] == 13
    assert notes == []


def test_unknown_country_is_marked_as_assumption() -> None:
    payload, notes = mingli._chart_input({**BIRTH, "country": "atlantis"}, [])
    assert payload["timezone"] == "Asia/Shanghai"
    assert "tz_assumed" in notes


def test_incomplete_birth_is_rejected() -> None:
    payload, notes = mingli._chart_input({"country": "usa"}, [])
    assert payload == {}
    assert notes == ["birth_info_incomplete"]


def test_load_rows_reads_normalized_jsonl(tmp_path: Path) -> None:
    path = tmp_path / "cases.jsonl"
    path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "id": "x1",
                        "domain": "bazi",
                        "question": "此命何年结婚？",
                        "options": [{"key": "A", "text": "1999"}, {"key": "B", "text": "2002"}],
                        "answer": "b",
                        "chart_input": {"birth_datetime": "1990-05-20T12:00:00"},
                        "source": "MingLi-Bench",
                        "split": "婚姻",
                        "meta": {"notes": []},
                    },
                    ensure_ascii=False,
                ),
                json.dumps({"id": "bad", "question": "缺字段"}, ensure_ascii=False),
            ]
        ),
        encoding="utf-8",
    )
    loaded = mingli.load(path)
    assert [case.id for case in loaded.cases] == ["x1"]
    assert loaded.cases[0].answer_key == "B"
    assert loaded.cases[0].split == "婚姻"
    assert loaded.skipped == 1


def test_chart_pipeline_produces_prompt_block() -> None:
    payload, _ = mingli._chart_input(BIRTH, [1996])
    result, error = charts.compute("bazi", payload)
    assert error == ""
    assert result is not None
    text = charts.summarize("bazi", result)
    assert "四柱：" in text
    assert "流年：" in text
    assert "1996" in text


def test_chart_pipeline_returns_error_instead_of_raising() -> None:
    result, error = charts.compute("bazi", {"birth_datetime": "not-a-date"})
    assert result is None
    assert "Error" in error
