"""紫微飞星串联：只列「哪一宫干化什么星、又落到哪一宫」的链路。

边界（与口径说明一致）：
- 不取用神、不论吉凶、不把「禄转忌」读成事件；
- 链路只做结构展示，最多 `depth` 跳，超过 `limit` 条即截断；
- 遇到重复宫位视为环路，当前链停止并标 `cycle=True`。

为什么默认只从命宫/身宫起：
12 宫 × 4 化 × 每层 4 条，两跳就是 192 条，面板会淹没重点。起点可配置，
给了大限/流年时再追加对应宫位。
"""

from __future__ import annotations

from typing import Any

DEFAULT_DEPTH = 2
DEFAULT_LIMIT = 200


def build_chains(
    palace_transformations: list[dict[str, Any]],
    starts: list[str],
    *,
    depth: int = DEFAULT_DEPTH,
    limit: int = DEFAULT_LIMIT,
) -> dict[str, Any]:
    by_from: dict[str, list[dict[str, Any]]] = {}
    for row in palace_transformations:
        by_from.setdefault(row["from_palace"], []).append(row)

    chains: list[dict[str, Any]] = []
    truncated = False

    for start in starts:
        seeds = by_from.get(start, [])
        for seed in seeds:
            if len(chains) >= limit:
                truncated = True
                break
            hops = [
                {
                    "palace": seed["from_palace"],
                    "type": seed["type"],
                    "star": seed["star"],
                    "to_palace": seed["to_palace"],
                }
            ]
            path = [start, seed["to_palace"]]
            current = seed["to_palace"]
            cycle = False
            for _ in range(1, max(depth, 1)):
                if current in path[:-1]:
                    cycle = True
                    break
                nxt = by_from.get(current, [])
                if not nxt:
                    break
                # 每一跳只取第一条，避免 4^depth 爆炸；四化类型在面板里仍完整可见
                step = nxt[0]
                hops.append(
                    {
                        "palace": current,
                        "type": step["type"],
                        "star": step["star"],
                        "to_palace": step["to_palace"],
                    }
                )
                path.append(step["to_palace"])
                if step["to_palace"] in path[:-1]:
                    cycle = True
                    break
                current = step["to_palace"]
            chains.append(
                {
                    "start_palace": start,
                    "start_stem": seed["stem"],
                    "hops": hops,
                    "cycle": cycle,
                }
            )
        if truncated:
            break

    return {
        "depth": depth,
        "starts": starts,
        "chains": chains,
        "truncated": truncated,
        "rule": "只列宫干四化的落宫链路，不推事件、不取用神；每跳取该宫第一条四化以避免组合爆炸",
    }
