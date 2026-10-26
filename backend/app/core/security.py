"""密码哈希与 JWT 签发/校验。

设计要点（见 docs/archive/查漏补缺与安全加固.md）：
- 密码只存 **Argon2id** 哈希，可调参，绝不落明文；登录时若参数变化自动 rehash。
- access token 短效（默认 15 分钟），只放 sub/typ/ver/iss/aud，不放邮箱等个人信息。
- refresh token 7 天，用 `users.token_version` 做全局撤销，用 `refresh_tokens.jti`
  做单枚轮换：刷新一次就废一枚，jti 重放视为被盗，整族（family_id）作废。
- `iss` / `aud` 强制校验：别的系统用同一密钥签的 token 不会被当成本站用户。
"""

from __future__ import annotations

import hashlib
import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.core.config import settings
from app.core.errors import Unauthorized

_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)
ALGORITHM = "HS256"

#: 签发方与受众，两处都要与 decode_token 的校验参数保持一致
ISSUER = "xuanshu"
AUDIENCE = "xuanshu-api"
#: 允许的时钟偏移，避免客户端/服务端几秒误差导致刚签发的 token 被判过期
LEEWAY_SECONDS = 5

TokenType = Literal["access", "refresh"]

#: 常见弱口令（够挡住「Password123」之外的明显弱口令，不追求字典完备）
COMMON_PASSWORDS = {
    "12345678",
    "123456789",
    "1234567890",
    "password",
    "password1",
    "password123",
    "qwerty123",
    "abc12345",
    "a1234567",
    "iloveyou",
    "admin123",
    "xuanshu123",
    "woaini1314",
}

_HAS_LETTER = re.compile(r"[A-Za-z]")
_HAS_DIGIT = re.compile(r"\d")


@dataclass(frozen=True)
class IssuedTokens:
    """一次签发产出的三样东西：access、refresh、以及 refresh 的账本信息。"""

    access_token: str
    refresh_token: str
    refresh_jti: str
    family_id: str
    refresh_expires_at: datetime


# ---- 密码 ----


def hash_password(raw: str) -> str:
    return _hasher.hash(raw)


def verify_password(raw: str, hashed: str | None) -> bool:
    if not hashed:
        return False
    try:
        return _hasher.verify(hashed, raw)
    except (VerifyMismatchError, InvalidHashError):
        return False


def needs_rehash(hashed: str) -> bool:
    try:
        return _hasher.check_needs_rehash(hashed)
    except InvalidHashError:
        return True


def validate_password_strength(password: str, *, email: str | None = None) -> str:
    """注册与重置共用的强度校验；返回原密码，异常由 pydantic 转成 422。

    规则刻意保守但可解释：长度 ≥8、字母与数字都要有、不在常见弱口令表、
    不包含邮箱 @ 前的部分（避免「邮箱即密码」）。
    """
    value = password.strip()
    if len(value) < 8:
        raise ValueError("密码至少 8 位")
    if not (_HAS_LETTER.search(value) and _HAS_DIGIT.search(value)):
        raise ValueError("密码需同时包含字母与数字")
    if value.lower() in COMMON_PASSWORDS:
        raise ValueError("该密码过于常见，请换一个")
    if email:
        local = email.split("@", 1)[0].strip().lower()
        if len(local) >= 4 and local in value.lower():
            raise ValueError("密码不能包含邮箱名")
    return value


# ---- 令牌 ----


def hash_token(raw: str) -> str:
    """重置令牌落库前先哈希：库被拖走也拿不到可用的明文令牌。"""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def new_reset_token() -> tuple[str, str]:
    """返回 (明文令牌, sha256)；明文只出现在邮件里一次。"""
    token = secrets.token_urlsafe(32)
    return token, hash_token(token)


def _encode(
    subject: str,
    token_type: TokenType,
    version: int,
    ttl: timedelta,
    *,
    jti: str | None = None,
) -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    token_id = jti or uuid.uuid4().hex
    payload: dict[str, Any] = {
        "sub": subject,
        "typ": token_type,
        "ver": version,
        "iss": ISSUER,
        "aud": AUDIENCE,
        "iat": int(now.timestamp()),
        "nbf": int(now.timestamp()),
        "exp": int((now + ttl).timestamp()),
        "jti": token_id,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM), token_id


def create_access_token(user_id: int, token_version: int) -> str:
    token, _ = _encode(
        str(user_id), "access", token_version, timedelta(minutes=settings.access_token_ttl_minutes)
    )
    return token


def issue_tokens(user_id: int, token_version: int, *, family_id: str | None = None) -> IssuedTokens:
    """签发一对令牌；refresh 带 jti，调用方负责把 jti 写进 `refresh_tokens`。"""
    access = create_access_token(user_id, token_version)
    ttl = timedelta(days=settings.refresh_token_ttl_days)
    refresh, jti = _encode(str(user_id), "refresh", token_version, ttl)
    return IssuedTokens(
        access_token=access,
        refresh_token=refresh,
        refresh_jti=jti,
        family_id=family_id or uuid.uuid4().hex,
        refresh_expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + ttl,
    )


def create_refresh_token(user_id: int, token_version: int) -> str:
    return _encode(str(user_id), "refresh", token_version, timedelta(days=settings.refresh_token_ttl_days))[0]


def decode_token(token: str, expected: TokenType) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[ALGORITHM],
            audience=AUDIENCE,
            issuer=ISSUER,
            leeway=LEEWAY_SECONDS,
            options={"require": ["exp", "iat", "sub", "typ", "iss", "aud"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise Unauthorized("登录已过期，请重新登录") from exc
    except jwt.PyJWTError as exc:
        raise Unauthorized() from exc
    if payload.get("typ") != expected:
        raise Unauthorized("令牌类型不匹配")
    return payload


def access_ttl_seconds() -> int:
    return settings.access_token_ttl_minutes * 60


def refresh_ttl_seconds() -> int:
    return settings.refresh_token_ttl_days * 24 * 3600
