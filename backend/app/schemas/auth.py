"""认证相关出入参。"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.core.security import validate_password_strength

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
CURRENT_PRIVACY_VERSION = "2026-10-24.v1"
CURRENT_TERMS_VERSION = "2026-10-24.v1"


class ConsentIn(BaseModel):
    privacy_version: str = CURRENT_PRIVACY_VERSION
    terms_version: str = CURRENT_TERMS_VERSION
    accepted: bool = True

    @field_validator("accepted")
    @classmethod
    def _must_accept(cls, value: bool) -> bool:
        if not value:
            raise ValueError("必须同意隐私政策与用户协议才能创建账号")
        return value


class RegisterIn(BaseModel):
    email: str = Field(max_length=190)
    password: str = Field(min_length=8, max_length=128)
    display_name: str | None = Field(default=None, max_length=80)
    consent: ConsentIn = Field(default_factory=ConsentIn)

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        value = value.strip().lower()
        if not EMAIL_RE.match(value):
            raise ValueError("邮箱格式不正确")
        return value

    @field_validator("password")
    @classmethod
    def _password_strength(cls, value: str) -> str:
        # 与忘记密码共用同一套规则，避免「注册卡得住、重置卡不住」
        return validate_password_strength(value)

    model_config = {"extra": "forbid"}


class LoginIn(BaseModel):
    email: str = Field(max_length=190)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def _normalize(cls, value: str) -> str:
        return value.strip().lower()

    model_config = {"extra": "forbid"}


class UserOut(BaseModel):
    id: int
    email: str | None
    display_name: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


class DeleteAccountIn(BaseModel):
    """注销账号必须二次确认密码，避免误操作。"""

    password: str = Field(min_length=1, max_length=128)
    confirm: Literal["DELETE"] = "DELETE"

    model_config = {"extra": "forbid"}


class ForgotPasswordIn(BaseModel):
    """申请重置：只需要邮箱。"""

    email: str = Field(max_length=190)

    @field_validator("email")
    @classmethod
    def _normalize(cls, value: str) -> str:
        value = value.strip().lower()
        if not EMAIL_RE.match(value):
            raise ValueError("邮箱格式不正确")
        return value

    model_config = {"extra": "forbid"}


class ForgotPasswordOut(BaseModel):
    """无论邮箱是否存在，返回内容完全一致（防账号枚举）。"""

    message: str
    expires_in_minutes: int
    #: 仅在 APP_ENV=development 且 MAIL_MODE=console 时返回，生产恒为 None
    debug_reset_url: str | None = None


class ResetPasswordIn(BaseModel):
    token: str = Field(min_length=16, max_length=200)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def _password_strength(cls, value: str) -> str:
        return validate_password_strength(value)

    model_config = {"extra": "forbid"}


class ResetPasswordOut(BaseModel):
    message: str
    #: 重置成功后所有设备都被踢下线，前端据此跳到登录页
    signed_out_all: bool = True


class SessionOut(BaseModel):
    active_sessions: int
