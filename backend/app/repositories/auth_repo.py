"""认证令牌的数据访问层：密码重置令牌、refresh 会话。

两个约定：
- 所有查询都带 `user_id` 条件，避免「拿到 jti 就能操作别人会话」；
- 只做数据访问，过期判断与业务分支放在 `api/v1/auth.py`，方便测试。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.models.auth_tokens import PasswordResetToken, RefreshToken


# ---- 密码重置令牌 ----


def create_reset_token(
    session: Session,
    *,
    user_id: int,
    token_hash: str,
    expires_at: datetime,
    requested_ip: str | None,
) -> PasswordResetToken:
    row = PasswordResetToken(
        user_id=user_id,
        token_hash=token_hash,
        expires_at=expires_at,
        requested_ip=requested_ip,
        created_at=utcnow(),
    )
    session.add(row)
    session.flush()
    return row


def get_reset_token(session: Session, token_hash: str) -> PasswordResetToken | None:
    return session.scalar(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash)
    )


def list_active_reset_tokens(session: Session, user_id: int) -> list[PasswordResetToken]:
    """该用户尚未使用且未过期的令牌，按创建时间升序。"""
    return list(
        session.scalars(
            select(PasswordResetToken)
            .where(
                PasswordResetToken.user_id == user_id,
                PasswordResetToken.used_at.is_(None),
                PasswordResetToken.expires_at > utcnow(),
            )
            .order_by(PasswordResetToken.created_at.asc())
        ).all()
    )


def consume_reset_token(session: Session, row: PasswordResetToken) -> None:
    row.used_at = utcnow()
    session.add(row)


def purge_other_reset_tokens(session: Session, *, user_id: int, keep_id: int) -> int:
    """重置成功后，把该用户其余未使用的令牌一并作废（防多封邮件多把钥匙）。"""
    rows = list_active_reset_tokens(session, user_id)
    removed = 0
    for row in rows:
        if row.id == keep_id:
            continue
        row.used_at = utcnow()
        session.add(row)
        removed += 1
    return removed


def delete_expired_reset_tokens(session: Session, *, before: datetime) -> int:
    result = session.execute(
        delete(PasswordResetToken).where(PasswordResetToken.expires_at < before)
    )
    return int(result.rowcount or 0)


# ---- refresh 会话 ----


def create_refresh_token(
    session: Session,
    *,
    jti: str,
    user_id: int,
    family_id: str,
    expires_at: datetime,
    user_agent: str | None,
) -> RefreshToken:
    row = RefreshToken(
        jti=jti,
        user_id=user_id,
        family_id=family_id,
        expires_at=expires_at,
        user_agent=(user_agent or "")[:255] or None,
        created_at=utcnow(),
    )
    session.add(row)
    session.flush()
    return row


def get_refresh_token(session: Session, jti: str) -> RefreshToken | None:
    return session.scalar(select(RefreshToken).where(RefreshToken.jti == jti))


def mark_refresh_used(session: Session, row: RefreshToken) -> None:
    row.used_at = utcnow()
    session.add(row)


def revoke_refresh_family(session: Session, family_id: str) -> int:
    """检测到重放：整条登录链作废。"""
    rows = list(session.scalars(select(RefreshToken).where(RefreshToken.family_id == family_id)).all())
    now = utcnow()
    changed = 0
    for row in rows:
        if row.revoked_at is None:
            row.revoked_at = now
            session.add(row)
            changed += 1
    return changed


def revoke_all_refresh_tokens(session: Session, user_id: int) -> int:
    """登出全部设备 / 修改密码 / 注销账号时调用。"""
    rows = list(
        session.scalars(
            select(RefreshToken).where(
                RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None)
            )
        ).all()
    )
    now = utcnow()
    for row in rows:
        row.revoked_at = now
        session.add(row)
    return len(rows)


def count_active_sessions(session: Session, user_id: int) -> int:
    """当前仍可用的 refresh 会话数（登出全部设备时用于回显）。"""
    total = session.scalar(
        select(func.count())
        .select_from(RefreshToken)
        .where(
            RefreshToken.user_id == user_id,
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > utcnow(),
        )
    )
    return int(total or 0)
