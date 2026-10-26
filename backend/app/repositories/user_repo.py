"""用户、凭证与登录会话的数据访问层。所有 owner 过滤都收敛在这一层。

## 用户
get_by_email / get_active / create / record_consent / bump_token_version / soft_delete

## 密码重置令牌 / refresh 会话
库里只存 sha256；refresh 每枚一行，用过即废，重放同一 jti 作废整族。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.models import (
    EmailVerificationCode,
    PasswordResetToken,
    RefreshToken,
    User,
    UserConsent,
)

# ------------------------------------------------------------------ 用户


"""用户与同意记录的数据访问层。所有 owner 过滤都收敛在这一层。"""





def get_by_email(session: Session, email: str) -> User | None:
    return session.scalar(select(User).where(User.email == email.lower()))


def get_active(session: Session, user_id: int) -> User | None:
    user = session.get(User, user_id)
    if user is None or user.status != "active" or user.deleted_at is not None:
        return None
    return user


def create(session: Session, *, email: str, password_hash: str, display_name: str | None) -> User:
    user = User(
        email=email.lower(),
        password_hash=password_hash,
        display_name=display_name or email.split("@")[0][:80],
        status="active",
        token_version=0,
    )
    session.add(user)
    session.flush()
    return user


def record_consent(session: Session, *, user_id: int, doc_type: str, doc_version: str) -> UserConsent:
    consent = UserConsent(user_id=user_id, doc_type=doc_type, doc_version=doc_version, consent_at=utcnow())
    session.add(consent)
    return consent


def bump_token_version(session: Session, user: User) -> None:
    user.token_version += 1
    session.add(user)


def soft_delete(session: Session, user: User) -> None:
    """软删账号：30 天后由清理任务物理删除，期间可申诉恢复。"""
    user.status = "pending_deletion"
    user.deleted_at = utcnow()
    user.email = None  # 释放唯一约束，同时停止用于任何联系
    user.password_hash = None
    session.add(user)


# ------------------------------------------------------- 密码重置令牌 / 会话
#
# 认证令牌的数据访问层：密码重置令牌、refresh 会话。
# 
# 两个约定：
# - 所有查询都带 `user_id` 条件，避免「拿到 jti 就能操作别人会话」；
# - 只做数据访问，过期判断与业务分支放在 `api/v1/auth.py`，方便测试。


"""认证令牌的数据访问层：密码重置令牌、refresh 会话。

两个约定：
- 所有查询都带 `user_id` 条件，避免「拿到 jti 就能操作别人会话」；
- 只做数据访问，过期判断与业务分支放在 `api/v1/auth.py`，方便测试。
"""






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


# ------------------------------------------------------------ 邮箱验证码


def create_verification_code(
    session: Session,
    *,
    email: str,
    purpose: str,
    code_hash: str,
    expires_at: datetime,
    requested_ip: str | None,
) -> EmailVerificationCode:
    """落一条验证码记录。调用方负责先作废同类旧码。"""
    row = EmailVerificationCode(
        email=email.strip().lower(),
        purpose=purpose,
        code_hash=code_hash,
        expires_at=expires_at,
        requested_ip=requested_ip,
    )
    session.add(row)
    session.flush()
    return row


def list_active_verification_codes(
    session: Session, *, email: str, purpose: str
) -> list[EmailVerificationCode]:
    """该邮箱该用途下仍然可用的码，按创建时间升序（旧 → 新）。"""
    return list(
        session.scalars(
            select(EmailVerificationCode)
            .where(
                EmailVerificationCode.email == email.strip().lower(),
                EmailVerificationCode.purpose == purpose,
                EmailVerificationCode.used_at.is_(None),
            )
            .order_by(EmailVerificationCode.created_at.asc())
        )
    )


def find_verification_code(
    session: Session, *, email: str, purpose: str, code_hash: str, now: datetime
) -> EmailVerificationCode | None:
    """按 (邮箱, 用途, 码哈希) 找一条未使用且未过期的记录。

    不匹配具体码是为了让调用方能区分「码错了」和「码过期了」：
    这里只按哈希查，查不到再由调用方判断是不是过期。
    """
    return session.scalar(
        select(EmailVerificationCode)
        .where(
            EmailVerificationCode.email == email.strip().lower(),
            EmailVerificationCode.purpose == purpose,
            EmailVerificationCode.code_hash == code_hash,
            EmailVerificationCode.used_at.is_(None),
            EmailVerificationCode.expires_at > now,
        )
        .order_by(EmailVerificationCode.created_at.desc())
    )


def consume_verification_code(session: Session, row: EmailVerificationCode) -> None:
    """标记已使用。一次性，用完即废。"""
    row.used_at = utcnow()
    session.add(row)


def bump_verification_attempts(session: Session, row: EmailVerificationCode) -> int:
    """输错计数 +1，返回当前次数。调用方据此决定是否作废。"""
    row.attempts += 1
    session.add(row)
    return row.attempts


def invalidate_verification_codes(
    session: Session, *, email: str, purpose: str, keep_id: int | None = None
) -> int:
    """作废该邮箱该用途下的全部未用码（可保留一条）。返回作废条数。"""
    rows = list_active_verification_codes(session, email=email, purpose=purpose)
    count = 0
    for row in rows:
        if keep_id is not None and row.id == keep_id:
            continue
        row.used_at = utcnow()
        session.add(row)
        count += 1
    return count


def purge_expired_verification_codes(session: Session, *, before: datetime) -> int:
    """清理过期记录（运维任务用）。"""
    result = session.execute(
        delete(EmailVerificationCode).where(EmailVerificationCode.expires_at < before)
    )
    return int(result.rowcount or 0)
