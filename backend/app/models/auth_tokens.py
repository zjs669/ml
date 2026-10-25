"""认证相关的两本账：密码重置令牌、refresh 会话。

为什么需要它们（见 docs/查漏补缺与安全加固.md 的 D2/D3）：

- `password_reset_tokens`：忘记密码走「一次性令牌」，库里只存 `sha256(token)`，
  即使库被拖走也无法直接拿去重置；用过即废、过期即废、一次性只留最近几枚。
- `refresh_tokens`：JWT 本身无状态，无法「用过即废」。这里给每枚 refresh 建一行，
  刷新时旧行标记 `used_at`，再次出现同一 jti 即视为重放，整族（family_id）作废。
  同时登出/改密可以只作废该用户的行，不必把所有设备一起踢掉。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String
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
