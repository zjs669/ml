"""请求依赖：解析 access token、取当前用户、可选用户。"""

from __future__ import annotations

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.errors import Unauthorized
from app.core.security import decode_token
from app.models import User
from app.repositories import user_repo


def _bearer_token(request: Request) -> str | None:
    header = request.headers.get("authorization")
    if not header:
        return None
    parts = header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1]


def get_current_user(
    request: Request,
    session: Session = Depends(get_session),
) -> User:
    token = _bearer_token(request)
    if not token:
        raise Unauthorized("缺少访问令牌，请先登录")
    payload = decode_token(token, "access")
    try:
        user_id = int(payload["sub"])
    except (KeyError, TypeError, ValueError) as exc:
        raise Unauthorized("令牌内容不合法") from exc
    user = user_repo.get_active(session, user_id)
    if user is None:
        raise Unauthorized("账号不可用或已注销")
    if int(payload.get("ver", -1)) != user.token_version:
        raise Unauthorized("登录状态已失效，请重新登录")
    request.state.user_id = user.id
    return user


def get_optional_user(
    request: Request,
    session: Session = Depends(get_session),
) -> User | None:
    try:
        return get_current_user(request, session)
    except Unauthorized:
        return None
