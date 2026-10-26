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
