"""节气时刻服务。

默认来源 `lunar_terms`：lunar-python（MIT License, 6tail）——经审查、可维护、
分钟级精度的历法库，符合产品文档 §6.1「优先采用经过审查、许可兼容且可维护的历法库」。

`builtin` 来源为本项目自研 Meeus 推算，仅用于离线兜底与交叉核验，
精度约 ±15 分钟，绝不作为默认口径。

所有对外时刻都是 **带时区的绝对时刻（UTC）**；lunar-python 内部使用北京时间。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo

from app.domains.calendar_core import astronomy

BEIJING = ZoneInfo("Asia/Shanghai")

# 二十四节气按太阳视黄经排序（小寒 285° 起）
TERM_LONGITUDE: dict[str, float] = {
    "小寒": 285, "大寒": 300, "立春": 315, "雨水": 330,
    "惊蛰": 345, "春分": 0, "清明": 15, "谷雨": 30,
    "立夏": 45, "小满": 60, "芒种": 75, "夏至": 90,
    "小暑": 105, "大暑": 120, "立秋": 135, "处暑": 150,
    "白露": 165, "秋分": 180, "寒露": 195, "霜降": 210,
    "立冬": 225, "小雪": 240, "大雪": 255, "冬至": 270,
}

# 十二节（定月），顺序即 寅→丑 的月份推进
JIE_NAMES: tuple[str, ...] = (
    "立春", "惊蛰", "清明", "立夏", "芒种", "小暑",
    "立秋", "白露", "寒露", "立冬", "大雪", "小寒",
)

# 二十四节气按公历年内的时间先后排列（奇门定局要 节+中气 一起看）
JIEQI_NAMES: tuple[str, ...] = tuple(TERM_LONGITUDE)


@dataclass(frozen=True)
class TermMoment:
    name: str
    instant: datetime  # aware, UTC
    source: str

    def local(self, tz: ZoneInfo) -> datetime:
        return self.instant.astimezone(tz)

    def to_dict(self, tz: ZoneInfo) -> dict[str, str]:
        local = self.local(tz)
        return {
            "name": self.name,
            "instant_utc": self.instant.isoformat(),
            "local": local.strftime("%Y-%m-%d %H:%M:%S"),
            "timezone": str(tz),
            "source": self.source,
        }


def _from_lunar_naive(dt: datetime) -> datetime:
    """lunar-python 返回的是北京时间 naive datetime → 转成 UTC 绝对时刻。"""
    return dt.replace(tzinfo=BEIJING).astimezone(timezone.utc)


class _LunarProvider:
    name = "lunar_python"

    def prev_next_jie(self, instant: datetime) -> tuple[TermMoment, TermMoment]:
        from lunar_python import Solar

        bj = instant.astimezone(BEIJING)
        lunar = Solar.fromYmdHms(bj.year, bj.month, bj.day, bj.hour, bj.minute, bj.second).getLunar()
        prev = lunar.getPrevJie()
        nxt = lunar.getNextJie()
        return (
            TermMoment(prev.getName(), _from_lunar_naive(_lunar_solar_dt(prev)), self.name),
            TermMoment(nxt.getName(), _from_lunar_naive(_lunar_solar_dt(nxt)), self.name),
        )

    def prev_next_term(self, instant: datetime) -> tuple[TermMoment, TermMoment]:
        """二十四节气（含中气）：奇门定局依赖冬至、夏至、春分等中气，不能只看节。"""
        from lunar_python import Solar

        bj = instant.astimezone(BEIJING)
        lunar = Solar.fromYmdHms(bj.year, bj.month, bj.day, bj.hour, bj.minute, bj.second).getLunar()
        prev = lunar.getPrevJieQi()
        nxt = lunar.getNextJieQi()
        return (
            TermMoment(prev.getName(), _from_lunar_naive(_lunar_solar_dt(prev)), self.name),
            TermMoment(nxt.getName(), _from_lunar_naive(_lunar_solar_dt(nxt)), self.name),
        )


def _lunar_solar_dt(jieqi) -> datetime:
    solar = jieqi.getSolar()
    return datetime(
        solar.getYear(), solar.getMonth(), solar.getDay(),
        solar.getHour(), solar.getMinute(), solar.getSecond(),
    )


class _BuiltinProvider:
    name = "builtin_meeus"

    def __init__(self) -> None:
        self._cache: dict[int, list[TermMoment]] = {}
        self._all_cache: dict[int, list[TermMoment]] = {}

    def _terms_of_year(self, year: int) -> list[TermMoment]:
        cached = self._cache.get(year)
        if cached is not None:
            return cached
        moments: list[TermMoment] = []
        for name, longitude in TERM_LONGITUDE.items():
            if name not in JIE_NAMES:
                continue
            # 小寒/大寒属于上一干支年，但公历上在当年 1 月
            instant = astronomy.solar_term_instant_utc(year, longitude)
            # 修正：若解落在同年但黄经周期错位，向前/后平移一年
            if abs((instant - datetime(year, 1, 1, tzinfo=timezone.utc)).days) > 380:
                instant = instant + timedelta(days=365)
            moments.append(TermMoment(name, instant, self.name))
        moments.sort(key=lambda m: m.instant)
        self._cache[year] = moments
        return moments

    def prev_next_jie(self, instant: datetime) -> tuple[TermMoment, TermMoment]:
        year = instant.astimezone(timezone.utc).year
        pool: list[TermMoment] = []
        for y in (year - 1, year, year + 1):
            pool.extend(self._terms_of_year(y))
        pool.sort(key=lambda m: m.instant)
        prev = pool[0]
        nxt = pool[-1]
        for i, moment in enumerate(pool):
            if moment.instant <= instant:
                prev = moment
                nxt = pool[i + 1] if i + 1 < len(pool) else pool[-1]
        return prev, nxt

    def _all_terms_of_year(self, year: int) -> list[TermMoment]:
        cached = self._all_cache.get(year)
        if cached is not None:
            return cached
        moments = [
            TermMoment(name, astronomy.solar_term_instant_utc(year, longitude), self.name)
            for name, longitude in TERM_LONGITUDE.items()
        ]
        moments.sort(key=lambda m: m.instant)
        self._all_cache[year] = moments
        return moments

    def prev_next_term(self, instant: datetime) -> tuple[TermMoment, TermMoment]:
        year = instant.astimezone(timezone.utc).year
        pool: list[TermMoment] = []
        for y in (year - 1, year, year + 1):
            pool.extend(self._all_terms_of_year(y))
        pool.sort(key=lambda m: m.instant)
        prev = pool[0]
        nxt = pool[-1]
        for i, moment in enumerate(pool):
            if moment.instant <= instant:
                prev = moment
                nxt = pool[i + 1] if i + 1 < len(pool) else pool[-1]
        return prev, nxt


class SolarTermService:
    """按需切换来源；默认 auto = 优先 lunar-python，缺失时回退自研。"""

    def __init__(self, provider: str = "auto") -> None:
        self._builtin = _BuiltinProvider()
        if provider == "auto":
            try:
                import lunar_python  # noqa: F401

                self._provider = _LunarProvider()
            except ImportError:  # pragma: no cover - 兜底路径
                self._provider = self._builtin
        elif provider == "builtin":
            self._provider = self._builtin
        else:
            self._provider = _LunarProvider()
        self.source = self._provider.name

    def prev_next_jie(self, instant: datetime) -> tuple[TermMoment, TermMoment]:
        return self._provider.prev_next_jie(instant)

    def prev_jie(self, instant: datetime) -> TermMoment:
        return self.prev_next_jie(instant)[0]

    def next_jie(self, instant: datetime) -> TermMoment:
        return self.prev_next_jie(instant)[1]

    def prev_term(self, instant: datetime) -> TermMoment:
        """二十四节气中的上一个（含中气）；奇门定局用。"""
        return self._provider.prev_next_term(instant)[0]

    def builtin_prev_next(self, instant: datetime) -> tuple[TermMoment, TermMoment]:
        """交叉核验用：始终返回自研推算结果。"""
        return self._builtin.prev_next_jie(instant)


@lru_cache
def get_term_service(provider: str = "auto") -> SolarTermService:
    return SolarTermService(provider)
