"""导出盘面校验用的 chart_facts 样本。

前端 `npm run check:boards` 会读这份 JSON 做 SSR 渲染冒烟。
为什么不放在 frontend/src 下：放进 src 会被打进产物；放 var/ 是运行时目录，已被 gitignore。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from app.domains.registry import get_engine

# scripts/ 的父目录是 backend/，再往上一级才是仓库根
BACKEND = Path(__file__).resolve().parents[1]
OUT = BACKEND / "var" / "board-facts.json"

#: 只导出有专属盘面的三个域
CASES: dict[str, dict] = {
    "almanac": {"date": "2026-10-25"},
    "tarot": {"spread": "three", "seed": "board-check"},
    "daliuren": {"cast_datetime": "2026-10-25T15:00:00"},
}


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, dict] = {}
    for domain, body in CASES.items():
        spec = get_engine(domain)
        payload[domain] = spec.calculate(spec.input_model.model_validate(body)).chart_facts
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已写入 {OUT}（{len(payload)} 个域）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
