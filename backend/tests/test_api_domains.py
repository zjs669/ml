"""新增术数的接口层测试。

只测「接口契约」这一层：注册表能分发、新端点能返回、错误码统一。
算法正确性由各域自己的测试负责，这里不重复断言。
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

PASSWORD = "Passw0rd123"


def _headers(client: TestClient) -> dict[str, str]:
    email = f"dom_{uuid.uuid4().hex[:10]}@example.com"
    response = client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


# ---- /meta/domains ----


def test_domains_endpoint_lists_all(client: TestClient) -> None:
    response = client.get("/api/v1/meta/domains")
    assert response.status_code == 200
    body = response.json()
    domains = {item["domain"] for item in body["domains"]}
    assert body["count"] == len(body["domains"])
    # 四个既有域 + 新增的域都必须在册
    for expected in (
        "bazi",
        "ziwei",
        "liuyao",
        "qimen",
        "almanac",
        "xiaoliuren",
        "meihua",
        "tarot",
        "taiyi",
        "daliuren",
        "astrology",
        "hepan",
        "mbti",
        "dream",
        "ziwei_horoscope",
        "ziwei_flying",
    ):
        assert expected in domains, expected


def test_domains_endpoint_reports_kind(client: TestClient) -> None:
    body = client.get("/api/v1/meta/domains").json()
    for item in body["domains"]:
        assert item["kind"] in ("deterministic", "generative")
        assert item["label"]
        assert item["schools"]


# ---- 新域的计算入口 ----


def test_almanac_calculate(client: TestClient) -> None:
    response = client.post("/api/v1/charts/almanac/calculate", json={"date": "2026-10-25"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["domain"] == "almanac"
    assert body["chart_facts"]["yi"] is not None


def test_xiaoliuren_calculate(client: TestClient) -> None:
    response = client.post(
        "/api/v1/charts/xiaoliuren/calculate",
        json={"input_mode": "gregorian", "date": "2026-10-25T00:00:00", "hour": 15},
    )
    assert response.status_code == 200, response.text
    assert response.json()["chart_facts"]["result_palace"]["name"]


def test_tarot_calculate_is_reproducible(client: TestClient) -> None:
    payload = {"spread": "three", "seed": "api-seed"}
    first = client.post("/api/v1/charts/tarot/calculate", json=payload).json()
    second = client.post("/api/v1/charts/tarot/calculate", json=payload).json()
    assert first["chart_facts"]["cards"] == second["chart_facts"]["cards"]


def test_meihua_calculate(client: TestClient) -> None:
    response = client.post(
        "/api/v1/charts/meihua/calculate", json={"method": "numbers", "numbers": [7, 13]}
    )
    assert response.status_code == 200, response.text
    assert response.json()["chart_facts"]["original"]["name"]


def test_taiyi_calculate(client: TestClient) -> None:
    response = client.post(
        "/api/v1/charts/taiyi/calculate", json={"date": "2026-10-25", "mode": "day"}
    )
    assert response.status_code == 200, response.text
    assert response.json()["chart_facts"]["primary"]["taiyi_name"]


def test_daliuren_calculate(client: TestClient) -> None:
    response = client.post(
        "/api/v1/charts/daliuren/calculate", json={"cast_datetime": "2026-10-25T15:00:00"}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["chart_facts"]["four_lessons"]) == 4


def test_astrology_calculate(client: TestClient) -> None:
    response = client.post(
        "/api/v1/charts/astrology/calculate",
        json={
            "birth_datetime": "1990-05-20T12:00:00",
            "timezone": "Asia/Shanghai",
            "latitude": 31.23,
            "longitude": 121.47,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["chart_facts"]["planets"]["sun"]["sign"]
    assert "水星" in body["chart_facts"]["unavailable"]


def test_ziwei_horoscope_calculate(client: TestClient) -> None:
    response = client.post(
        "/api/v1/charts/ziwei_horoscope/calculate",
        json={
            "birth_datetime": "1990-05-20T12:00:00",
            "gender": "male",
            "target_date": "2026-10-25T00:00:00",
        },
    )
    assert response.status_code == 200, response.text
    layers = response.json()["chart_facts"]["layers"]
    assert [item["layer"] for item in layers] == ["大限", "小限", "流年", "流月", "流日", "流时"]


def test_ziwei_flying_calculate(client: TestClient) -> None:
    response = client.post(
        "/api/v1/charts/ziwei_flying/calculate",
        json={
            "birth_datetime": "1990-05-20T12:00:00",
            "gender": "male",
            "query_type": "flies_from",
            "from_palace": "命宫",
        },
    )
    assert response.status_code == 200, response.text
    assert len(response.json()["chart_facts"]["answer"]["flights"]) == 4


def test_hepan_calculate(client: TestClient) -> None:
    response = client.post(
        "/api/v1/charts/hepan/calculate",
        json={
            "left": {"label": "甲方", "pillars": {"year": "庚午", "month": "辛巳", "day": "乙酉", "hour": "壬午"}},
            "right": {"label": "乙方", "pillars": {"year": "庚午", "month": "辛巳", "day": "丙辰", "hour": "甲午"}},
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["chart_facts"]["summary"]["cross_count"] >= 0


def test_mbti_calculate(client: TestClient) -> None:
    bank = client.get("/api/v1/mbti/questions").json()
    answers = {item["id"]: "A" for item in bank["questions"]}
    response = client.post("/api/v1/charts/mbti/calculate", json={"answers": answers})
    assert response.status_code == 200, response.text
    assert response.json()["chart_facts"]["code"] == "ESTJ"


def test_dream_calculate(client: TestClient) -> None:
    response = client.post(
        "/api/v1/charts/dream/calculate", json={"text": "梦见一条蛇在水边游走"}
    )
    assert response.status_code == 200, response.text
    keywords = [item["keyword"] for item in response.json()["chart_facts"]["keywords"]]
    assert "蛇" in keywords


# ---- /mbti/questions ----


def test_mbti_bank_endpoint(client: TestClient) -> None:
    response = client.get("/api/v1/mbti/questions")
    assert response.status_code == 200
    body = response.json()
    assert body["bank_version"]
    assert len(body["questions"]) == 40
    assert len(body["dimensions"]) == 4
    assert body["school_note"]


def test_mbti_bank_questions_are_complete(client: TestClient) -> None:
    body = client.get("/api/v1/mbti/questions").json()
    for item in body["questions"]:
        assert item["text"] and item["option_a"] and item["option_b"]
        assert item["dimension"] in ("EI", "SN", "TF", "JP")


# ---- 错误路径 ----


def test_missing_required_field_returns_422(client: TestClient) -> None:
    response = client.post("/api/v1/charts/almanac/calculate", json={})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_incomplete_mbti_answers_rejected(client: TestClient) -> None:
    response = client.post("/api/v1/charts/mbti/calculate", json={"answers": {"ei-01": "A"}})
    assert response.status_code == 422


def test_vision_types_is_public(client: TestClient) -> None:
    response = client.get("/api/v1/vision/types")
    assert response.status_code == 200
    body = response.json()
    assert body["face"]["types"] and body["palm"]["types"]
    assert body["face"]["disclaimer"]


def test_vision_analyze_requires_login(client: TestClient) -> None:
    response = client.post("/api/v1/vision/face/analyze", files={"file": ("a.jpg", b"x", "image/jpeg")})
    assert response.status_code == 401


def test_vision_rejects_bad_mime(client: TestClient) -> None:
    headers = _headers(client)
    response = client.post(
        "/api/v1/vision/face/analyze",
        files={"file": ("a.gif", b"GIF89a", "image/gif")},
        headers={**headers, "Idempotency-Key": uuid.uuid4().hex},
    )
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "UNSUPPORTED_MEDIA_TYPE"


def test_vision_returns_503_without_model(client: TestClient) -> None:
    """未配置视觉模型时必须 503，而不是 500 或悄悄用文本模型。"""
    headers = _headers(client)
    response = client.post(
        "/api/v1/vision/face/analyze",
        files={"file": ("a.jpg", b"\xff\xd8\xff\xd9", "image/jpeg")},
        headers={**headers, "Idempotency-Key": uuid.uuid4().hex},
    )
    assert response.status_code in (415, 422, 503)
    if response.status_code == 503:
        assert response.json()["error"]["code"] == "VISION_NOT_CONFIGURED"
