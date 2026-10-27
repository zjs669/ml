"""指标采集与 Prometheus 暴露。

三条必须守住的约束：

1. **标签基数有界**。路由按模板打标签，/charts/123 必须归到 /charts/{chart_id}，
   否则每个 id 都是一个新时间序列，内存会随用户数一直涨。
2. **/metrics 不泄露用户数据**。只有路由模板、状态码、域名这类结构信息。
3. **采集失败不影响主链路**。gauge 取值要查数据库，它挂了不能让 /metrics 500。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core import metrics


@pytest.fixture(autouse=True)
def clean_metrics():
    """每个用例前清空指标，避免用例之间互相污染。"""
    metrics.reset()
    yield
    metrics.reset()


def test_counter_increments_and_renders() -> None:
    metrics.inc("test_total", {"result": "ok"})
    metrics.inc("test_total", {"result": "ok"})
    metrics.inc("test_total", {"result": "error"})

    text = metrics.render()
    assert 'test_total{result="ok"} 2' in text
    assert 'test_total{result="error"} 1' in text
    assert "# TYPE test_total counter" in text


def test_histogram_renders_buckets_sum_count() -> None:
    metrics.observe("http_request_duration_seconds", 0.03, {"route": "/x"})

    text = metrics.render()
    assert 'http_request_duration_seconds_bucket{route="/x",le="0.025"} 0' in text
    assert 'http_request_duration_seconds_bucket{route="/x",le="0.05"} 1' in text
    assert 'http_request_duration_seconds_bucket{route="/x",le="+Inf"} 1' in text
    assert 'http_request_duration_seconds_count{route="/x"} 1' in text
    assert 'http_request_duration_seconds_sum{route="/x"} 0.03' in text


def test_histogram_buckets_differ_by_metric_prefix() -> None:
    """排盘是毫秒级、请求是秒级，桶边界必须分开，不能共用一套。"""
    metrics.observe("chart_generate_duration_seconds", 0.002, {"domain": "bazi"})
    text = metrics.render()

    assert 'chart_generate_duration_seconds_bucket{domain="bazi",le="0.001"} 0' in text
    assert 'chart_generate_duration_seconds_bucket{domain="bazi",le="0.005"} 1' in text


def test_gauge_supplier_failure_does_not_break_render() -> None:
    """gauge 取值要查数据库，它挂了不能让整个 /metrics 500。"""

    def _boom() -> float:
        raise RuntimeError("数据库连不上")

    metrics.register_gauge("broken_gauge", "故意失败的 gauge", _boom)
    text = metrics.render()
    assert "broken_gauge" not in text

    metrics.inc("still_alive_total")
    assert "still_alive_total 1" in metrics.render()


def test_metrics_endpoint_returns_prometheus_text(client: TestClient) -> None:
    client.post(
        "/api/v1/charts/bazi/calculate",
        json={"birth_datetime": "1990-05-20T12:00:00", "timezone": "Asia/Shanghai"},
    )
    response = client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain; version=0.0.4")

    body = response.text
    assert "chart_generate_total" in body
    assert "http_requests_total" in body
    assert "db_pool_in_use" in body


def test_route_label_uses_template_not_path(client: TestClient) -> None:
    """/charts/123 必须归到模板 /charts/{chart_id}，否则标签基数无界。"""
    client.get("/api/v1/charts/999999")

    body = client.get("/metrics").text
    assert 'route="/charts/{chart_id}"' in body
    assert 'route="/charts/999999"' not in body


def test_metrics_exposes_no_user_data(client: TestClient) -> None:
    """指标里只能有结构信息，不能出现邮箱、原文、token。"""
    import uuid

    email = f"metrics_{uuid.uuid4().hex[:8]}@example.com"
    client.post("/api/v1/auth/register", json={"email": email, "password": "Passw0rd123"})

    body = client.get("/metrics").text
    assert email not in body
    assert "Passw0rd123" not in body
    assert "Bearer" not in body


def test_metrics_not_in_openapi_schema(client: TestClient) -> None:
    """/metrics 不挂进 OpenAPI：它是运维接口，不该出现在给前端看的文档里。"""
    schema = client.get("/openapi.json").json()
    assert "/metrics" not in schema["paths"]
