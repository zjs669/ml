"""真实模型连通性自检。

    python -m scripts.llm_selftest
    python -m scripts.llm_selftest --task bazi.overview.v1

只发一条最小请求，验证五件事：能不能连上、回的 JSON 合不合法、
延迟多少、token 多少、成本估多少。失败时给出**可执行的修复建议**，
但绝不打印 API Key，也不改任何配置。
"""

from __future__ import annotations

import argparse
import json
import sys
import time

from app.core.config import settings
from app.domains.llm.base import LLMRequest, LLMUnavailable
from app.domains.llm.openai_compatible import OpenAICompatibleProvider

PANEL = "=" * 60

SYSTEM_PROMPT = (
    "你是一个只输出 JSON 的填充器。不要输出任何解释、Markdown 或代码围栏，"
    "只输出一个 JSON 对象。"
)
USER_PROMPT = (
    "请输出一个 JSON 对象，包含三个字段：\n"
    '- "summary": 字符串，值为 "ok"\n'
    '- "items": 数组，包含 1 个字符串元素 "fact"\n'
    '- "uncertainties": 空数组\n'
    "不要添加任何其他字段。"
)

EXPECTED_KEYS = {"summary", "items", "uncertainties"}


def _suggest(message: str) -> list[str]:
    """把错误信息翻成下一步动作，而不是只说"失败了"。"""
    if "LLM_API_KEY" in message:
        return [
            "在 backend/.env 里设置 LLM_API_KEY=<你的 key>（不要提交到仓库）",
            "同时确认 LLM_MODE=openai_compatible",
        ]
    if "API Key" in message:
        return [
            "检查 key 是否被截断、是否带了多余空格或引号",
            "确认该 key 对 LLM_MODEL 指定的模型有调用权限",
        ]
    if "模型不存在" in message or "404" in message:
        return [
            "确认 LLM_BASE_URL 是否以 /v1 结尾（例如 https://api.deepseek.com/v1）",
            "确认 LLM_MODEL 与服务商的模型名完全一致",
        ]
    if "限流" in message:
        return ["等待一分钟重试；或确认账户余额与配额是否充足"]
    if "超时" in message:
        return ["调大 LLM_TIMEOUT_SECONDS（当前 %s 秒）" % settings.llm_timeout_seconds]
    if "截断" in message:
        return ["调大 LLM_MAX_OUTPUT_TOKENS（当前 %s）" % settings.llm_max_output_tokens]
    if "JSON" in message:
        return [
            "该模型可能不支持 response_format=json_object，尝试 LLM_JSON_MODE=prompt_only",
            "检查是否为推理模型，其输出可能夹带思维过程文本",
        ]
    if "连接失败" in message:
        return ["检查本机网络/代理，或确认 LLM_BASE_URL 可从服务器访问"]
    return ["先确认 LLM_MODE / LLM_BASE_URL / LLM_MODEL 三项与文档一致"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="真实模型连通性自检")
    parser.add_argument("--task", default="selftest", help="写入账本的调用任务名")
    args = parser.parse_args(argv)

    print(PANEL)
    print(f"模式       : {settings.llm_mode}")
    print(f"服务地址   : {settings.llm_base_url}")
    print(f"模型       : {settings.llm_model}")
    print(f"JSON 模式  : {settings.llm_json_mode}")
    print(f"Key 已配置 : {'是' if settings.llm_api_key else '否'}")
    print(PANEL)

    if not settings.llm_configured:
        print("结论：当前不具备调用真实模型的条件（LLM_MODE=mock 或 LLM_API_KEY 为空）。")
        for line in _suggest("未配置 LLM_API_KEY"):
            print("  -", line)
        return 1

    try:
        provider = OpenAICompatibleProvider()
    except LLMUnavailable as exc:  # pragma: no cover - 与上一分支同类
        print(f"结论：Provider 初始化失败：{exc}")
        return 1

    started = time.monotonic()
    try:
        response = provider.generate_json(
            LLMRequest(
                task=args.task,
                system_prompt=SYSTEM_PROMPT,
                user_prompt=USER_PROMPT,
                max_output_tokens=256,
            )
        )
    except LLMUnavailable as exc:
        elapsed = int((time.monotonic() - started) * 1000)
        print(f"结论：调用失败（{elapsed} ms）：{exc}")
        print("建议：")
        for line in _suggest(str(exc)):
            print("  -", line)
        return 1

    elapsed = int((time.monotonic() - started) * 1000)
    payload = response.payload
    missing = EXPECTED_KEYS - set(payload)
    extra = set(payload) - EXPECTED_KEYS
    cost = settings.estimate_cost(response.input_tokens, response.output_tokens)

    print("调用成功")
    print(f"  实际模型   : {response.model}")
    print(f"  端到端耗时 : {elapsed} ms（provider 自记 {response.latency_ms} ms）")
    print(f"  tokens     : 输入 {response.input_tokens} / 输出 {response.output_tokens}")
    print(f"  成本估算   : {'未配置单价' if cost is None else f'{cost:.6f} 元'}")
    print(f"  finish     : {response.finish_reason or '未知'}")
    print(f"  返回内容   : {json.dumps(payload, ensure_ascii=False)[:300]}")

    if missing or extra:
        print(PANEL)
        print(f"结论：JSON 合法但键不符（缺 {sorted(missing)}，多 {sorted(extra)}）。")
        print("  这不影响生产（真实 schema 由 skill 定义），但说明模型不严格守约，")
        print("  建议保留 schema 校验 + 一次受控重试。")
        return 2

    print(PANEL)
    print("结论：自检通过，可切到 LLM_MODE=openai_compatible 对外服务。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
