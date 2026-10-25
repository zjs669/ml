"""LLM Provider 抽象。

约束：
- 只接受「任务 + 系统提示词 + 已组装的上下文」，不接触数据库、不接触用户身份；
- 只返回结构化 JSON，文本解析留给 provider 自己，异常一律抛 `LLMUnavailable`；
- `domains/bazi` 与 `domains/relations` 不允许 import 本包（依赖方向硬约束）。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


class LLMUnavailable(RuntimeError):
    """上游不可用 / 超时 / 返回非 JSON，调用方据此退款并降级。"""


@dataclass
class LLMRequest:
    task: str
    system_prompt: str
    user_prompt: str
    context: dict[str, Any] = field(default_factory=dict)
    max_output_tokens: int = 3000


@dataclass
class LLMResponse:
    payload: dict[str, Any]
    provider: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    raw_text: str = ""
    retried: bool = False
    latency_ms: int = 0
    finish_reason: str = ""


class LLMProvider(ABC):
    name: str = "base"
    model: str = "base"

    @abstractmethod
    def generate_json(self, request: LLMRequest) -> LLMResponse:
        """返回已解析的 JSON 对象；不允许返回半结构化文本。"""
