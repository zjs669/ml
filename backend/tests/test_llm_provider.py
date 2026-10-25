"""真实模型 Provider 的失败模式覆盖。

不联网：用 `httpx.MockTransport` 注入响应，逐条验证
200 / 401 / 404 / 429 / 500 / 非 JSON / ```json 围栏 / 正文夹 JSON / 超时 / 截断 / prompt_only，
并且**每一条错误分支都不得把 API Key 写进异常信息**（验收门槛里的安全项）。
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from app.domains.llm import openai_compatible as oc
from app.domains.llm.base import LLMRequest, LLMUnavailable

API_KEY = "sk-selftest-SECRET-9f3a7c"
BASE_URL = "https://llm.example.com/v1"
MODEL = "test-chat-v1"

PAYLOAD_OUT = {"summary": "盘面事实陈述", "observations": [], "uncertainties": []}


def _request() -> LLMRequest:
    return LLMRequest(
        task="bazi.overview.v1",
        system_prompt="你是研习助手，只输出 JSON。",
        user_prompt="请按 Schema 输出。",
        max_output_tokens=1200,
    )


def _provider(**kwargs: Any) -> oc.OpenAICompatibleProvider:
    params: dict[str, Any] = {
        "base_url": BASE_URL,
        "api_key": API_KEY,
        "model": MODEL,
        "timeout_seconds": 2,
        "json_mode": "json_object",
    }
    params.update(kwargs)
    return oc.OpenAICompatibleProvider(**params)


def _chat_body(content: str, *, finish_reason: str = "stop") -> dict[str, Any]:
    return {
        "model": MODEL,
        "choices": [{"message": {"role": "assistant", "content": content}, "finish_reason": finish_reason}],
        "usage": {"prompt_tokens": 120, "completion_tokens": 45},
    }


def _json_response(content: str, *, finish_reason: str = "stop", status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=_chat_body(content, finish_reason=finish_reason))


def _patch_transport(monkeypatch: pytest.MonkeyPatch, handler: Callable[[httpx.Request], httpx.Response]) -> list[httpx.Request]:
    """把 httpx.Client 换成挂了 MockTransport 的实例，并回收所有出站请求用于断言。"""
    seen: list[httpx.Request] = []

    def wrapped(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    real_client = httpx.Client

    def factory(*args: Any, **kwargs: Any) -> httpx.Client:
        kwargs["transport"] = httpx.MockTransport(wrapped)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(oc.httpx, "Client", factory)
    return seen


def test_successful_call_records_tokens_and_latency(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _patch_transport(monkeypatch, lambda _: _json_response(json.dumps(PAYLOAD_OUT)))

    response = _provider().generate_json(_request())

    assert response.payload == PAYLOAD_OUT
    assert response.provider == "openai_compatible"
    assert response.model == MODEL
    assert (response.input_tokens, response.output_tokens) == (120, 45)
    assert response.finish_reason == "stop"
    assert response.latency_ms >= 0
    body = json.loads(seen[0].content)
    assert body["response_format"] == {"type": "json_object"}
    assert body["max_tokens"] == 1200
    assert seen[0].headers["authorization"] == f"Bearer {API_KEY}"


def test_prompt_only_mode_does_not_send_response_format(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _patch_transport(monkeypatch, lambda _: _json_response(json.dumps(PAYLOAD_OUT)))

    _provider(json_mode="prompt_only").generate_json(_request())

    body = json.loads(seen[0].content)
    assert "response_format" not in body


def test_json_fence_is_stripped(monkeypatch: pytest.MonkeyPatch) -> None:
    content = "下面是结果：\n```json\n" + json.dumps(PAYLOAD_OUT, ensure_ascii=False) + "\n```\n"
    _patch_transport(monkeypatch, lambda _: _json_response(content))

    assert _provider().generate_json(_request()).payload == PAYLOAD_OUT


def test_json_embedded_in_prose_is_extracted(monkeypatch: pytest.MonkeyPatch) -> None:
    content = "好的，我按要求给出：" + json.dumps(PAYLOAD_OUT, ensure_ascii=False) + " 以上。"
    _patch_transport(monkeypatch, lambda _: _json_response(content))

    assert _provider().generate_json(_request()).payload == PAYLOAD_OUT


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, "API Key 无效"),
        (403, "API Key 无效"),
        (404, "模型不存在"),
        (429, "限流"),
        (500, "上游服务异常"),
        (503, "上游服务异常"),
    ],
)
def test_http_errors_are_classified(
    monkeypatch: pytest.MonkeyPatch, status: int, expected: str
) -> None:
    _patch_transport(monkeypatch, lambda _: httpx.Response(status, json={"error": "boom"}))

    with pytest.raises(LLMUnavailable) as excinfo:
        _provider().generate_json(_request())
    assert expected in str(excinfo.value)
    assert API_KEY not in str(excinfo.value)


def test_non_json_content_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_transport(monkeypatch, lambda _: _json_response("这就是一段普通说明文字，没有 JSON。"))

    with pytest.raises(LLMUnavailable, match="JSON"):
        _provider().generate_json(_request())


def test_broken_response_shape_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_transport(monkeypatch, lambda _: httpx.Response(200, json={"unexpected": True}))

    with pytest.raises(LLMUnavailable, match="chat/completions"):
        _provider().generate_json(_request())


def test_timeout_is_reported_with_seconds(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out", request=request)

    _patch_transport(monkeypatch, handler)

    with pytest.raises(LLMUnavailable) as excinfo:
        _provider(timeout_seconds=7).generate_json(_request())
    assert "超时" in str(excinfo.value)
    assert "7" in str(excinfo.value)
    assert API_KEY not in str(excinfo.value)


def test_connection_error_does_not_leak_key(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"failed to connect with {API_KEY}", request=request)

    _patch_transport(monkeypatch, handler)

    with pytest.raises(LLMUnavailable) as excinfo:
        _provider().generate_json(_request())
    assert "连接失败" in str(excinfo.value)
    # 上游异常文本里若回显了 key，也不能透传出去
    assert API_KEY not in str(excinfo.value)


def test_truncated_output_reports_max_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    # 截断时 content 通常是不完整 JSON，错误必须指向 max_tokens 而不是"不是合法 JSON"
    _patch_transport(
        monkeypatch, lambda _: _json_response('{"summary": "写到一半', finish_reason="length")
    )

    with pytest.raises(LLMUnavailable) as excinfo:
        _provider(max_output_tokens=2048).generate_json(_request())
    assert "截断" in str(excinfo.value)
    assert "2048" in str(excinfo.value)


def test_missing_api_key_fails_loudly() -> None:
    with pytest.raises(LLMUnavailable, match="LLM_API_KEY"):
        oc.OpenAICompatibleProvider(base_url=BASE_URL, api_key="", model=MODEL)


def test_unknown_mode_is_rejected() -> None:
    with pytest.raises(LLMUnavailable, match="LLM_MODE"):
        oc.get_provider("no_such_mode")
