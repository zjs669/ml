"""导出盘面校验用的 chart_facts 样本。

前端 `npm run check:boards` 会读这份 JSON 做 SSR 渲染冒烟。
为什么不放在 frontend/src 下：放进 src 会被打进产物；放 var/ 是运行时目录，已被 gitignore。

覆盖范围必须与 `ChartBoard.vue` 的 `BOARDS` 登记表一致 —— 有专属盘面就要有样本，
否则「新增盘面忘了验」只能靠人记。`tests/test_board_facts.py` 会校验两边一致。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from app.domains.registry import get_engine

# scripts/ 的父目录是 backend/，再往上一级才是仓库根
BACKEND = Path(__file__).resolve().parents[1]
OUT = BACKEND / "var" / "board-facts.json"

#: 有专属盘面组件的域 → 一组能覆盖主要分支的入参
CASES: dict[str, dict] = {
    "almanac": {"date": "2026-10-25"},
    "tarot": {"spread": "three", "seed": "board-check"},
    "daliuren": {"cast_datetime": "2026-10-25T15:00:00"},
    "astrology": {
        "birth_datetime": "1990-05-20T12:00:00",
        "timezone": "Asia/Shanghai",
        "latitude": 31.23,
        "longitude": 121.47,
    },
    "meihua": {"method": "numbers", "numbers": [7, 13]},
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
