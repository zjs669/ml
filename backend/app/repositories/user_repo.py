"""用户与同意记录的数据访问层。所有 owner 过滤都收敛在这一层。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.models.user import User, UserConsent


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
