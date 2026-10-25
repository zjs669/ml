"""题库适配：把不同来源的题目统一成 `BenchCase`。

不在代码里下载数据集（许可证与体积原因）。使用者把文件放到
`backend/data/bench/<dataset>/cases.jsonl`，再指定 `--dataset` 选择字段映射。

已知来源的字段差异（按公开描述的常见布局）：

| 来源 | 题目 | 选项 | 答案 |
|---|---|---|---|
| MingLi-Bench | `question` | `options` | `answer`（A/B/C/D） |
| fate-bench | `question` / `q` | `options` / `choices` | `answer` / `label` |
| BaziQA | `question` / `q` | `options` / `choices` | `answer` / `correct` |
| generic | 同上，任选一种 | | |

适配器全部是「宽容读取 + 明确报错」：读不到题号或答案就跳过并计数，
不会猜一个答案继续跑——那会让准确率看起来比实际好。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

LETTERS = "ABCDEFGH"


@dataclass
class BenchCase:
    id: str
    domain: str
    question: str
    options: list[tuple[str, str]]  # (key, text)
    answer_key: str
    answer_text: str
    source: str
    split: str = "test"
    chart_input: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class LoadReport:
    cases: list[BenchCase]
    skipped: int = 0
    reasons: list[str] = field(default_factory=list)


def _pick(record: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in record and record[key] not in (None, "", []):
            return record[key]
    return None


def _options(raw: Any) -> list[tuple[str, str]]:
    if isinstance(raw, dict):
        items = sorted(raw.items(), key=lambda pair: str(pair[0]))
        return [(str(key).strip()[:1].upper() or LETTERS[index], str(value)) for index, (key, value) in enumerate(items)]
    if isinstance(raw, list):
        result: list[tuple[str, str]] = []
        for index, item in enumerate(raw):
            if isinstance(item, str):
                result.append((LETTERS[index], item))
            elif isinstance(item, dict):
                key = _pick(item, "key", "label", "option", "id")
                text = _pick(item, "text", "value", "content", "option")
                if text is None:
                    continue
                result.append((str(key or LETTERS[index]).strip()[:1].upper(), str(text)))
        return result
    return []


def _answer_key(answer: Any, options: list[tuple[str, str]]) -> tuple[str, str]:
    """把答案归一成 (字母, 文本)；支持字母、1-based 序号、完整文本。"""
    if answer is None:
        return "", ""
    text = str(answer).strip()
    upper = text.upper()
    keys = [key for key, _ in options]
    if upper[:1] in keys:
        key = upper[:1]
        return key, dict(options)[key]
    if upper.startswith("OPTION "):
        candidate = upper.split(" ", 1)[1][:1]
        if candidate in keys:
            return candidate, dict(options)[candidate]
    if text.isdigit():
        index = int(text) - 1
        if 0 <= index < len(options):
            return options[index]
        if 0 <= int(text) < len(options):
            return options[int(text)]
    for key, value in options:
        if text and (text == value or text in value or value in text):
            return key, value
    return upper[:1], ""


def _normalize(record: dict[str, Any], index: int, *, fmt: str, source: str) -> BenchCase | None:
    question = _pick(record, "question", "q", "prompt", "stem", "title")
    options = _options(_pick(record, "options", "choices", "candidates", "items"))
    answer = _pick(record, "answer", "correct", "label", "target", "gold")
    if not question or not options or answer is None:
        return None
    key, text = _answer_key(answer, options)
    if not key:
        return None
    domain = str(_pick(record, "domain", "subject", "category") or ("bazi" if fmt in ("baziqa", "mingli_bench") else "bazi"))
    # 只有本仓库支持的四个术数才参与评测，其他类别（健康/婚姻等）仍归到 bazi 大类
    if domain not in ("bazi", "ziwei", "liuyao", "qimen"):
        domain = "bazi"
    return BenchCase(
        id=str(_pick(record, "id", "case_id", "qid") or f"{fmt}-{index:05d}"),
        domain=domain,
        question=str(question).strip(),
        options=options,
        answer_key=key,
        answer_text=text,
        source=str(_pick(record, "source", "origin", "dataset") or source),
        split=str(_pick(record, "split", "set") or "test"),
        chart_input=_pick(record, "chart_input", "birth", "chart") or {},
        raw=record,
    )


def load_cases(path: Path, *, fmt: str = "generic", limit: int | None = None) -> LoadReport:
    if not path.is_file():
        raise FileNotFoundError(f"题库文件不存在：{path}")
    cases: list[BenchCase] = []
    skipped = 0
    reasons: list[str] = []
    with path.open("r", encoding="utf-8") as handle:
        for index, line in enumerate(handle):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                skipped += 1
                reasons.append(f"第 {index + 1} 行不是合法 JSON")
                continue
            if not isinstance(record, dict):
                skipped += 1
                continue
            case = _normalize(record, index, fmt=fmt, source=path.parent.name)
            if case is None:
                skipped += 1
                reasons.append(f"第 {index + 1} 行缺少题目/选项/答案")
                continue
            cases.append(case)
            if limit is not None and len(cases) >= limit:
                break
    return LoadReport(cases=cases, skipped=skipped, reasons=reasons[:10])


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1
    return count


def append_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    """追加写入。追问式蒸馏需要历史：同一道题错几次，靠追加才看得见。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1
    return count


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            rows.append(record)
    return rows
