"""OpenAI 兼容 Provider（/chat/completions + json_object）。

真正接线上模型时只需要改环境变量：
LLM_MODE=openai_compatible / LLM_BASE_URL / LLM_API_KEY / LLM_MODEL。

设计约定：
- provider 只做**单次**调用，重试策略统一放在 `reporting.service`（一次受控重试），
  避免"provider 重试 × service 重试"放大成本；
- 错误信息可以带状态码与耗时，但**任何分支都不得包含 API Key**；
- 部分模型不支持 `response_format=json_object`，可用 `LLM_JSON_MODE=prompt_only` 关掉，
  解析端同时支持 ```json 围栏与"正文里夹一段 JSON"的常见退化输出。
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

import httpx

from app.core.config import _is_placeholder, settings
from app.domains.llm.base import LLMProvider, LLMRequest, LLMResponse, LLMUnavailable
from app.domains.llm.mock import MockProvider

FENCE = re.compile(r"```(?:json|JSON)?\s*(.*?)```", re.S)

MAX_ERROR_CHARS = 200


def _balanced_object(text: str) -> str | None:
    """从任意文本里取出第一个括号平衡的 JSON 对象（跳过字符串内的花括号）。"""
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def extract_json_object(content: str) -> dict[str, Any]:
    """把模型返回的文本解析成 JSON 对象；失败抛 LLMUnavailable（由上层重试/降级）。"""
    raw = (content or "").strip()
    if not raw:
        raise LLMUnavailable("模型返回内容为空")
    fence = FENCE.search(raw)
    if fence:
        raw = fence.group(1).strip()
    candidates = [raw]
    balanced = _balanced_object(raw)
    if balanced and balanced != raw:
        candidates.append(balanced)
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    raise LLMUnavailable("模型返回内容不是合法 JSON 对象")


def _describe_http_error(status: int) -> str:
    if status in (401, 403):
        return "API Key 无效或无权访问该模型"
    if status == 404:
        return "接口路径或模型不存在（请检查 LLM_BASE_URL 与 LLM_MODEL）"
    if status == 429:
        return "上游限流或账户额度不足"
    if 500 <= status < 600:
        return f"上游服务异常（HTTP {status}）"
    return f"模型服务返回 HTTP {status}"


class OpenAICompatibleProvider(LLMProvider):
    name = "openai_compatible"

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout_seconds: int | None = None,
        max_output_tokens: int | None = None,
        json_mode: str | None = None,
        temperature: float | None = None,
    ) -> None:
        self.base_url = (base_url or settings.llm_base_url).rstrip("/")
        self.api_key = api_key if api_key is not None else settings.llm_api_key_value
        self.model = model or settings.llm_model
        self.timeout_seconds = timeout_seconds or settings.llm_timeout_seconds
        self.max_output_tokens = max_output_tokens or settings.llm_max_output_tokens
        self.json_mode = (json_mode or settings.llm_json_mode).lower()
        self.temperature = settings.llm_temperature if temperature is None else temperature
        if _is_placeholder(self.api_key):
            raise LLMUnavailable(
                "LLM_API_KEY 为空或仍是占位值，无法使用真实模型（请在 backend/.env 填入真实 key）"
            )

    def _payload(self, request: LLMRequest) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.user_prompt},
            ],
            "temperature": self.temperature,
            "top_p": 0.9,
            "max_tokens": min(request.max_output_tokens, self.max_output_tokens),
        }
        if self.json_mode == "json_object":
            payload["response_format"] = {"type": "json_object"}
        return payload

    def generate_json(self, request: LLMRequest) -> LLMResponse:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        started = time.monotonic()
        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.post(
                    f"{self.base_url}/chat/completions",
                    json=self._payload(request),
                    headers=headers,
                )
        except httpx.TimeoutException as exc:
            raise LLMUnavailable(f"模型服务超时（{self.timeout_seconds} 秒）") from exc
        except httpx.HTTPError as exc:
            raise LLMUnavailable(f"模型服务连接失败：{exc.__class__.__name__}") from exc
        latency_ms = int((time.monotonic() - started) * 1000)

        if response.status_code >= 400:
            raise LLMUnavailable(_describe_http_error(response.status_code))

        try:
            body = response.json()
            choice = body["choices"][0]
            content = choice["message"]["content"]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise LLMUnavailable("模型响应结构不符合 chat/completions 约定") from exc
        if not isinstance(content, str):
            raise LLMUnavailable("模型返回的 content 不是文本")

        usage = body.get("usage") or {}
        finish_reason = str(choice.get("finish_reason") or "")
        # 截断要在解析之前判定，否则用户只会看到“不是合法 JSON”这种误导性提示
        if finish_reason == "length":
            raise LLMUnavailable(
                f"模型输出被 max_tokens 截断（{self.max_output_tokens}），请提高 LLM_MAX_OUTPUT_TOKENS"
            )
        parsed = extract_json_object(content)

        return LLMResponse(
            payload=parsed,
            provider=self.name,
            model=str(body.get("model") or self.model),
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
            raw_text=content[:MAX_ERROR_CHARS] if finish_reason == "content_filter" else content,
            latency_ms=latency_ms,
            finish_reason=finish_reason,
        )


def get_provider(mode: str | None = None) -> LLMProvider:
    """按配置返回 Provider。mock 为默认值，保证离线可跑。"""
    resolved = (mode or settings.llm_mode).lower()
    if resolved == "mock":
        return MockProvider()
    if resolved == "openai_compatible":
        return OpenAICompatibleProvider()
    raise LLMUnavailable(f"未知的 LLM_MODE：{resolved}")
