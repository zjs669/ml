"""端点路径必须与合并前一致。

本轮把 `feedback.py` / `mbti.py` 并进了 `me.py` / `meta.py`，做法是
「保留独立 sub-router，由 main.py 单独注册」。这种合并很容易出错 ——
如果装饰器写成 `@router.post` 而不是 `@feedback_router.post`，
端点就会悄悄挂到 `/me` 前缀下，路径从 `/feedback` 变成 `/me/feedback`。

全量测试当时**没有发现**这个问题（只有 OpenAPI 快照能看出来），
所以这里把关键路径写死成断言：合并文件可以，改 URL 不行。
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_core_paths_unchanged(client: TestClient) -> None:
    """这些路径是前端与外部脚本直接调用的，合并文件时不得漂移。"""
    expected = {
        "/api/v1/feedback": "post",
        "/api/v1/mbti/questions": "get",
        "/api/v1/meta/about": "get",
        "/api/v1/meta/domains": "get",
        "/api/v1/meta/conventions": "get",
        "/api/v1/meta/llm-status": "get",
        "/api/v1/knowledge/search": "get",
        "/api/v1/knowledge/stats": "get",
        "/api/v1/charts/bazi/reverse-search": "post",
        "/api/v1/me/usage": "get",
        "/api/v1/me/orders": "get",
        "/api/v1/me/ledger": "get",
        "/api/v1/me/consents": "get",
        "/api/v1/me/export": "get",
    }
    spec = client.app.openapi()  # type: ignore[attr-defined]
    paths = spec["paths"]
    missing = sorted(p for p in expected if p not in paths)
    assert not missing, f"这些路径不存在了（合并时挂错了 router？）：{missing}"
    for path, method in expected.items():
        assert method in paths[path], f"{path} 缺少 {method.upper()} 方法"


def test_no_path_gained_unexpected_prefix(client: TestClient) -> None:
    """根级端点不能被某个带 prefix 的模块吞掉。

    典型错误：把 `@router.post` 写进有 `prefix="/me"` 的模块，
    端点就变成 `/me/feedback` —— 前端调 `/feedback` 会 404。
    """
    spec = client.app.openapi()  # type: ignore[attr-defined]
    paths = set(spec["paths"])
    leaked = sorted(
        p
        for p in paths
        if p.startswith("/api/v1/me/") and p.split("/")[-1] in {"feedback"}
    )
    assert not leaked, f"这些根级端点被 /me 前缀吞了：{leaked}"


def test_list_endpoints_expose_bounded_limit(client: TestClient) -> None:
    """列表接口必须带 limit 且有上限，不能全量返回。

    数据量小的时候「全量返回」看不出问题，但响应体会随使用时长线性膨胀。
    这里锁住两点：参数存在、上限被服务端强制。
    """
    spec = client.app.openapi()
    for path in (
        "/api/v1/charts/{chart_id}/reports",
        "/api/v1/reports/{report_id}/followups",
    ):
        params = spec["paths"][path]["get"].get("parameters", [])
        limits = [p for p in params if p["name"] == "limit"]
        assert limits, f"{path} 没有 limit 参数"
        schema = limits[0]["schema"]
        assert schema.get("maximum") == 100, f"{path} 的 limit 上限应为 100"
        assert schema.get("minimum") == 1, f"{path} 的 limit 下限应为 1"


def test_limit_above_maximum_is_rejected(auth_client) -> None:
    """超过上限应返回 422，而不是被静默截断或放行。

    必须带登录态：这两个端点先过鉴权再校验参数，匿名请求会先吃 401，
    测不到 limit 的约束。
    """
    client, headers = auth_client
    response = client.get("/api/v1/charts/1/reports?limit=1000", headers=headers)
    assert response.status_code == 422