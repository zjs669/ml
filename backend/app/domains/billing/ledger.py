"""额度账本：reserve → settle / refund 三态，加 grant 发放。

规则：
- `balance = sum(units)`，grant 为正、reserve 为负、settle 为差额（预扣 - 实扣）、refund 为退回；
- 免费日额度不进余额，用 `units=0, note='free'` 的 reserve 行计数，避免"送出去的额度"被滥用；
- `idempotency_key` 唯一索引 + 先查后插 + 唯一冲突回查，保证并发下只生效一次。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import utcnow
from app.core.errors import QuotaExceeded
from app.models import UsageLedger

BEIJING = ZoneInfo("Asia/Shanghai")

EVENT_GRANT = "grant"
EVENT_RESERVE = "reserve"
EVENT_SETTLE = "settle"
EVENT_REFUND = "refund"

SOURCE_FREE = "free"
SOURCE_PAID = "paid"


@dataclass
class Reservation:
    key: str
    ledger_id: int
    units: int
    source: str

    @property
    def paid(self) -> bool:
        return self.source == SOURCE_PAID


def daily_window_start() -> datetime:
    """按北京时间自然日切分，落库仍用 UTC。"""
    local_now = datetime.now(BEIJING)
    local_start = datetime.combine(local_now.date(), time.min, tzinfo=BEIJING)
    return local_start.astimezone(timezone.utc).replace(tzinfo=None)


def paid_balance(session: Session, user_id: int) -> int:
    total = session.scalar(
        select(func.coalesce(func.sum(UsageLedger.units), 0)).where(UsageLedger.user_id == user_id)
    )
    return max(int(total or 0), 0)


def free_used_today(session: Session, user_id: int) -> int:
    """当日已用的免费次数 = 免费预扣行 - 已退款的免费预扣行。

    降级或失败时 `refund` 会写一行 `reference_id=<预扣行 id>` 的退回记录，
    这里必须把它扣掉，否则「失败退还额度」只在付费额度上生效、免费次数仍然被吃掉。
    """
    reserved_ids = session.scalars(
        select(UsageLedger.id).where(
            UsageLedger.user_id == user_id,
            UsageLedger.event_type == EVENT_RESERVE,
            UsageLedger.note == SOURCE_FREE,
            UsageLedger.created_at >= daily_window_start(),
        )
    ).all()
    if not reserved_ids:
        return 0
    live = {str(item) for item in reserved_ids}
    refunded_refs = session.scalars(
        select(UsageLedger.reference_id).where(
            UsageLedger.user_id == user_id,
            UsageLedger.event_type == EVENT_REFUND,
            UsageLedger.reference_type == "reservation",
        )
    ).all()
    refunded = len(live & {ref for ref in refunded_refs if ref})
    return max(len(live) - refunded, 0)


def free_remaining(session: Session, user_id: int) -> int:
    return max(settings.daily_free_report_limit - free_used_today(session, user_id), 0)


def _existing(session: Session, key: str) -> UsageLedger | None:
    return session.scalar(select(UsageLedger).where(UsageLedger.idempotency_key == key))


def find_event(session: Session, key: str) -> UsageLedger | None:
    """按幂等键查已有账本行；上层据此判断“这次请求是不是重放”。"""
    return _existing(session, key)


def _append(
    session: Session,
    *,
    user_id: int,
    event_type: str,
    units: int,
    key: str,
    reference_type: str | None,
    reference_id: str | None,
    note: str | None,
) -> UsageLedger:
    """写一行账本；key 已存在时直接返回旧行（幂等）。"""
    found = _existing(session, key)
    if found is not None:
        return found
    entry = UsageLedger(
        user_id=user_id,
        event_type=event_type,
        units=units,
        reference_type=reference_type,
        reference_id=reference_id,
        note=note,
        idempotency_key=key,
    )
    try:
        with session.begin_nested():
            session.add(entry)
            session.flush()
    except IntegrityError:
        found = _existing(session, key)
        if found is None:  # pragma: no cover - 唯一冲突却查不到属数据异常
            raise
        return found
    return entry


def reserve(
    session: Session,
    *,
    user_id: int,
    reference_type: str,
    reference_id: str,
    idempotency_key: str,
    units: int = 1,
    allow_free: bool = True,
) -> Reservation:
    """预扣一次调用额度。付费额度优先，其次免费日额度；两者皆无则 402。"""
    found = _existing(session, idempotency_key)
    if found is not None:
        return Reservation(
            key=idempotency_key,
            ledger_id=found.id,
            units=abs(found.units) if found.note == SOURCE_PAID else 0,
            source=found.note or SOURCE_FREE,
        )

    if paid_balance(session, user_id) >= units:
        row = _append(
            session,
            user_id=user_id,
            event_type=EVENT_RESERVE,
            units=-units,
            key=idempotency_key,
            reference_type=reference_type,
            reference_id=reference_id,
            note=SOURCE_PAID,
        )
        return Reservation(key=idempotency_key, ledger_id=row.id, units=units, source=SOURCE_PAID)

    if allow_free and free_remaining(session, user_id) > 0:
        row = _append(
            session,
            user_id=user_id,
            event_type=EVENT_RESERVE,
            units=0,
            key=idempotency_key,
            reference_type=reference_type,
            reference_id=reference_id,
            note=SOURCE_FREE,
        )
        return Reservation(key=idempotency_key, ledger_id=row.id, units=0, source=SOURCE_FREE)

    raise QuotaExceeded(
        f"今日免费额度已用完（每日 {settings.daily_free_report_limit} 次），"
        "购买单次解读或会员后可继续生成。"
    )


def settle(session: Session, reservation: Reservation, *, actual_units: int | None = None) -> UsageLedger:
    """按实际消耗结算：只把「预扣 - 实扣」的差额退回。"""
    actual = reservation.units if actual_units is None else actual_units
    delta = reservation.units - actual
    return _append(
        session,
        user_id=_owner_of(session, reservation),
        event_type=EVENT_SETTLE,
        units=delta,
        key=f"{reservation.key}:settle",
        reference_type="reservation",
        reference_id=str(reservation.ledger_id),
        note=SOURCE_PAID if reservation.paid else SOURCE_FREE,
    )


def refund(session: Session, reservation: Reservation, *, reason: str = "upstream_failed") -> UsageLedger:
    """调用失败：预扣全额退回（幂等，重复调用不会重复退）。"""
    return _append(
        session,
        user_id=_owner_of(session, reservation),
        event_type=EVENT_REFUND,
        units=reservation.units,
        key=f"{reservation.key}:refund",
        reference_type="reservation",
        reference_id=str(reservation.ledger_id),
        note=reason[:255],
    )


def grant(
    session: Session,
    *,
    user_id: int,
    units: int,
    reason: str,
    idempotency_key: str,
    reference_type: str | None = "order",
    reference_id: str | None = None,
) -> UsageLedger:
    return _append(
        session,
        user_id=user_id,
        event_type=EVENT_GRANT,
        units=units,
        key=idempotency_key,
        reference_type=reference_type,
        reference_id=reference_id,
        note=reason[:255],
    )


def _owner_of(session: Session, reservation: Reservation) -> int:
    user_id = session.scalar(select(UsageLedger.user_id).where(UsageLedger.id == reservation.ledger_id))
    if user_id is None:  # pragma: no cover - 账本被外部删除
        raise QuotaExceeded("额度记录异常，请联系支持")
    return int(user_id)


def snapshot(session: Session, user_id: int) -> dict:
    """给前端展示的额度视图，全部实时聚合，不缓存。"""
    used = free_used_today(session, user_id)
    limit = settings.daily_free_report_limit
    balance = paid_balance(session, user_id)
    return {
        "daily_free_limit": limit,
        "daily_free_used": used,
        "daily_free_remaining": max(limit - used, 0),
        "paid_balance": balance,
        "daily_free_reset_at": (daily_window_start() + timedelta(days=1)).isoformat() + "Z",
        "can_generate": balance > 0 or used < limit,
        "server_time_utc": utcnow().isoformat() + "Z",
    }
