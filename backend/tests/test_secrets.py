"""密钥静态加密的行为约定。

锁死四件事：
1. 密文里不能出现明文（截图/备份泄露时不能直接读到 key）；
2. 加密幂等、解密可逆、历史明文直通（渐进式迁移不停机）；
3. 主密钥变了必须明确报错，不能静默返回空串去请求上游；
4. 生产自检必须拦住明文密钥。
"""

from __future__ import annotations

import pytest

from app.core import secrets
from app.core.config import settings
from app.core.secrets import SecretDecryptError, decrypt_value, encrypt_value, is_encrypted, mask

MASTER = "unit-test-master-key-0123456789abcdef"


@pytest.fixture(autouse=True)
def _master(monkeypatch):
    monkeypatch.setattr(settings, "secrets_master_key", MASTER)
    yield


def test_roundtrip_and_prefix() -> None:
    raw = "b0ab3ec11ef59ff46c8740f10a6e8f8e"
    cipher = encrypt_value(raw)
    assert cipher.startswith(secrets.PREFIX)
    assert raw not in cipher
    assert decrypt_value(cipher) == raw


def test_encrypt_is_idempotent() -> None:
    once = encrypt_value("abc123")
    assert encrypt_value(once) == once
    assert is_encrypted(once)


def test_legacy_plaintext_passes_through() -> None:
    """迁移期：没加前缀的值按明文处理，不能把老配置读成空。"""
    assert decrypt_value("plain-value") == "plain-value"
    assert decrypt_value("") == ""


def test_wrong_master_key_raises(monkeypatch) -> None:
    cipher = encrypt_value("secret-value")
    monkeypatch.setattr(settings, "secrets_master_key", "another-master-key-0123456789abcdef")
    with pytest.raises(SecretDecryptError):
        decrypt_value(cipher)


def test_short_master_key_rejected(monkeypatch) -> None:
    monkeypatch.setattr(settings, "secrets_master_key", "short")
    with pytest.raises(SecretDecryptError):
        encrypt_value("x")


def test_fallback_to_secret_key(monkeypatch) -> None:
    monkeypatch.setattr(settings, "secrets_master_key", "")
    monkeypatch.setattr(settings, "secret_key", "fallback-secret-key-for-unit-tests")
    assert secrets.using_derived_master() is True
    assert decrypt_value(encrypt_value("hello")) == "hello"


def test_mask_never_leaks_full_value() -> None:
    text = "abcdefghijklmnopqrstuvwxyz012345"
    masked = mask(text)
    assert text not in masked
    assert masked.startswith("ab***")


def test_config_properties_decrypt(monkeypatch) -> None:
    monkeypatch.setattr(settings, "llm_api_key", encrypt_value("llm-key-value"))
    monkeypatch.setattr(settings, "smtp_password", encrypt_value("smtp-pass-value"))
    assert settings.llm_api_key_value == "llm-key-value"
    assert settings.smtp_password_value == "smtp-pass-value"


def test_production_check_blocks_plaintext_secret(monkeypatch) -> None:
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "llm_mode", "openai_compatible")
    monkeypatch.setattr(settings, "llm_api_key", "still-plaintext-key")
    monkeypatch.setattr(settings, "smtp_password", "")
    monkeypatch.setattr(settings, "secret_key", "x" * 40)
    monkeypatch.setattr(settings, "mock_payment_secret", "a-real-secret-value")
    with pytest.raises(RuntimeError) as exc:
        settings.assert_safe_for_production()
    assert "LLM_API_KEY" in str(exc.value)
