"""认证相关的两本账：密码重置令牌、refresh 会话。

为什么需要它们：

- `password_reset_tokens`：忘记密码走「一次性令牌」，库里只存 `sha256(token)`，
  即使库被拖走也无法直接拿去重置；用过即废、过期即废、一次性只留最近几枚。
- `refresh_tokens`：JWT 本身无状态，无法「用过即废」。这里给每枚 refresh 建一行，
  刷新时旧行标记 `used_at`，再次出现同一 jti 即视为重放，整族（family_id）作废。
  同时登出/改密可以只作废该用户的行，不必把所有设备一起踢掉。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import utcnow
from app.models.base import Base


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"
    __table_args__ = (
        Index("idx_reset_user_created", "user_id", "created_at"),
        Index("idx_reset_expires", "expires_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    #: 只存 sha256(明文 token)，明文只在邮件里出现一次
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    requested_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    __table_args__ = (
        Index("idx_refresh_user", "user_id"),
        Index("idx_refresh_family", "family_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    jti: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    #: 同一条登录链上的所有 refresh 共享一个 family_id，重放时整族作废
    family_id: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class EmailVerificationCode(Base):
    """邮箱验证码（注册 / 找回密码共用）。

    为什么用验证码而不是只有重置链接：
    链接在手机与电脑之间转移不方便，而验证码可以手输。两者并存 ——
    验证码用于「本人在某个设备上操作」，链接用于「换设备继续」。

    安全约定：
    - 库里只存 `sha256(邮箱 + 验证码)`，明文只出现在邮件里；
    - 6 位数字，10 分钟过期（`verification_code_ttl_minutes`）；
    - 同一邮箱同一用途只保留最近 N 条，用完即标记 `used_at`；
    - 连续输错达到阈值即作废该码（`attempts` 计数），防止暴力穷举。
    """

    __tablename__ = "email_verification_codes"
    __table_args__ = (
        Index("idx_code_email_purpose", "email", "purpose", "created_at"),
        Index("idx_code_expires", "expires_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    #: 目标邮箱（小写）。不建外键：注册场景下用户还不存在
    email: Mapped[str] = mapped_column(String(190), nullable=False)
    #: reset_password / register / change_email
    purpose: Mapped[str] = mapped_column(String(32), nullable=False, default="reset_password")
    #: sha256(email + ":" + code)，明文只在邮件里出现一次
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    #: 已输错次数；达到上限即作废，不等待自然过期
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    requested_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
