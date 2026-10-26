"""前端表单配置与后端入参的契约测试。

`frontend/src/config/domainForms.ts` 的 `build()` 会产出具体 JSON，
但这些 JSON 是否被后端接受，前端 typecheck 查不出来 —— 两侧各自都对，
拼在一起才 422。这里用「前端真实会发的形状」逐域打接口。

字段名与取值必须与 domainForms.ts 保持一致；改任一侧都要同步这里。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

#: 照 domainForms.ts 的 build() 产出构造，包含「条件字段留空」的情形
FRONTEND_PAYLOADS: dict[str, dict] = {
    "almanac": {"date": "2026-10-25", "timezone": "Asia/Shanghai", "birth_date": None},
    "xiaoliuren": {
        "input_mode": "gregorian",
        "date": "2026-10-25T12:00:00",
        "lunar_month": None,
        "lunar_day": None,
        "is_leap_month": False,
        "hour": 12,
        "timezone": "Asia/Shanghai",
        "question": None,
        "store_question": True,
    },
    "tarot": {
        "spread": "three",
        "deck": "all",
        "allow_reversed": True,
        "reversed_probability": 0.35,
        "seed": None,
        "question": None,
        "store_question": True,
    },
    "taiyi": {
        "date": "2026-10-25",
        "mode": "day",
        "hour": 12,
        "timezone": "Asia/Shanghai",
        "question": None,
        "store_question": True,
    },
    "daliuren": {
        "cast_datetime": "2026-10-25T12:00:00",
        "timezone": "Asia/Shanghai",
        "month_general": None,
        "question": None,
        "store_question": True,
    },
    "astrology": {
        "birth_datetime": "1990-05-20T12:00:00",
        "timezone": "Asia/Shanghai",
        "latitude": 31.23,
        "longitude": 121.47,
        "time_known": True,
    },
    "ziwei_horoscope": {
        "birth_datetime": "1990-05-20T12:00:00",
        "timezone": "Asia/Shanghai",
        "gender": "unknown",
        "target_date": "2026-10-25T12:00:00",
        "target_hour": 12,
    },
    "ziwei_flying": {
        "birth_datetime": "1990-05-20T12:00:00",
        "timezone": "Asia/Shanghai",
        "gender": "unknown",
        "query_type": "flies_from",
        "from_palace": "命宫",
        "to_palace": None,
        "mutagens": [],
    },
    "dream": {
        "text": "梦见一条蛇在水边游走",
        "max_keywords": 8,
        "include_traditional": True,
        "store_text": True,
    },
}

#: 梅花七种起卦法各自的 payload（前端按 method 条件拼装）
MEIHUA_PAYLOADS: dict[str, dict] = {
    "time": {"method": "time", "cast_datetime": "2026-10-25T12:00:00"},
    "numbers-2": {"method": "numbers", "numbers": [7, 13]},
    "numbers-3": {"method": "numbers", "numbers": [7, 13, 5]},
    "text": {"method": "text", "text": "占一卦"},
    "measure": {"method": "measure", "length_value": 9, "width_value": 5},
    "direction": {"method": "direction", "direction": "南"},
    "hexagram": {"method": "hexagram", "upper": "乾", "lower": "坤", "moving_line": 3},
}


@pytest.mark.parametrize("domain", sorted(FRONTEND_PAYLOADS))
def test_frontend_payload_accepted(client: TestClient, domain: str) -> None:
    response = client.post(
        f"/api/v1/charts/{domain}/calculate", json=FRONTEND_PAYLOADS[domain]
    )
    assert response.status_code == 200, f"{domain}: {response.text}"


@pytest.mark.parametrize("case", sorted(MEIHUA_PAYLOADS))
def test_meihua_all_casting_methods(client: TestClient, case: str) -> None:
    body = {
        "timezone": "Asia/Shanghai",
        "question": None,
        "store_question": True,
        **MEIHUA_PAYLOADS[case],
    }
    response = client.post("/api/v1/charts/meihua/calculate", json=body)
    assert response.status_code == 200, f"{case}: {response.text}"
    assert response.json()["chart_facts"]["original"]["name"]


def test_xiaoliuren_lunar_mode_payload(client: TestClient) -> None:
    """农历模式下前端会把 date 置 null、农历字段填值。"""
    body = {
        "input_mode": "lunar",
        "date": None,
        "lunar_month": 9,
        "lunar_day": 16,
        "is_leap_month": False,
        "hour": 15,
        "timezone": "Asia/Shanghai",
        "question": None,
        "store_question": True,
    }
    response = client.post("/api/v1/charts/xiaoliuren/calculate", json=body)
    assert response.status_code == 200, response.text


def test_ziwei_flying_flies_into_payload(client: TestClient) -> None:
    """flies_into 时前端把 from_palace 置 null。"""
    body = {
        "birth_datetime": "1990-05-20T12:00:00",
        "timezone": "Asia/Shanghai",
        "gender": "unknown",
        "query_type": "flies_into",
        "from_palace": None,
        "to_palace": "官禄",
        "mutagens": [],
    }
    response = client.post("/api/v1/charts/ziwei_flying/calculate", json=body)
    assert response.status_code == 200, response.text


def test_tarot_with_seed_payload(client: TestClient) -> None:
    body = {
        "spread": "celtic",
        "deck": "minor",
        "allow_reversed": False,
        "reversed_probability": 0.0,
        "seed": "user-seed",
        "question": None,
        "store_question": True,
    }
    response = client.post("/api/v1/charts/tarot/calculate", json=body)
    assert response.status_code == 200, response.text
    assert response.json()["chart_facts"]["draw"]["seed"] == "user-seed"
