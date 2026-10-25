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
from typing import Any, Literal

from pydantic import BaseModel

from app.core.errors import AppError
from app.domains.almanac.engine import calculate as calculate_almanac
from app.domains.almanac.schemas import AlmanacCalculateIn
from app.domains.astrology.engine import calculate as calculate_astrology
from app.domains.astrology.schemas import AstrologyCalculateIn
from app.domains.bazi.engine import calculate as calculate_bazi
from app.domains.bazi.schemas import ChartResult
from app.domains.liuyao.engine import calculate as calculate_liuyao
from app.domains.liuyao.schemas import LiuyaoCalculateIn
from app.domains.dream.engine import calculate as calculate_dream
from app.domains.dream.schemas import DreamCalculateIn
from app.domains.hepan.engine import calculate as calculate_hepan
from app.domains.hepan.schemas import HepanCalculateIn
from app.domains.mbti.engine import calculate as calculate_mbti
from app.domains.mbti.schemas import MbtiCalculateIn
from app.domains.meihua.engine import calculate as calculate_meihua
from app.domains.meihua.schemas import MeihuaCalculateIn
from app.domains.qimen.engine import calculate as calculate_qimen
from app.domains.qimen.schemas import QimenCalculateIn
from app.domains.taiyi.engine import calculate as calculate_taiyi
from app.domains.taiyi.schemas import TaiyiCalculateIn
from app.domains.tarot.engine import calculate as calculate_tarot
from app.domains.tarot.schemas import TarotCalculateIn
from app.domains.xiaoliuren.engine import calculate as calculate_xiaoliuren
from app.domains.xiaoliuren.schemas import XiaoliurenCalculateIn
from app.domains.ziwei.engine import calculate as calculate_ziwei
from app.domains.ziwei.schemas import ZiweiCalculateIn
from app.domains.ziwei_flying.engine import calculate as calculate_ziwei_flying
from app.domains.ziwei_flying.schemas import FlyingCalculateIn
from app.domains.ziwei_horoscope.engine import calculate as calculate_ziwei_horoscope
from app.domains.ziwei_horoscope.schemas import HoroscopeCalculateIn
from app.schemas.charts import CalculateIn


class DomainNotSupported(AppError):
    def __init__(self, domain: str, supported: list[str]) -> None:
        super().__init__(
            "DOMAIN_NOT_SUPPORTED",
            f"暂不支持的术数「{domain}」，当前可用：{'、'.join(supported)}",
            status_code=400,
        )


#: 引擎类别。deterministic = 纯函数算出可核验的盘面事实；
#: generative = 只能产出「观察 + 解释」，事实部分只记录用户输入，不放模型输出。
EngineKind = Literal["deterministic", "generative"]


@dataclass(frozen=True)
class EngineSpec:
    domain: str
    label: str
    input_model: type[BaseModel]
    calculate: Callable[[Any], ChartResult]
    #: 本引擎支持的流派/口径标识，前端据此渲染选项，避免把不支持的流派当成可选项
    schools: tuple[str, ...] = ("default_v1",)
    #: 引擎类别。生成式域不允许产出 triggered_rules，报告校验据此走不同分支
    kind: EngineKind = "deterministic"
    #: 是否需要用户上传图片（面相 / 手相）
    requires_media: bool = False


def _calculate_almanac(payload: Any) -> ChartResult:
    return calculate_almanac(payload, payload.convention)


def _calculate_astrology(payload: Any) -> ChartResult:
    return calculate_astrology(payload, payload.convention)


def _calculate_bazi(payload: Any) -> ChartResult:
    return calculate_bazi(payload, payload.convention)


def _calculate_ziwei(payload: Any) -> ChartResult:
    return calculate_ziwei(payload, payload.convention)


def _calculate_ziwei_horoscope(payload: Any) -> ChartResult:
    return calculate_ziwei_horoscope(payload, payload.convention)


def _calculate_ziwei_flying(payload: Any) -> ChartResult:
    return calculate_ziwei_flying(payload, payload.convention)


def _calculate_liuyao(payload: Any) -> ChartResult:
    return calculate_liuyao(payload, payload.convention)


def _calculate_qimen(payload: Any) -> ChartResult:
    return calculate_qimen(payload, payload.convention)


def _calculate_meihua(payload: Any) -> ChartResult:
    return calculate_meihua(payload, payload.convention)


def _calculate_hepan(payload: Any) -> ChartResult:
    return calculate_hepan(payload, payload.convention)


def _calculate_dream(payload: Any) -> ChartResult:
    return calculate_dream(payload, payload.convention)


def _calculate_mbti(payload: Any) -> ChartResult:
    return calculate_mbti(payload, payload.convention)


def _calculate_taiyi(payload: Any) -> ChartResult:
    return calculate_taiyi(payload, payload.convention)


def _calculate_tarot(payload: Any) -> ChartResult:
    return calculate_tarot(payload, payload.convention)


def _calculate_xiaoliuren(payload: Any) -> ChartResult:
    return calculate_xiaoliuren(payload, payload.convention)


ENGINES: dict[str, EngineSpec] = {
    "astrology": EngineSpec(
        domain="astrology",
        label="西洋占星",
        input_model=AstrologyCalculateIn,
        calculate=_calculate_astrology,
        schools=("simplified_sun_moon_v1",),
    ),
    "almanac": EngineSpec(
        domain="almanac",
        label="黄历",
        input_model=AlmanacCalculateIn,
        calculate=_calculate_almanac,
        schools=("tongshu_daily_v1",),
    ),
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
    "dream": EngineSpec(
        domain="dream",
        label="解梦",
        input_model=DreamCalculateIn,
        calculate=_calculate_dream,
        schools=("keyword_lookup_v1",),
    ),
    "hepan": EngineSpec(
        domain="hepan",
        label="关系合盘",
        input_model=HepanCalculateIn,
        calculate=_calculate_hepan,
        schools=("bazi_cross_v1",),
    ),
    "mbti": EngineSpec(
        domain="mbti",
        label="性格问卷",
        input_model=MbtiCalculateIn,
        calculate=_calculate_mbti,
        schools=("self_authored_four_dim_v1",),
    ),
    "meihua": EngineSpec(
        domain="meihua",
        label="梅花易数",
        input_model=MeihuaCalculateIn,
        calculate=_calculate_meihua,
        schools=("shaoyong_tongxing_v1",),
    ),
    "ziwei_horoscope": EngineSpec(
        domain="ziwei_horoscope",
        label="紫微运限",
        input_model=HoroscopeCalculateIn,
        calculate=_calculate_ziwei_horoscope,
        schools=("sanhe_default_v1",),
    ),
    "ziwei_flying": EngineSpec(
        domain="ziwei_flying",
        label="紫微飞星",
        input_model=FlyingCalculateIn,
        calculate=_calculate_ziwei_flying,
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
    "taiyi": EngineSpec(
        domain="taiyi",
        label="太乙九星",
        input_model=TaiyiCalculateIn,
        calculate=_calculate_taiyi,
        schools=("jiuxing_observation_v1",),
    ),
    "tarot": EngineSpec(
        domain="tarot",
        label="塔罗",
        input_model=TarotCalculateIn,
        calculate=_calculate_tarot,
        schools=("rider_waite_v1",),
    ),
    "xiaoliuren": EngineSpec(
        domain="xiaoliuren",
        label="小六壬",
        input_model=XiaoliurenCalculateIn,
        calculate=_calculate_xiaoliuren,
        schools=("liugong_digui_v1",),
    ),
}


def supported_domains() -> list[str]:
    return list(ENGINES)


def get_engine(domain: str) -> EngineSpec:
    spec = ENGINES.get(domain)
    if spec is None:
        raise DomainNotSupported(domain, supported_domains())
    return spec
