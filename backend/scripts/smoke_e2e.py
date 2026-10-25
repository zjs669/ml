"""端到端联调：四术数各跑一遍「排盘 → 保存 → 解读 → 额度」。

用法：
    # 先起后端 uvicorn，再起前端 npm run dev
    python -m scripts.smoke_e2e
    # 不经过前端代理时：
    SMOKE_BASE=http://127.0.0.1:8000/api/v1 python -m scripts.smoke_e2e

前端代码使用的就是这些接口，本脚本可当作「前后端契约回归 + 额度回归」用：
四柱、紫微、六爻、奇门走同一套 calculate → save → report 流程，任何一术数的
入参字段名、响应结构或技能解析改坏了，这里会先红。
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from typing import Any

import httpx

BASE = os.environ.get("SMOKE_BASE", "http://localhost:5173/api/v1")
HEALTH_URL = os.environ.get("SMOKE_HEALTH", "http://127.0.0.1:8000/healthz")

#: 四术数入参。字段名与 frontend/src/api/charts.ts 一一对应，改一处必须同步另一处。
CASES: dict[str, dict[str, Any]] = {
    "bazi": {
        "birth_datetime": "1990-06-15T09:10:00",
        "timezone": "Asia/Shanghai",
        "gender": "female",
        "time_known": True,
        "convention": {},
    },
    "ziwei": {
        "calendar": "gregorian",
        "birth_datetime": "1990-06-15T09:10:00",
        "timezone": "Asia/Shanghai",
        "gender": "female",
        "time_known": True,
        "convention": {},
    },
    "liuyao": {
        "method": "coins",
        "cast_datetime": "2026-01-01T12:00:00",
        "timezone": "Asia/Shanghai",
        "seed": 20260101,
        "convention": {},
    },
    "qimen": {
        "cast_datetime": "2026-01-01T12:00:00",
        "timezone": "Asia/Shanghai",
        "convention": {},
    },
}


def check(condition: bool, message: str) -> None:
    if not condition:
        print(f"断言失败：{message}", file=sys.stderr)
        sys.exit(1)


def show(label: str, response: httpx.Response) -> dict[str, Any]:
    print(f"{label} -> {response.status_code}")
    if response.status_code >= 400:
        print(response.text[:400])
        sys.exit(1)
    return response.json() if response.content else {}


def hint(domain: str, facts: dict[str, Any]) -> str:
    """每个术数挑一处最能一眼看出「算没算」的盘面事实打印出来。"""
    if domain == "bazi":
        return " ".join(facts["pillars"][key]["text"] for key in facts["order"])
    if domain == "ziwei":
        return (
            f"{facts['lunar_date']['text']} "
            f"命宫{facts['life_palace']['text']} "
            f"{facts['five_element_bureau']['name']} "
            f"紫微在{facts['ziwei_star']['branch']}"
        )
    if domain == "liuyao":
        changed = facts.get("changed") or {}
        return (
            f"{facts['original']['name']}（{facts['original']['palace']}宫）"
            f"→ {changed.get('name') or '无变卦'} "
            f"动爻{facts['moving_lines'] or '无'}"
        )
    return (
        f"{facts['dun']['text']} "
        f"值符{facts['zhifu']['star']}→{facts['zhifu']['landing_name']} "
        f"值使{facts['zhishi']['door']}→{facts['zhishi']['palace_name']}"
    )


def usage(client: httpx.Client, headers: dict[str, str]) -> dict[str, Any]:
    return client.get("/me/usage", headers=headers).json()


def buy(client: httpx.Client, headers: dict[str, str], plan_code: str) -> dict[str, Any]:
    """走一遍下单 + Mock 支付回调，把额度打到账户上。"""
    created = show("create order", client.post("/billing/orders", json={"plan_code": plan_code}, headers=headers))
    callback = created["mock_callback"]
    return show(
        "mock callback",
        client.post(
            callback["url"].removeprefix("/api/v1"),
            content=callback["body_raw"],
            headers={callback["header"]: callback["signature"], "Content-Type": "application/json"},
        ),
    )


def report(
    client: httpx.Client,
    headers: dict[str, str],
    chart_id: int,
    *,
    depth: str,
    key: str,
) -> dict[str, Any]:
    return show(
        f"{depth} report",
        client.post(
            f"/charts/{chart_id}/reports",
            json={"depth": depth, "topic": None, "skill_key": None},
            headers={**headers, "Idempotency-Key": key},
        ),
    )


def main() -> None:
    # 报告接口会真的调模型：单份 brief 实测 10～40s，默认 30s 超时会误报。
    # 连接类超时仍保持短，避免把“后端没起”也当成模型慢。
    timeout = httpx.Timeout(180.0, connect=10.0)
    with httpx.Client(base_url=BASE, timeout=timeout) as client:
        show("healthz", client.get(HEALTH_URL))

        plans = show("plans", client.get("/billing/plans"))
        print("  plans:", [item["code"] for item in plans["plans"]])

        email = f"smoke_{uuid.uuid4().hex[:8]}@example.com"
        registered = show(
            "register", client.post("/auth/register", json={"email": email, "password": "Passw0rd123"})
        )
        headers = {"Authorization": f"Bearer {registered['access_token']}"}
        show("me", client.get("/auth/me", headers=headers))

        about = show("about", client.get("/meta/about"))
        llm = about["llm"]
        print(
            f"  模型：{llm['mode']} · {llm['model']} · configured={llm['configured']}"
            f" · 今日调用 {llm['budget_used']}/{llm['budget_limit']}"
        )
        check(
            set(CASES).issubset(set(about["supported_domains"])),
            f"meta.supported_domains 应包含四术数，实际 {about['supported_domains']}",
        )
        if llm["mode"] != "openai_compatible" or not llm["configured"]:
            print("  提示：当前为演示模型（Mock），报告会是 degraded 模板；接真实模型见 README「接真实模型」")

        # ---- 1. 四术数排盘：免登录、不落库、不耗额度 ----
        for domain, payload in CASES.items():
            result = show(f"[{domain}] calculate", client.post(f"/charts/{domain}/calculate", json=payload))
            check(result["domain"] == domain, f"{domain} 返回的 domain 为 {result['domain']}")
            check(bool(result["algorithm_version"]), f"{domain} 缺少 algorithm_version")
            check(bool(result["convention"]), f"{domain} 缺少 convention 回显")
            check(bool(result["chart_facts"]), f"{domain} chart_facts 为空")
            print(f"  {hint(domain, result['chart_facts'])}")
            print(f"  规则 {len(result['triggered_rules'])} 条 · 提示 {len(result['warnings'])} 条")

        # ---- 2. 四术数保存：服务端重算后入库，不采信客户端盘面 ----
        chart_ids: dict[str, int] = {}
        for domain, payload in CASES.items():
            saved = show(
                f"[{domain}] save",
                client.post(f"/charts/{domain}", json={**payload, "title": f"联调{domain}"}, headers=headers),
            )
            chart_ids[domain] = saved["id"]
            check(saved["domain"] == domain, f"{domain} 保存后 domain 为 {saved['domain']}")
            detail = show(f"[{domain}] detail", client.get(f"/charts/{saved['id']}", headers=headers))
            check(detail["domain"] == domain, f"{domain} 详情 domain 为 {detail['domain']}")
            check(detail["chart_facts"] == saved["chart_facts"], f"{domain} 详情与保存返回的盘面不一致")
            listed = client.get("/charts", params={"domain": domain}, headers=headers)
            show(f"[{domain}] list", listed)
            check(
                all(item["domain"] == domain for item in listed.json()["items"]),
                f"按 domain={domain} 过滤时混入了其他术数",
            )

        # ---- 3. 未购额度时，详版解读必须 402（不能白给） ----
        blocked = client.post(
            f"/charts/{chart_ids['bazi']}/reports",
            json={"depth": "detailed", "topic": None, "skill_key": None},
            headers={**headers, "Idempotency-Key": f"smoke-blocked-{chart_ids['bazi']}"},
        )
        print("detailed without credits ->", blocked.status_code, blocked.json().get("error", {}).get("code"))
        check(blocked.status_code == 402, "无付费额度时详版解读应返回 402")

        # ---- 4. 购买额度 ----
        buy(client, headers, "member_month")
        before_all = usage(client, headers)
        print("  usage:", before_all)
        check(
            before_all["paid_balance"] >= len(CASES),
            f"购买后付费额度应 ≥ {len(CASES)}，实际 {before_all['paid_balance']}",
        )

        # ---- 5. 四术数各生成一次简版解读，并逐次核对账本 ----
        for domain, chart_id in chart_ids.items():
            before = usage(client, headers)
            data = report(client, headers, chart_id, depth="brief", key=f"smoke-{chart_id}-brief")
            after = usage(client, headers)
            print(
                f"  [{domain}] status={data['status']}"
                f" model={data['model_provider']}/{data['model_name']}"
                f" 技能={data['skill_version']} 引用={len(data['citations'])}"
            )
            check(
                data["skill_version"].startswith(f"{domain}."),
                f"{domain} 报告用的技能是 {data['skill_version']}，说明技能未按 domain 解析",
            )
            check(data["domain"] == domain, f"{domain} 报告的 domain 为 {data['domain']}")
            if data["status"] == "complete":
                check(
                    after["paid_balance"] == before["paid_balance"] - 1,
                    f"{domain} 完成态应扣 1 次付费额度（{before['paid_balance']} → {after['paid_balance']}）",
                )
            else:
                check(
                    after["paid_balance"] == before["paid_balance"],
                    f"{domain} 降级时必须退还额度（{before['paid_balance']} → {after['paid_balance']}）",
                )
                check(
                    bool(data["report"].get("uncertainties")),
                    f"{domain} 降级报告必须写明降级原因",
                )
            check(
                after["daily_free_used"] == before["daily_free_used"],
                f"{domain} 有付费额度时不应再消耗免费日额度",
            )

        # ---- 6. 幂等重放：同一 Idempotency-Key 不重复扣费、返回同一份报告 ----
        replay = report(
            client, headers, chart_ids["bazi"], depth="brief", key=f"smoke-{chart_ids['bazi']}-brief"
        )
        print("  replay same report:", replay["id"], "replayed:", (replay.get("validation") or {}).get("replayed"))

        # ---- 7. 详版解读（此时有额度） ----
        detailed = report(client, headers, chart_ids["bazi"], depth="detailed", key=f"smoke-{chart_ids['bazi']}-detailed")
        print("  detailed status:", detailed["status"], "citations:", len(detailed["citations"]))

        # ---- 8. 分享、导出、笔记、知识检索 ----
        share = show(
            "share",
            client.post(f"/charts/{chart_ids['qimen']}/share", json={"expires_in_days": 7}, headers=headers),
        )
        preview = show("share preview", client.get(f"/share/{share['token']}"))
        print("  preview pillars:", preview["pillars_text"])

        exports = client.get(f"/charts/{chart_ids['liuyao']}/export", params={"format": "md"}, headers=headers)
        print("export ->", exports.status_code)
        check(exports.status_code == 200, f"Markdown 导出失败：{exports.text[:200]}")
        print("  export head:", exports.text.splitlines()[0])

        show(
            "note",
            client.post(f"/charts/{chart_ids['ziwei']}/notes", json={"content": "联调笔记"}, headers=headers),
        )

        search = show("knowledge search", client.get("/knowledge/search", params={"q": "六合"}))
        print("  hits:", search["count"])

        print(
            json.dumps(
                {"ok": True, "email": email, "charts": chart_ids, "usage": usage(client, headers)},
                ensure_ascii=False,
            )
        )


if __name__ == "__main__":
    main()
