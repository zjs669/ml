"""极简进程内限流（MVP 用）。

不引入 Redis 的前提下，用滑动窗口计数即可挡住登录爆破与报告接口刷量。
多进程部署时每个 worker 独立计数，等第二阶段接 Redis 再统一。
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import Request

from app.core.config import settings
from app.core.errors import AppError

_LOCK = Lock()
_BUCKETS: dict[str, deque[float]] = defaultdict(deque)


class RateLimited(AppError):
    def __init__(self, retry_after: int) -> None:
        super().__init__(
            "RATE_LIMITED",
            f"操作过于频繁，请 {retry_after} 秒后再试",
            status_code=429,
        )
        self.retry_after = retry_after


def hit(key: str, *, limit: int, window_seconds: int) -> None:
    # 开发/演示环境可以关掉：反复跑 smoke_e2e 时，注册限流（5 次/小时/IP）
    # 会把脚本自己挡住。生产必须保持开启（默认为 True）。
    if not settings.ratelimit_enabled:
        return
    now = time.monotonic()
    with _LOCK:
        bucket = _BUCKETS[key]
        while bucket and now - bucket[0] > window_seconds:
            bucket.popleft()
        if len(bucket) >= limit:
            retry = int(window_seconds - (now - bucket[0])) + 1
            raise RateLimited(retry)
        bucket.append(now)


def client_key(request: Request, scope: str) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "unknown")
    return f"{scope}:{ip}"


def reset() -> None:
    """测试用：清空所有计数。"""
    with _LOCK:
        _BUCKETS.clear()
