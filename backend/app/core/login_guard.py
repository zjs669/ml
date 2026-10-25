"""按账号的登录失败锁定（进程内）。

为什么不能只靠 IP 限流：撞库是分布式的，攻击者每换一个出口 IP 就能绕开
`ratelimit.hit(client_key(...))`，但**目标账号**是固定的。所以这里按邮箱计数。

实现是进程内字典，和 `core/ratelimit.py` 同样的取舍：
- 单机内测够用；
- 多 worker / 多机部署时必须换成 Redis 或数据库计数，否则每个进程各算一份。

锁定策略：连续失败达到 `LOGIN_MAX_FAILURES` 后锁定 `LOGIN_LOCK_MINUTES`；
每再触发一轮锁定，时长翻倍（上限 24 小时），成功登录即清零。
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from threading import Lock

from app.core.config import settings
from app.core.errors import AppError

MAX_LOCK_MINUTES = 24 * 60


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


_LOCK = Lock()
_STATES: dict[str, _State] = {}


def _key(email: str) -> str:
    return email.strip().lower()


def check_locked(email: str) -> None:
    """登录前先问一次：该账号是否还在锁定期内。"""
    now = time.monotonic()
    with _LOCK:
        state = _STATES.get(_key(email))
        if state and state.locked_until > now:
            raise AccountLocked(int(state.locked_until - now) + 1)


def note_failure(email: str) -> None:
    """记一次失败；达到阈值就锁定，并按轮次指数退避。"""
    now = time.monotonic()
    with _LOCK:
        state = _STATES.setdefault(_key(email), _State())
        state.failures += 1
        if state.failures < settings.login_max_failures:
            return
        state.failures = 0
        state.lock_round += 1
        minutes = min(settings.login_lock_minutes * (2 ** (state.lock_round - 1)), MAX_LOCK_MINUTES)
        state.locked_until = now + minutes * 60


def reset(email: str) -> None:
    """登录成功或密码重置成功后清零。"""
    with _LOCK:
        _STATES.pop(_key(email), None)


def reset_all() -> None:
    """测试用：清空全部状态。"""
    with _LOCK:
        _STATES.clear()
