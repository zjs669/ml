"""认证接口：注册 / 登录 / 刷新 / 登出 / 忘记密码 / 会话管理。

安全约定（详见 docs/查漏补缺与安全加固.md）：
- 登录失败既受 IP 限流，也受**按账号**的失败锁定（`core/login_guard.py`）；
- 登录成功时若 Argon2id 参数已升级，自动 rehash 写回，老密码无需用户干预；
- refresh 走**服务端轮换**：每枚 refresh 落一行 `refresh_tokens`，用过即废，
  重放同一 jti 视为被盗，整族作废并要求重新登录；
- 忘记密码对「邮箱存在 / 不存在」返回完全相同的响应，杜绝账号枚举。
"""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core import login_guard, mailer
from app.core.config import settings
from app.core.db import get_session, utcnow
from app.core.errors import AppError, Conflict, Unauthorized
from app.core.ratelimit import client_key, hit
from app.core.security import (
    access_ttl_seconds,
    decode_token,
    hash_password,
    hash_token,
    issue_tokens,
    needs_rehash,
    new_reset_token,
    refresh_ttl_seconds,
    verify_password,
)
from app.models.billing import AuditLog
from app.models.user import User
from app.repositories import auth_repo, user_repo
from app.schemas.auth import (
    ForgotPasswordIn,
    ForgotPasswordOut,
    LoginIn,
    RegisterIn,
    ResetPasswordIn,
    ResetPasswordOut,
    SessionOut,
    TokenOut,
    UserOut,
)

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE_PATH = f"{settings.api_prefix}/auth"

#: 申请重置的统一文案：不区分邮箱是否存在
FORGOT_MESSAGE = "如果该邮箱已注册，我们已发送重置链接；链接 30 分钟内有效，请检查收件箱与垃圾箱。"


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    return request.client.host[:64] if request.client else None


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=token,
        max_age=refresh_ttl_seconds(),
        httponly=True,
        samesite="lax",
        secure=settings.is_production,
        path=REFRESH_COOKIE_PATH,
    )


def _issue(
    response: Response,
    user: User,
    session: Session,
    request: Request,
    *,
    family_id: str | None = None,
) -> TokenOut:
    """签发一对令牌，并把 refresh 的 jti 记进账本（登出/轮换据此判断）。

    `family_id` 在刷新时必须原样传下去：同一条登录链共用一族，
    否则重放检测只能废掉旧的一枚，新的一枚照旧能用。
    """
    tokens = issue_tokens(user.id, user.token_version, family_id=family_id)
    auth_repo.create_refresh_token(
        session,
        jti=tokens.refresh_jti,
        user_id=user.id,
        family_id=tokens.family_id,
        expires_at=tokens.refresh_expires_at,
        user_agent=request.headers.get("user-agent"),
    )
    session.commit()
    _set_refresh_cookie(response, tokens.refresh_token)
    return TokenOut(
        access_token=tokens.access_token,
        expires_in=access_ttl_seconds(),
        user=UserOut.model_validate(user),
    )


def _audit(session: Session, action: str, *, user_id: int | None, detail: dict | None = None) -> None:
    session.add(
        AuditLog(
            actor=f"user:{user_id}" if user_id else "anonymous",
            action=action,
            target_type="user",
            target_id=str(user_id) if user_id else None,
            detail_json=detail or {},
        )
    )


@router.post("/register", response_model=TokenOut, status_code=201)
def register(
    payload: RegisterIn,
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
) -> TokenOut:
    hit(client_key(request, "register"), limit=5, window_seconds=3600)
    if user_repo.get_by_email(session, payload.email) is not None:
        raise Conflict("EMAIL_TAKEN", "该邮箱已注册，请直接登录或找回密码")
    try:
        user = user_repo.create(
            session,
            email=payload.email,
            password_hash=hash_password(payload.password),
            display_name=payload.display_name,
        )
        user_repo.record_consent(
            session, user_id=user.id, doc_type="privacy", doc_version=payload.consent.privacy_version
        )
        user_repo.record_consent(
            session, user_id=user.id, doc_type="terms", doc_version=payload.consent.terms_version
        )
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise Conflict("EMAIL_TAKEN", "该邮箱已注册，请直接登录") from exc
    return _issue(response, user, session, request)


@router.post("/login", response_model=TokenOut)
def login(
    payload: LoginIn,
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
) -> TokenOut:
    hit(client_key(request, "login"), limit=10, window_seconds=600)
    # 先看账号是否还在锁定期，避免「密码对了也先算一次失败」
    login_guard.check_locked(payload.email)

    user = user_repo.get_by_email(session, payload.email)
    if user is None or not verify_password(payload.password, user.password_hash):
        # 不区分"用户不存在"与"密码错误"，避免账号枚举；但失败次数照记
        login_guard.note_failure(payload.email)
        raise Unauthorized("邮箱或密码不正确")
    if user.status != "active" or user.deleted_at is not None:
        raise Unauthorized("账号不可用，请联系支持")

    login_guard.reset(payload.email)
    # 参数升级后自动 rehash：用户无感，库里也不会长期留着旧强度哈希
    if user.password_hash and needs_rehash(user.password_hash):
        user.password_hash = hash_password(payload.password)
        session.add(user)
        session.commit()
    return _issue(response, user, session, request)


@router.post("/refresh", response_model=TokenOut)
def refresh(
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
) -> TokenOut:
    token = request.cookies.get(settings.refresh_cookie_name)
    if not token:
        raise Unauthorized("登录已过期，请重新登录")
    payload = decode_token(token, "refresh")
    jti = str(payload.get("jti") or "")
    row = auth_repo.get_refresh_token(session, jti) if jti else None
    if row is None:
        # 旧版本签发（无账本记录）或伪造：一律要求重新登录
        raise Unauthorized("登录状态已失效，请重新登录")
    if row.revoked_at is not None:
        raise Unauthorized("登录状态已失效，请重新登录")
    if row.used_at is not None:
        # 重放：同一枚 refresh 被用了第二次，说明可能被窃取 → 整族作废
        auth_repo.revoke_refresh_family(session, row.family_id)
        _audit(session, "auth.refresh_replay", user_id=row.user_id, detail={"family_id": row.family_id})
        session.commit()
        raise Unauthorized("登录状态异常，已注销全部会话，请重新登录")
    if row.expires_at <= utcnow():
        raise Unauthorized("登录已过期，请重新登录")

    user = user_repo.get_active(session, int(payload["sub"]))
    if user is None or int(payload.get("ver", -1)) != user.token_version:
        raise Unauthorized("登录状态已失效，请重新登录")

    auth_repo.mark_refresh_used(session, row)
    return _issue(response, user, session, request, family_id=row.family_id)


@router.post("/logout", status_code=204)
def logout(
    response: Response,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Response:
    # token_version +1 → 所有已签发的 access/refresh 立刻失效；账本同步作废
    user_repo.bump_token_version(session, user)
    auth_repo.revoke_all_refresh_tokens(session, user.id)
    session.commit()
    response.delete_cookie(settings.refresh_cookie_name, path=REFRESH_COOKIE_PATH)
    response.status_code = 204
    return response


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(user)


@router.get("/sessions", response_model=SessionOut)
def sessions(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> SessionOut:
    return SessionOut(active_sessions=auth_repo.count_active_sessions(session, user.id))


@router.delete("/sessions", response_model=SessionOut)
def revoke_sessions(
    response: Response,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> SessionOut:
    """登出全部设备：作废 refresh 账本并让 token_version 前进一位。"""
    auth_repo.revoke_all_refresh_tokens(session, user.id)
    user_repo.bump_token_version(session, user)
    session.commit()
    response.delete_cookie(settings.refresh_cookie_name, path=REFRESH_COOKIE_PATH)
    # 全部作废后可用会话数必为 0，直接返回 0 而不必再查一次库
    return SessionOut(active_sessions=0)


@router.post("/password/forgot", response_model=ForgotPasswordOut)
def forgot_password(
    payload: ForgotPasswordIn,
    request: Request,
    session: Session = Depends(get_session),
) -> ForgotPasswordOut:
    """申请重置密码。

    响应与「邮箱是否存在」完全无关：连 `expires_in_minutes` 都一样。
    开发环境（`APP_ENV=development` 且 `MAIL_MODE=console`）会额外返回
    `debug_reset_url`，方便本机联调；生产环境该字段恒为 None。
    """
    hit(client_key(request, "forgot"), limit=3, window_seconds=600)
    hit(f"forgot:email:{payload.email}", limit=3, window_seconds=3600)

    ttl = timedelta(minutes=settings.password_reset_ttl_minutes)
    debug_url: str | None = None
    user = user_repo.get_by_email(session, payload.email)

    if user is not None and user.status == "active" and user.deleted_at is None:
        # 只留最近 N 枚，避免「反复申请」把旧链接长期留在库里
        for stale in auth_repo.list_active_reset_tokens(session, user.id)[
            max(settings.password_reset_max_active - 1, 0) :
        ]:
            auth_repo.consume_reset_token(session, stale)

        raw_token, token_hash = new_reset_token()
        auth_repo.create_reset_token(
            session,
            user_id=user.id,
            token_hash=token_hash,
            expires_at=utcnow() + ttl,
            requested_ip=_client_ip(request),
        )
        reset_url = f"{settings.frontend_base_url.rstrip('/')}/reset-password?token={raw_token}"
        body = (
            "你好：\n\n"
            f"我们收到了重置「{settings.app_name}」账号密码的请求。\n"
            f"请在 {settings.password_reset_ttl_minutes} 分钟内打开下面的链接设置新密码：\n\n"
            f"{reset_url}\n\n"
            "如果这不是你本人的操作，忽略本邮件即可，密码不会被修改。\n"
            f"重置成功后，所有已登录设备都会被强制下线。\n\n"
            f"——{settings.app_name}"
        )
        try:
            mailer.send_mail(to=payload.email, subject=f"【{settings.app_name}】重置密码", body=body)
        except mailer.MailDeliveryError:
            # 投递失败不能暴露给调用方（否则成了「这个邮箱存在」的侧信道），
            # 但要在应用日志与审计里留痕，便于运维排查。
            _audit(session, "auth.password_reset_mail_failed", user_id=user.id)
        _audit(session, "auth.password_reset_requested", user_id=user.id, detail={"ttl_minutes": ttl.seconds // 60})
        if settings.app_env == "development" and settings.mail_mode == "console":
            debug_url = reset_url

    session.commit()
    return ForgotPasswordOut(
        message=FORGOT_MESSAGE,
        expires_in_minutes=settings.password_reset_ttl_minutes,
        debug_reset_url=debug_url,
    )


@router.post("/password/reset", response_model=ResetPasswordOut)
def reset_password(
    payload: ResetPasswordIn,
    request: Request,
    session: Session = Depends(get_session),
) -> ResetPasswordOut:
    hit(client_key(request, "reset"), limit=10, window_seconds=600)

    invalid = AppError(
        "INVALID_RESET_TOKEN",
        "重置链接无效或已过期，请重新申请",
        status_code=400,
    )
    row = auth_repo.get_reset_token(session, hash_token(payload.token))
    if row is None or row.used_at is not None or row.expires_at <= utcnow():
        raise invalid

    user = user_repo.get_active(session, row.user_id)
    if user is None:
        raise invalid
    if user.password_hash and verify_password(payload.password, user.password_hash):
        raise AppError("PASSWORD_REUSED", "新密码不能与当前密码相同", status_code=422)

    user.password_hash = hash_password(payload.password)
    user.token_version += 1  # 所有已签发的令牌立刻失效
    session.add(user)
    auth_repo.consume_reset_token(session, row)
    auth_repo.purge_other_reset_tokens(session, user_id=user.id, keep_id=row.id)
    auth_repo.revoke_all_refresh_tokens(session, user.id)
    login_guard.reset(user.email or "")
    _audit(session, "auth.password_reset", user_id=user.id, detail={"ip": _client_ip(request)})
    session.commit()

    return ResetPasswordOut(message="密码已更新，请用新密码重新登录。")
