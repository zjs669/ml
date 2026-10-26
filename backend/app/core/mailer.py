"""邮件投递：验证码与重置链接共用。

两种通道，靠 `MAIL_MODE` 切换：

- `console`（开发默认）：不真的发信，把邮件原样追加到 `backend/var/mail_outbox.log`，
  每行一个 JSON，本地联调时直接看这个文件即可。这样既不需要配置邮箱，
  也不会把验证码/重置链接打到应用日志里（日志可能被采集上传）。
- `smtp`：走标准 SMTP。QQ 邮箱用 465 + SSL，授权码当密码（不是登录密码）。

投递失败会抛 `MailDeliveryError`，由调用方决定如何对外表现：
忘记密码接口一律返回同一句文案，不因「发信失败」暴露邮箱是否存在。

## 关于 QQ 邮箱

`SENDER_PASSWORD` 填的是「授权码」而不是 QQ 登录密码，在
QQ 邮箱 → 设置 → 账户 → POP3/SMTP 服务 里生成。授权码等同于密码，
必须放在 `.env`（已 gitignore），不能写进代码或提交到仓库。
"""

from __future__ import annotations

import json
import random
import smtplib
from datetime import datetime, timezone
from email.message import EmailMessage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from app.core.config import BACKEND_DIR, settings


class MailDeliveryError(RuntimeError):
    """投递失败（通道不可用、SMTP 拒收等）。消息里不含任何凭据。"""


def outbox_path() -> Path:
    configured = (settings.mail_outbox_path or "").strip()
    if configured:
        return Path(configured)
    return BACKEND_DIR / "var" / "mail_outbox.log"


def generate_verification_code() -> str:
    """生成 6 位数字验证码。

    用 `random` 而不是 `secrets`：验证码的有效期只有 10 分钟且限制尝试次数
    （见 `verification_code_max_attempts`），攻击者拿不到足够的样本反推状态。
    如果将来把有效期延长到小时级，应换成 `secrets.randbelow`。
    """
    return f"{random.randint(0, 999999):06d}"


def render_code_email(*, code: str, ttl_minutes: int, app_name: str) -> str:
    """验证码邮件的 HTML 正文。

    单文件内联样式：邮件客户端普遍不加载外部 CSS，`<style>` 也有被剥离的。
    """
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><title>验证码通知</title></head>
<body style="margin:0;padding:0;background:#f7f7f7;">
  <div style="max-width:600px;margin:24px auto;padding:24px;background:#fff;
              border:1px solid #e1e1e1;border-radius:6px;
              font-family:'Microsoft YaHei',Arial,sans-serif;line-height:1.7;color:#333;">
    <h2 style="color:#1890ff;text-align:center;margin:0 0 20px;">{app_name} · 验证码</h2>
    <p>您好！</p>
    <p>您正在验证邮箱，验证码为：</p>
    <div style="font-size:32px;font-weight:bold;color:#1890ff;letter-spacing:6px;
                padding:14px 20px;background:#f0f9ff;border-radius:6px;
                text-align:center;margin:20px 0;">{code}</div>
    <p>该验证码 <strong>{ttl_minutes} 分钟</strong>内有效，请尽快完成验证。</p>
    <p style="color:#999;font-size:12px;">如果这不是你本人的操作，忽略本邮件即可，你的密码不会被修改。</p>
    <div style="color:#999;font-size:12px;margin-top:28px;padding-top:14px;border-top:1px solid #eee;">
      此邮件由系统自动发送，请勿回复。
    </div>
  </div>
</body>
</html>"""


def _deliver_console(*, to: str, subject: str, body: str, html: str | None) -> None:
    path = outbox_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "sent_at": datetime.now(timezone.utc).isoformat(),
        "from": settings.mail_from,
        "to": to,
        "subject": subject,
        "body": body,
        "html": bool(html),
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _build_message(*, to: str, subject: str, body: str, html: str | None) -> EmailMessage:
    if not html:
        message = EmailMessage()
        message["From"] = settings.mail_from
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)
        return message

    # 同时带纯文本与 HTML：只发 HTML 会被部分客户端判为垃圾邮件
    message = MIMEMultipart("alternative")
    message["From"] = settings.mail_from
    message["To"] = to
    message["Subject"] = subject
    message.attach(MIMEText(body, "plain", "utf-8"))
    message.attach(MIMEText(html, "html", "utf-8"))
    return message


def _deliver_smtp(*, to: str, subject: str, body: str, html: str | None) -> None:
    if not settings.smtp_host:
        raise MailDeliveryError("MAIL_MODE=smtp 但未配置 SMTP_HOST")
    try:
        password = settings.smtp_password_value
    except Exception as exc:
        raise MailDeliveryError(f"SMTP 密码读取失败：{exc.__class__.__name__}") from exc
    if not password:
        raise MailDeliveryError("MAIL_MODE=smtp 但未配置 SMTP_PASSWORD（QQ 邮箱填授权码）")

    message = _build_message(to=to, subject=subject, body=body, html=html)
    try:
        if settings.smtp_use_ssl:
            with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=20) as client:
                if settings.smtp_username:
                    client.login(settings.smtp_username, password)
                client.send_message(message)
        else:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as client:
                client.starttls()
                if settings.smtp_username:
                    client.login(settings.smtp_username, password)
                client.send_message(message)
    except smtplib.SMTPAuthenticationError as exc:
        # 535：授权码错误。这是最常见的一类，单独给出可操作的提示
        raise MailDeliveryError(
            "SMTP 认证失败（535）：QQ 邮箱要填「授权码」而不是登录密码，"
            "在 QQ 邮箱 → 设置 → 账户 → POP3/SMTP 服务 里生成"
        ) from exc
    except smtplib.SMTPSenderRefused as exc:
        raise MailDeliveryError(
            "发件人被拒绝（550）：MAIL_FROM 必须与 SMTP_USERNAME 是同一个邮箱"
        ) from exc
    except smtplib.SMTPRecipientsRefused as exc:
        raise MailDeliveryError("收件人被拒绝：目标邮箱地址无效或拒收") from exc
    except (OSError, smtplib.SMTPException) as exc:
        # 只报异常类型，绝不把用户名/密码/邮件内容写进异常信息
        raise MailDeliveryError(f"SMTP 投递失败：{exc.__class__.__name__}") from exc


def send_mail(*, to: str, subject: str, body: str, html: str | None = None) -> str:
    """发送一封邮件，返回实际使用的通道名（`smtp` / `console`）。"""
    mode = (settings.mail_mode or "console").lower()
    if mode == "smtp":
        _deliver_smtp(to=to, subject=subject, body=body, html=html)
        return "smtp"
    _deliver_console(to=to, subject=subject, body=body, html=html)
    return "console"


def send_verification_code(*, to: str, code: str, ttl_minutes: int) -> str:
    """发送验证码邮件（纯文本 + HTML 双版本）。"""
    body = (
        f"您好！\n\n"
        f"您正在验证「{settings.app_name}」账号邮箱，验证码为：\n\n"
        f"    {code}\n\n"
        f"该验证码 {ttl_minutes} 分钟内有效，请尽快完成验证。\n"
        f"如果这不是你本人的操作，忽略本邮件即可。\n\n"
        f"——{settings.app_name}"
    )
    html = render_code_email(code=code, ttl_minutes=ttl_minutes, app_name=settings.app_name)
    return send_mail(
        to=to,
        subject=f"【{settings.app_name}】验证码 {code}",
        body=body,
        html=html,
    )


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
