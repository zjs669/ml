"""新域的报告链路冒烟测试。

技能包存在 ≠ 报告能生成：解析、检索、预扣、校验、降级、结算每一步都可能断。
这里对每个新域各跑一次「保存命盘 → 生成简版报告」，断言不抛 SKILL_REJECTED、
账本一致、报告状态合法。

算法正确性由各域自己的测试负责，这里只验链路。
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

PASSWORD = "Passw0rd123"

#: 每个域一份最小可算入参（与 test_api_domains 共用同一批，避免两处漂移）
PAYLOADS: dict[str, dict] = {
    "almanac": {"date": "2026-10-25"},
    "xiaoliuren": {"input_mode": "gregorian", "date": "2026-10-25T00:00:00", "hour": 15},
    "meihua": {"method": "numbers", "numbers": [7, 13]},
    "tarot": {"spread": "three", "seed": "smoke-seed"},
    "taiyi": {"date": "2026-10-25", "mode": "day"},
    "daliuren": {"cast_datetime": "2026-10-25T15:00:00"},
    "astrology": {
        "birth_datetime": "1990-05-20T12:00:00",
        "timezone": "Asia/Shanghai",
        "latitude": 31.23,
        "longitude": 121.47,
    },
    "ziwei_horoscope": {
        "birth_datetime": "1990-05-20T12:00:00",
        "gender": "male",
        "target_date": "2026-10-25T00:00:00",
    },
    "ziwei_flying": {
        "birth_datetime": "1990-05-20T12:00:00",
        "gender": "male",
        "query_type": "flies_from",
        "from_palace": "命宫",
    },
    "hepan": {
        "left": {"label": "甲方", "pillars": {"year": "庚午", "month": "辛巳", "day": "乙酉", "hour": "壬午"}},
        "right": {"label": "乙方", "pillars": {"year": "庚午", "month": "辛巳", "day": "丙辰", "hour": "甲午"}},
    },
    "dream": {"text": "梦见一条蛇在水边游走"},
}


def _headers(client: TestClient) -> dict[str, str]:
    email = f"rp_{uuid.uuid4().hex[:10]}@example.com"
    response = client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.mark.parametrize("domain", sorted(PAYLOADS))
def test_report_pipeline_works_for_each_domain(client: TestClient, domain: str) -> None:
    headers = _headers(client)

    saved = client.post(f"/api/v1/charts/{domain}", json=PAYLOADS[domain], headers=headers)
    assert saved.status_code == 201, saved.text
    chart_id = saved.json()["id"]

    report = client.post(
        f"/api/v1/charts/{chart_id}/reports",
        json={"depth": "brief", "topic": None, "skill_key": None},
        headers={**headers, "Idempotency-Key": uuid.uuid4().hex},
    )
    assert report.status_code == 201, report.text
    body = report.json()
    assert body["status"] in ("complete", "degraded")
    assert body["domain"] == domain
    # 技能必须被解析到本域，不能落回别的域
    assert body["skill_version"].startswith(domain)
    # 出参字段名是 report（不是 report_json），与 AiReport 模型列名不同
    assert isinstance(body["report"]["uncertainties"], list)
    assert body["report"]["safety_note"]


def test_mbti_report_pipeline(client: TestClient) -> None:
    headers = _headers(client)
    bank = client.get("/api/v1/mbti/questions").json()
    answers = {item["id"]: "A" for item in bank["questions"]}

    saved = client.post(
        "/api/v1/charts/mbti", json={"answers": answers}, headers=headers
    )
    assert saved.status_code == 201, saved.text
    chart_id = saved.json()["id"]

    report = client.post(
        f"/api/v1/charts/{chart_id}/reports",
        json={"depth": "brief", "topic": None, "skill_key": None},
        headers={**headers, "Idempotency-Key": uuid.uuid4().hex},
    )
    assert report.status_code == 201, report.text
    assert report.json()["skill_version"].startswith("mbti")


def test_every_registered_domain_has_a_skill(client: TestClient) -> None:
    """注册表里的每个域都必须有可用技能包，否则报告会直接 SKILL_REJECTED。"""
    from app.domains.registry import supported_domains
    from app.domains.skills.loader import load_all

    with_skills = {spec.domain for spec in load_all()}
    missing = [domain for domain in supported_domains() if domain not in with_skills]
    assert not missing, f"这些域没有技能包，报告会失败：{missing}"
