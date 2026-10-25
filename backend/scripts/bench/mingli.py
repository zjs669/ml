"""MingLi-Bench 适配器（160 题 / 32 个命例 / MIT）。

数据来源：https://github.com/DestinyLinker/MingLi-Bench
放在 `backend/data/bench/MingLi-Bench/data/data.json`（已 gitignore，不随仓库分发）。

这个适配器比通用 JSONL 多做三件事：

1. **出生信息 → 排盘入参**：把 `birth_info` 转成 `chart_input`，评测时先算盘再答题；
2. **从题干抽年份 → 流年窗口**：问「1996 年发生何事」时，把 1996 附近的流年一起给模型；
3. **显式记录假设**：原数据只有「出生地点：usa」这类文字，没有时区。
   时区按下表近似，并在 `notes` 里标注 `tz_assumed`，避免把「时区猜错」算成模型答错。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from scripts.bench.datasets import BenchCase, LoadReport

#: 只覆盖数据里出现过的国家/地区；没命中就退回 Asia/Shanghai 并标记假设
COUNTRY_TZ = {
    "usa": "America/New_York",
    "united states": "America/New_York",
    "canada": "America/Toronto",
    "uk": "Europe/London",
    "united kingdom": "Europe/London",
    "china": "Asia/Shanghai",
    "中国大陆": "Asia/Shanghai",
    "中国": "Asia/Shanghai",
    "hong kong": "Asia/Hong_Kong",
    "香港": "Asia/Hong_Kong",
    "taiwan": "Asia/Taipei",
    "台灣": "Asia/Taipei",
    "台湾": "Asia/Taipei",
    "malaysia": "Asia/Kuala_Lumpur",
    "singapore": "Asia/Singapore",
    "australia": "Australia/Sydney",
    "japan": "Asia/Tokyo",
}

YEAR_RE = re.compile(r"(1[89]\d{2}|20\d{2})")


def _timezone(birth: dict[str, Any]) -> tuple[str, bool]:
    location = str(birth.get("country") or birth.get("location") or "").strip().lower()
    for key, tz in COUNTRY_TZ.items():
        if key in location:
            return tz, False
    return "Asia/Shanghai", True


def _chart_input(birth: dict[str, Any], years: list[int]) -> tuple[dict[str, Any], list[str]]:
    notes: list[str] = []
    try:
        year = int(birth["year"])
        month = int(birth["month"])
        day = int(birth["day"])
        hour = int(birth.get("hour") or 0)
        minute = int(birth.get("minute") or 0)
    except (KeyError, TypeError, ValueError):
        return {}, ["birth_info_incomplete"]

    if str(birth.get("calendar_type") or "solar") != "solar":
        notes.append("non_solar_calendar")

    tz, assumed = _timezone(birth)
    if assumed:
        notes.append("tz_assumed")

    gender_text = str(birth.get("gender") or "")
    gender = "male" if "男" in gender_text or gender_text.lower() == "male" else (
        "female" if "女" in gender_text or gender_text.lower() == "female" else "unknown"
    )

    payload: dict[str, Any] = {
        "birth_datetime": f"{year:04d}-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}:00",
        "timezone": tz,
        "gender": gender,
        "time_known": True,
        "convention": {},
    }
    # 题干里出现过 19xx/20xx 时，把这一段流年一起算出来，模型才能谈「那一年」
    if years:
        start = min(years)
        span = max(years) - start + 1
        if 0 < span <= 30:
            payload["liunian_start_year"] = start
            payload["liunian_years"] = span
        else:
            payload["liunian_start_year"] = start
            payload["liunian_years"] = 10
            notes.append("liunian_window_truncated")
    return payload, notes


def _options(raw: list[dict[str, Any]]) -> list[dict[str, str]]:
    options: list[dict[str, str]] = []
    for item in raw:
        letter = str(item.get("letter") or "").strip().upper()
        text = str(item.get("text") or "").strip()
        if letter and text:
            options.append({"key": letter, "text": text})
    return options


def _load_rows(path: Path, *, limit: int | None) -> LoadReport:
    """读 `prepare_bench` 产出的归一化 JSONL（带 chart_input）。"""
    cases: list[BenchCase] = []
    skipped = 0
    reasons: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            skipped += 1
            continue
        options = [(str(item.get("key")), str(item.get("text"))) for item in row.get("options") or []]
        if not row.get("question") or not options or not row.get("answer"):
            skipped += 1
            reasons.append(f"{row.get('id')}: 字段不完整")
            continue
        cases.append(
            BenchCase(
                id=str(row.get("id")),
                domain=str(row.get("domain") or "bazi"),
                question=str(row["question"]),
                options=options,
                answer_key=str(row["answer"]).upper(),
                answer_text="",
                source=str(row.get("source") or "MingLi-Bench"),
                split=str(row.get("split") or "unknown"),
                chart_input=row.get("chart_input") or {},
                raw=row.get("meta") or {},
            )
        )
        if limit is not None and len(cases) >= limit:
            break
    return LoadReport(cases=cases, skipped=skipped, reasons=reasons[:10])


def load(path: Path, *, limit: int | None = None) -> LoadReport:
    if path.suffix.lower() == ".jsonl":
        return _load_rows(path, limit=limit)

    payload = json.loads(path.read_text(encoding="utf-8"))
    questions = payload.get("questions") if isinstance(payload, dict) else payload
    if not isinstance(questions, list):
        raise ValueError("MingLi-Bench data.json 结构不符合预期（缺少 questions 数组）")

    cases: list[BenchCase] = []
    skipped = 0
    reasons: list[str] = []
    for item in questions:
        if not isinstance(item, dict):
            skipped += 1
            continue
        if not item.get("has_answer") or not item.get("answer"):
            skipped += 1
            reasons.append(f"{item.get('id')}: 无标准答案")
            continue
        options = _options(item.get("options") or [])
        if len(options) < 2:
            skipped += 1
            reasons.append(f"{item.get('id')}: 选项不足")
            continue
        question = str(item.get("question") or "").strip()
        if not question:
            skipped += 1
            continue

        years = sorted({int(match) for match in YEAR_RE.findall(question)})
        chart_input, notes = _chart_input(item.get("birth_info") or {}, years)
        if not chart_input:
            skipped += 1
            reasons.append(f"{item.get('id')}: 出生信息不完整")
            continue

        cases.append(
            BenchCase(
                id=str(item.get("id") or f"mlb-{len(cases):04d}"),
                domain="bazi",
                question=question,
                options=[(entry["key"], entry["text"]) for entry in options],
                answer_key=str(item["answer"]).strip().upper(),
                answer_text="",
                source="MingLi-Bench",
                split=str(item.get("category") or "unknown"),
                chart_input=chart_input,
                raw={
                    "category": item.get("category"),
                    "case_id": item.get("case_id"),
                    "birth_info": item.get("birth_info"),
                    "notes": notes,
                },
            )
        )
        if limit is not None and len(cases) >= limit:
            break
    return LoadReport(cases=cases, skipped=skipped, reasons=reasons[:10])
