"""第三方密钥的静态加密（Fernet）。

为什么需要：用户密码是 Argon2id 哈希（不可逆），但程序自己要**用**的密钥
（模型 API Key、SMTP 授权码）必须是可逆的，只能加密存储。`.env` 一旦被备份、
误传、截图或打进镜像层，明文就等于泄露。

设计取舍：

- 密文统一带 `enc:v1:` 前缀，解密时按前缀判断；没有前缀的值按**历史明文**直通，
  这样加密是渐进式的，不需要一次性停机改配置。
- 主密钥优先取 `SECRETS_MASTER_KEY`；没配时用 `SECRET_KEY` 经 HKDF 派生。
  派生模式能用，但 `SECRET_KEY` 一换密文就解不开，所以生产自检要求显式配置。
- 轮换：`scripts/encrypt_secrets.py` 只负责把明文变成密文；换主密钥需要重新加密
  （旧密文解不开时直接抛 `SecretDecryptError`，绝不静默退化成空串）。
"""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

PREFIX = "enc:v1:"
_HKDF_INFO = b"xuanshu-secret-store-v1"
#: 主密钥最短长度。Fernet 本身只要 32 字节，这里要求配置值也不短于 32，
#: 避免有人用「123456」当主密钥还以为加密了。
MIN_MASTER_LEN = 32


class SecretDecryptError(RuntimeError):
    """密文无法解开：主密钥变了、抄错、或值不是本系统产生的。"""


def is_encrypted(value: str | None) -> bool:
    return bool(value) and value.strip().startswith(PREFIX)


def _master_secret() -> tuple[bytes, bool]:
    """返回 (主密钥原材料, 是否来自 SECRET_KEY 派生)。"""
    from app.core.config import settings

    explicit = (settings.secrets_master_key or "").strip()
    if explicit:
        if len(explicit) < MIN_MASTER_LEN:
            raise SecretDecryptError(
                f"SECRETS_MASTER_KEY 长度不足 {MIN_MASTER_LEN} 字符，无法作为主密钥"
            )
        return explicit.encode("utf-8"), False
    return (settings.secret_key or "").encode("utf-8"), True


def _fernet() -> Fernet:
    material, _ = _master_secret()
    key = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"xuanshu.secret.salt",
        info=_HKDF_INFO,
    ).derive(material)
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt_value(raw: str) -> str:
    """把明文加密成 `enc:v1:...`；已加密的值原样返回（幂等）。"""
    if not raw:
        return ""
    if is_encrypted(raw):
        return raw
    token = _fernet().encrypt(raw.encode("utf-8")).decode("ascii")
    return PREFIX + token


def decrypt_value(value: str | None) -> str:
    """解密；没有前缀的值按历史明文直通，解不开则抛错而不是返回空串。"""
    if not value:
        return ""
    text = value.strip()
    if not is_encrypted(text):
        return text
    try:
        return _fernet().decrypt(text[len(PREFIX) :].encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError) as exc:
        raise SecretDecryptError(
            "密文无法解密：SECRETS_MASTER_KEY / SECRET_KEY 可能已变更，请重新执行 "
            "python -m scripts.encrypt_secrets 生成密文"
        ) from exc


def mask(value: str | None, *, keep: int = 4) -> str:
    """日志与 CLI 展示用：只留尾部若干位，绝不打印完整密钥。"""
    if not value:
        return "（空）"
    text = value.strip()
    if len(text) <= keep * 2:
        return "*" * len(text)
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:6]
    return f"{text[:2]}***{text[-keep:]}（指纹 {digest}）"


def using_derived_master() -> bool:
    """未显式配置主密钥时为 True；启动日志据此提示风险。"""
    _, derived = _master_secret()
    return derived
