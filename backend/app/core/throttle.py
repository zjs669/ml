"""进程内限流与账号锁定。

两个模块放一起的原因：它们解决的是同一类问题 —— **单机进程内计数**，
取舍也完全一样（单机内测够用，多 worker / 多机必须换 Redis 或落库）。
分开维护时，改一处取舍说明就要同步另一处，且调用方要记住两个模块名。

## 限流（`hit` / `client_key`）
按 key 的滑动窗口计数，挡住登录爆破与报告接口刷量。

## 账号锁定（`check_locked` / `note_failure` / `reset`）
为什么不能只靠 IP 限流：撞库是分布式的，攻击者每换一个出口 IP 就能绕开
`hit(client_key(...))`，但**目标账号**是固定的。所以这里按邮箱计数。
连续失败达到 `LOGIN_MAX_FAILURES` 后锁定 `LOGIN_LOCK_MINUTES`，
每再触发一轮锁定时长翻倍（上限 24 小时），成功登录即清零。
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass
from threading import Lock

from fastapi import Request

from app.core.config import settings
from app.core import metrics
from app.core.errors import AppError

MAX_LOCK_MINUTES = 24 * 60


# --------------------------------------------------------------- 限流


class RateLimited(AppError):
    def __init__(self, retry_after: int) -> None:
        super().__init__(
            "RATE_LIMITED",
            f"操作过于频繁，请 {retry_after} 秒后再试",
            status_code=429,
        )
        self.retry_after = retry_after


_LIMIT_LOCK = Lock()
_BUCKETS: dict[str, deque[float]] = defaultdict(deque)


def hit(key: str, *, limit: int, window_seconds: int) -> None:
    # 开发/演示环境可以关掉：反复跑 smoke_e2e 时，注册限流（5 次/小时/IP）
    # 会把脚本自己挡住。生产必须保持开启（默认为 True）。
    if not settings.ratelimit_enabled:
        return
    now = time.monotonic()
    with _LIMIT_LOCK:
        bucket = _BUCKETS[key]
        while bucket and now - bucket[0] > window_seconds:
            bucket.popleft()
        if len(bucket) >= limit:
            retry = int(window_seconds - (now - bucket[0])) + 1
            metrics.inc("rate_limit_hits_total", {"scope": "ip"})
            raise RateLimited(retry)
        bucket.append(now)


def client_key(request: Request, scope: str) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "unknown")
    return f"{scope}:{ip}"


def reset() -> None:
    """测试用：清空所有限流计数。"""
    with _LIMIT_LOCK:
        _BUCKETS.clear()


# ----------------------------------------------------------- 账号锁定


class AccountLocked(AppError):
    """账号被临时锁定。用 429 与限流保持一致，前端按 retry_after 提示。"""

    def __init__(self, retry_after: int) -> None:
        minutes = max(retry_after // 60, 1)
        super().__init__(
            "ACCOUNT_LOCKED",
            f"该账号连续登录失败次数过多，已锁定，请约 {minutes} 分钟后再试",
            status_code=429,
        )
        self.retry_after = retry_after


@dataclass
class _State:
    failures: int = 0
    locked_until: float = 0.0
    lock_round: int = 0


_STATE_LOCK = Lock()
_STATES: dict[str, _State] = {}


def _key(email: str) -> str:
    return email.strip().lower()


def check_locked(email: str) -> None:
    """登录前先问一次：该账号是否还在锁定期内。"""
    now = time.monotonic()
    with _STATE_LOCK:
        state = _STATES.get(_key(email))
        if state and state.locked_until > now:
            metrics.inc("rate_limit_hits_total", {"scope": "account"})
            raise AccountLocked(int(state.locked_until - now) + 1)


def note_failure(email: str) -> None:
    """记一次失败；达到阈值就锁定，并按轮次指数退避。"""
    now = time.monotonic()
    with _STATE_LOCK:
        state = _STATES.setdefault(_key(email), _State())
        state.failures += 1
        if state.failures < settings.login_max_failures:
            return
        state.failures = 0
        state.lock_round += 1
        minutes = min(settings.login_lock_minutes * (2 ** (state.lock_round - 1)), MAX_LOCK_MINUTES)
        state.locked_until = now + minutes * 60


def unlock(email: str) -> None:
    """登录成功或密码重置成功后清零。"""
    with _STATE_LOCK:
        _STATES.pop(_key(email), None)


def reset_all() -> None:
    """测试用：清空全部锁定状态。"""
    with _STATE_LOCK:
        _STATES.clear()
