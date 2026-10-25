"""邮件投递（忘记密码用）。

两种通道，靠 `MAIL_MODE` 切换：

- `console`（开发默认）：不真的发信，把邮件原样追加到 `backend/var/mail_outbox.log`，
  每行一个 JSON，本地联调时直接看这个文件即可。这样既不需要配置邮箱，
  也不会把重置链接打到应用日志里（日志可能被采集上传）。
- `smtp`：走标准 SMTP（465 + SSL 或 587 + STARTTLS），生产必须用这个。

投递失败会抛 `MailDeliveryError`，由调用方决定如何对外表现：
忘记密码接口一律返回同一句文案，不因「发信失败」暴露邮箱是否存在。
"""

from __future__ import annotations

import json
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

from app.core.config import BACKEND_DIR, settings


class MailDeliveryError(RuntimeError):
    """投递失败（通道不可用、SMTP 拒收等）。消息里不含任何凭据。"""


def outbox_path() -> Path:
    configured = (settings.mail_outbox_path or "").strip()
    if configured:
        return Path(configured)
    return BACKEND_DIR / "var" / "mail_outbox.log"


def _deliver_console(message: EmailMessage) -> None:
    path = outbox_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "sent_at": datetime.now(timezone.utc).isoformat(),
        "from": message["From"],
        "to": message["To"],
        "subject": message["Subject"],
        "body": message.get_content(),
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _deliver_smtp(message: EmailMessage) -> None:
    if not settings.smtp_host:
        raise MailDeliveryError("MAIL_MODE=smtp 但未配置 SMTP_HOST")
    # 密码可能是 `enc:v1:` 密文；解不开时按投递失败处理，不静默用空密码重试
    try:
        password = settings.smtp_password_value
    except Exception as exc:
        raise MailDeliveryError(f"SMTP 密码解密失败：{exc.__class__.__name__}") from exc
    try:
        if settings.smtp_use_ssl:
            with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=15) as client:
                if settings.smtp_username:
                    client.login(settings.smtp_username, password)
                client.send_message(message)
        else:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as client:
                client.starttls()
                if settings.smtp_username:
                    client.login(settings.smtp_username, password)
                client.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        # 只报异常类型，绝不把用户名/密码/邮件内容写进异常信息
        raise MailDeliveryError(f"SMTP 投递失败：{exc.__class__.__name__}") from exc


def send_mail(*, to: str, subject: str, body: str) -> str:
    """发送一封纯文本邮件，返回实际使用的通道名。"""
    message = EmailMessage()
    message["From"] = settings.mail_from
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)

    mode = (settings.mail_mode or "console").lower()
    if mode == "smtp":
        _deliver_smtp(message)
        return "smtp"
    _deliver_console(message)
    return "console"


def read_outbox(limit: int = 20) -> list[dict]:
    """读最近若干封 console 模式的邮件，供本地联调与测试断言用。"""
    path = outbox_path()
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()[-limit:]
    items: list[dict] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            items.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return items
