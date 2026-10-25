"""术数引擎注册表。

一个术数要接入，只需要在这里登记四样东西：
`domain` / `label` / 入参模型 / `(payload) -> ChartResult` 的计算函数。
`ChartResult` 外壳（八字段）保持不变，因此报告管线、技能解析、知识检索、
额度与前端分发都不需要为每个术数各写一套胶水。

新增术数时不要改 `charts.py`：`POST /charts/{domain}/calculate` 会自动识别。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from app.core.errors import AppError
from app.domains.bazi.engine import calculate as calculate_bazi
from app.domains.bazi.schemas import ChartResult
from app.domains.liuyao.engine import calculate as calculate_liuyao
from app.domains.liuyao.schemas import LiuyaoCalculateIn
from app.domains.qimen.engine import calculate as calculate_qimen
from app.domains.qimen.schemas import QimenCalculateIn
from app.domains.ziwei.engine import calculate as calculate_ziwei
from app.domains.ziwei.schemas import ZiweiCalculateIn
from app.schemas.charts import CalculateIn


class DomainNotSupported(AppError):
    def __init__(self, domain: str, supported: list[str]) -> None:
        super().__init__(
            "DOMAIN_NOT_SUPPORTED",
            f"暂不支持的术数「{domain}」，当前可用：{'、'.join(supported)}",
            status_code=400,
        )


@dataclass(frozen=True)
class EngineSpec:
    domain: str
    label: str
    input_model: type[BaseModel]
    calculate: Callable[[Any], ChartResult]
    #: 本引擎支持的流派/口径标识，前端据此渲染选项，避免把不支持的流派当成可选项
    schools: tuple[str, ...] = ("default_v1",)


def _calculate_bazi(payload: Any) -> ChartResult:
    return calculate_bazi(payload, payload.convention)


def _calculate_ziwei(payload: Any) -> ChartResult:
    return calculate_ziwei(payload, payload.convention)


def _calculate_liuyao(payload: Any) -> ChartResult:
    return calculate_liuyao(payload, payload.convention)


def _calculate_qimen(payload: Any) -> ChartResult:
    return calculate_qimen(payload, payload.convention)


ENGINES: dict[str, EngineSpec] = {
    "bazi": EngineSpec(
        domain="bazi",
        label="四柱八字",
        input_model=CalculateIn,
        calculate=_calculate_bazi,
    ),
    "ziwei": EngineSpec(
        domain="ziwei",
        label="紫微斗数",
        input_model=ZiweiCalculateIn,
        calculate=_calculate_ziwei,
        schools=("sanhe_default_v1",),
    ),
    "liuyao": EngineSpec(
        domain="liuyao",
        label="六爻",
        input_model=LiuyaoCalculateIn,
        calculate=_calculate_liuyao,
        schools=("jingfang_najia_v1",),
    ),
    "qimen": EngineSpec(
        domain="qimen",
        label="奇门遁甲",
        input_model=QimenCalculateIn,
        calculate=_calculate_qimen,
        schools=("chaibu_zhuanpan_v1",),
    ),
}


def supported_domains() -> list[str]:
    return list(ENGINES)


def get_engine(domain: str) -> EngineSpec:
    spec = ENGINES.get(domain)
    if spec is None:
        raise DomainNotSupported(domain, supported_domains())
    return spec
