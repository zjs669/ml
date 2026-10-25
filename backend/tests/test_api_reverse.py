"""反查接口层测试：免登录、参数校验、错误码、限流。"""

from __future__ import annotations

from fastapi.testclient import TestClient

URL = "/api/v1/charts/bazi/reverse-search"


def _body(**overrides) -> dict:
    body = {
        "pillars": {"day": "辛亥"},
        "range_start": "1990-01-01",
        "range_end": "1990-12-31",
        "timezone": "Asia/Shanghai",
        "limit": 10,
    }
    body.update(overrides)
    return body


def test_reverse_search_works_without_login(client: TestClient) -> None:
    response = client.post(URL, json=_body())
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["total_matches"] > 0
    assert data["candidates"]
    assert data["algorithm_version"]
    assert data["query"]["day"] == "辛亥"


def test_illegal_pillar_returns_422(client: TestClient) -> None:
    response = client.post(URL, json=_body(pillars={"day": "甲丑"}))
    assert response.status_code == 422


def test_inconsistent_pillars_returns_400_with_hint(client: TestClient) -> None:
    response = client.post(URL, json=_body(pillars={"day": "辛亥", "hour": "甲寅"}))
    assert response.status_code == 400, response.text
    error = response.json()["error"]
    assert error["code"] == "INCONSISTENT_PILLARS"
    assert "庚" in error["message"]


def test_hour_only_returns_400(client: TestClient) -> None:
    response = client.post(URL, json=_body(pillars={"hour": "乙卯"}))
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "QUERY_TOO_LOOSE"


def test_range_over_200_years_returns_422(client: TestClient) -> None:
    response = client.post(
        URL,
        json=_body(range_start="1800-01-01", range_end="2101-01-01"),
    )
    assert response.status_code == 422


def test_rate_limit_kicks_in(client: TestClient) -> None:
    body = _body(range_start="1990-01-01", range_end="1990-01-05", limit=1)
    codes = [client.post(URL, json=body).status_code for _ in range(31)]
    assert codes[0] == 200
    assert 429 in codes
