"""结构化日志 + 脱敏。日志只写标准输出，不落用户敏感原文。"""

from __future__ import annotations

import json
import logging
import re
import sys
from datetime import datetime, timezone

_REDACT_PATTERNS = [
    (re.compile(r"(sk-[A-Za-z0-9_\-]{8,})"), "sk-***"),
    (re.compile(r"(?i)(api[_-]?key|authorization|token|password)\"?\s*[:=]\s*\"?([^\s\",}]+)"), r"\1=***"),
    # 出生时间/日期不在日志里原文出现
    (re.compile(r"\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?\b"), "<datetime>"),
    (re.compile(r"\b\d{4}-\d{2}-\d{2}\b"), "<date>"),
]


def redact(text: str) -> str:
    for pattern, repl in _REDACT_PATTERNS:
        text = pattern.sub(repl, text)
    return text


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": redact(record.getMessage()),
        }
        for key in ("request_id", "user_id", "path", "status", "duration_ms"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exc"] = redact(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    # 关掉 uvicorn 默认访问日志，由中间件统一输出
    logging.getLogger("uvicorn.access").disabled = True
