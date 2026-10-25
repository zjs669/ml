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


@dataclass(frozen=True)
class ImagePart:
    """一张待送入视觉模型的内联图片。

    只放 base64 与 MIME，不放文件名、路径或任何用户可识别信息 ——
    图片元数据（EXIF、GPS、设备型号）必须在上传层剥离后再到这里。
    """

    base64_data: str
    mime_type: str

    def __post_init__(self) -> None:
        if not self.base64_data:
            raise ValueError("图片 base64 为空")
        if not self.mime_type.startswith("image/"):
            raise ValueError(f"MIME 必须是 image/*，收到 {self.mime_type}")

    def data_url(self) -> str:
        return f"data:{self.mime_type};base64,{self.base64_data}"


@dataclass
class LLMRequest:
    task: str
    system_prompt: str
    user_prompt: str
    context: dict[str, Any] = field(default_factory=dict)
    max_output_tokens: int = 3000
    #: 视觉任务用：非空时 provider 必须把 user 消息拼成多段内容（文本 + 图片）
    images: list[ImagePart] = field(default_factory=list)

    @property
    def is_vision(self) -> bool:
        return bool(self.images)


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
