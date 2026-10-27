"""进程内指标采集与 Prometheus 文本暴露。

为什么自己写而不引 prometheus_client：这个项目只有一个后端进程，
需要的指标是「按路由的请求数/耗时」「排盘成功失败」「模型调用与降级」
这十来项。引一个库要连带 client_python 的多进程模式、registry 生命周期、
gauge 回调语义 —— 成本远大于收益。这里用固定标签组合的计数器 + 分桶直方图，
一百多行能覆盖，且读代码就能看懂。

## 设计取舍

**标签基数必须有界。** 路由按「模板」而不是实际路径打标签：`/charts/123`
会归到 `/charts/{chart_id}`，否则每个 id 都是一个新时间序列，内存会一直涨。
所以这里依赖 FastAPI 的 `request.scope["route"].path`，而不是 `request.url.path`。

**直方图用固定桶，不做动态分位数。** 排盘是毫秒级、报告是 20–40 秒级，
两者的桶边界完全不同，因此分开两组桶，而不是一套通用桶。

**线程安全用一把锁。** 采集在请求路径上，代价是几十纳秒的 dict 自增；
CPython 的 GIL 下裸 dict 自增也不是原子的（+= 是读-改-写），
一把全局锁比逐指标锁更简单，且争用可忽略。
"""

from __future__ import annotations

import threading
from typing import Any

#: 请求耗时桶（秒）。覆盖排盘（毫秒）到报告（数十秒）。
_HTTP_BUCKETS: tuple[float, ...] = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0)
#: 排盘耗时桶（秒）。确定性引擎应在毫秒级，超过 1 秒就是异常。
_CHART_BUCKETS: tuple[float, ...] = (0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 5.0)

_lock = threading.Lock()

#: counter 名称 → {(标签元组): 值}
_counters: dict[str, dict[tuple[tuple[str, str], ...], float]] = {}
#: histogram 名称 → (桶边界, {标签元组: [各桶计数..., 总和, 总数]})
_histograms: dict[str, tuple[tuple[float, ...], dict[tuple[tuple[str, str], ...], list[float]]]] = {}
#: gauge 名称 → (帮助文本, 取值函数)
_gauges: dict[str, tuple[str, Any]] = {}


def _key(labels: dict[str, str]) -> tuple[tuple[str, str], ...]:
    return tuple(sorted(labels.items()))


def inc(name: str, labels: dict[str, str] | None = None, value: float = 1.0) -> None:
    """计数器自增。标签组合必须稳定 —— 不要把 id、邮箱、原文放进标签。"""
    k = _key(labels or {})
    with _lock:
        bucket = _counters.setdefault(name, {})
        bucket[k] = bucket.get(k, 0.0) + value


def observe(name: str, seconds: float, labels: dict[str, str] | None = None) -> None:
    """直方图打点。桶边界由指标名决定，未登记的走 HTTP 桶。"""
    buckets = _CHART_BUCKETS if name.startswith("chart_") else _HTTP_BUCKETS
    k = _key(labels or {})
    with _lock:
        _, series = _histograms.setdefault(name, (buckets, {}))
        slot = series.get(k)
        if slot is None:
            slot = [0.0] * (len(buckets) + 2)  # 各桶 + sum + count
            series[k] = slot
        for index, edge in enumerate(buckets):
            if seconds <= edge:
                slot[index] += 1
        slot[-2] += seconds
        slot[-1] += 1


def register_gauge(name: str, help_text: str, supplier: Any) -> None:
    """注册一个「取值时才计算」的 gauge（如数据库连接池占用）。"""
    _gauges[name] = (help_text, supplier)


def reset() -> None:
    """测试用：清空所有指标，避免用例之间互相污染。"""
    with _lock:
        _counters.clear()
        _histograms.clear()


def _fmt_labels(pairs: tuple[tuple[str, str], ...]) -> str:
    if not pairs:
        return ""
    inner = ",".join(f'{key}="{value}"' for key, value in pairs)
    return "{" + inner + "}"


def render() -> str:
    """渲染成 Prometheus 文本格式（text/plain; version=0.0.4）。"""
    lines: list[str] = []
    with _lock:
        for name, series in sorted(_counters.items()):
            lines.append(f"# TYPE {name} counter")
            for pairs, value in sorted(series.items()):
                lines.append(f"{name}{_fmt_labels(pairs)} {value:g}")
        for name, (buckets, series) in sorted(_histograms.items()):
            lines.append(f"# TYPE {name} histogram")
            for pairs, slot in sorted(series.items()):
                for index, edge in enumerate(buckets):
                    labels = pairs + (("le", f"{edge:g}"),)
                    lines.append(f"{name}_bucket{_fmt_labels(labels)} {slot[index]:g}")
                labels = pairs + (("le", "+Inf"),)
                lines.append(f"{name}_bucket{_fmt_labels(labels)} {slot[-1]:g}")
                lines.append(f"{name}_sum{_fmt_labels(pairs)} {slot[-2]:g}")
                lines.append(f"{name}_count{_fmt_labels(pairs)} {slot[-1]:g}")
        gauges = list(_gauges.items())

    # gauge 取值可能查数据库，放在锁外避免阻塞请求路径
    for name, (help_text, supplier) in sorted(gauges):
        try:
            value = supplier()
        except Exception:  # pragma: no cover - 采集失败不能影响 /metrics
            continue
        lines.append(f"# HELP {name} {help_text}")
        lines.append(f"# TYPE {name} gauge")
        lines.append(f"{name} {value:g}")
    return "\n".join(lines) + "\n"
