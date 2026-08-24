from __future__ import annotations

import json
import socket
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from autofag.clock import Clock
from autofag.models import CourseCode, DeliveryResult, Notification, RowStatus, WatchEntry
from autofag.storage.db import (
    EnrollmentLedgerRow,
    NotificationDeliveryRow,
    RequestBudgetRow,
    RunRow,
    StatusObservationRow,
    WatchEntryRow,
)

LEDGER_ATTEMPTED = "attempted"
LEDGER_CONFIRMED = "confirmed"
LEDGER_UNVERIFIED = "unverified"
LEDGER_FAILED = "failed"


class RunAlreadyActive(RuntimeError):
    pass


class WatchlistRepository:
    def __init__(self, session_factory: sessionmaker, clock: Clock) -> None:
        self._session_factory = session_factory
        self._clock = clock

    def upsert(self, entry: WatchEntry) -> None:
        with self._session_factory() as session, session.begin():
            row = session.scalar(
                select(WatchEntryRow).where(WatchEntryRow.course_code == entry.code.value)
            )
            if row is None:
                row = WatchEntryRow(course_code=entry.code.value, created_at=self._clock.now())
                session.add(row)
            row.course_name = entry.name
            row.auto_enroll = int(entry.auto_enroll)
            row.opens_at = entry.opens_at
            row.expires_at = entry.expires_at
            row.last_status = entry.last_status.value if entry.last_status else None
            row.last_status_text = entry.last_status_text
            row.last_status_change_at = entry.last_status_change_at
            row.stopped_reason = entry.stopped_reason
            row.dialog_choices = json.dumps(entry.dialog_choices, ensure_ascii=False)

    def remove(self, code: CourseCode) -> None:
        with self._session_factory() as session, session.begin():
            row = session.scalar(
                select(WatchEntryRow).where(WatchEntryRow.course_code == code.value)
            )
            if row is not None:
                session.delete(row)

    def all_entries(self) -> list[WatchEntry]:
        with self._session_factory() as session:
            rows = session.scalars(select(WatchEntryRow).order_by(WatchEntryRow.course_code)).all()
        return [_to_entry(row) for row in rows]

    def active_entries(self) -> list[WatchEntry]:
        return [entry for entry in self.all_entries() if not entry.is_stopped]

    def record_observation(self, code: CourseCode, status: RowStatus, status_text: str) -> None:
        with self._session_factory() as session, session.begin():
            session.add(
                StatusObservationRow(
                    course_code=code.value,
                    status=status.value,
                    status_text=status_text,
                    observed_at=self._clock.now(),
                )
            )


class EnrollmentLedger:
    def __init__(self, session_factory: sessionmaker, clock: Clock) -> None:
        self._session_factory = session_factory
        self._clock = clock

    def has_record(self, code: CourseCode, run_id: str, states: tuple[str, ...]) -> bool:
        with self._session_factory() as session:
            row = session.scalar(
                select(EnrollmentLedgerRow)
                .where(EnrollmentLedgerRow.course_code == code.value)
                .where(EnrollmentLedgerRow.run_id == run_id)
                .where(EnrollmentLedgerRow.state.in_(states))
            )
        return row is not None

    def record_attempt(self, code: CourseCode, term: str, run_id: str) -> int:
        now = self._clock.now()
        with self._session_factory() as session, session.begin():
            row = EnrollmentLedgerRow(
                course_code=code.value,
                term=term,
                state=LEDGER_ATTEMPTED,
                run_id=run_id,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            session.flush()
            return row.id

    def settle(self, ledger_id: int, state: str, detail: str) -> None:
        with self._session_factory() as session, session.begin():
            row = session.get(EnrollmentLedgerRow, ledger_id)
            if row is None:
                return
            row.state = state
            row.detail = detail
            row.updated_at = self._clock.now()

    def count_state(self, code: CourseCode, run_id: str, state: str) -> int:
        with self._session_factory() as session:
            rows = session.scalars(
                select(EnrollmentLedgerRow)
                .where(EnrollmentLedgerRow.course_code == code.value)
                .where(EnrollmentLedgerRow.run_id == run_id)
                .where(EnrollmentLedgerRow.state == state)
            ).all()
        return len(rows)


class BudgetStore:
    def __init__(self, session_factory: sessionmaker, clock: Clock) -> None:
        self._session_factory = session_factory
        self._clock = clock

    def consume(self, limit_per_hour: int) -> bool:
        bucket = self._clock.now().strftime("%Y-%m-%dT%H")
        with self._session_factory() as session, session.begin():
            row = session.scalar(
                select(RequestBudgetRow).where(RequestBudgetRow.hour_bucket == bucket)
            )
            if row is None:
                row = RequestBudgetRow(hour_bucket=bucket, request_count=0)
                session.add(row)
                session.flush()
            if row.request_count >= limit_per_hour:
                return False
            row.request_count += 1
            row.last_request_monotonic = self._clock.monotonic()
            return True

    def used_this_hour(self) -> int:
        bucket = self._clock.now().strftime("%Y-%m-%dT%H")
        with self._session_factory() as session:
            row = session.scalar(
                select(RequestBudgetRow).where(RequestBudgetRow.hour_bucket == bucket)
            )
        return row.request_count if row else 0


class DeliveryLog:
    def __init__(self, session_factory: sessionmaker, clock: Clock) -> None:
        self._session_factory = session_factory
        self._clock = clock

    def was_delivered_recently(self, notification: Notification, window_seconds: float) -> bool:
        cutoff = self._clock.now() - timedelta(seconds=window_seconds)
        with self._session_factory() as session:
            row = session.scalar(
                select(NotificationDeliveryRow)
                .where(NotificationDeliveryRow.dedupe_key == notification.dedupe_key())
                .where(NotificationDeliveryRow.delivered == 1)
                .where(NotificationDeliveryRow.created_at >= cutoff)
            )
        return row is not None

    def count_delivered(self, notification: Notification, since: datetime) -> int:
        with self._session_factory() as session:
            rows = session.scalars(
                select(NotificationDeliveryRow)
                .where(NotificationDeliveryRow.kind == notification.kind.value)
                .where(
                    NotificationDeliveryRow.course_code
                    == (notification.course_code.value if notification.course_code else "")
                )
                .where(NotificationDeliveryRow.delivered == 1)
                .where(NotificationDeliveryRow.created_at >= since)
            ).all()
        return len({row.dedupe_key + str(row.created_at) for row in rows})

    def record(self, notification: Notification, results: list[DeliveryResult]) -> None:
        now = self._clock.now()
        with self._session_factory() as session, session.begin():
            for result in results:
                session.add(
                    NotificationDeliveryRow(
                        kind=notification.kind.value,
                        course_code=(
                            notification.course_code.value if notification.course_code else ""
                        ),
                        channel=result.channel,
                        dedupe_key=notification.dedupe_key(),
                        delivered=int(result.delivered),
                        detail=result.detail,
                        created_at=now,
                    )
                )


class RunLock:
    def __init__(
        self, session_factory: sessionmaker, clock: Clock, stale_after_seconds: float = 120.0
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock
        self._stale_after_seconds = stale_after_seconds

    def acquire(self, run_id: str) -> None:
        now = self._clock.now()
        cutoff = now - timedelta(seconds=self._stale_after_seconds)
        with self._session_factory() as session, session.begin():
            mine = session.scalar(select(RunRow).where(RunRow.run_id == run_id))
            if mine is not None:
                mine.finished_at = None
                mine.heartbeat_at = now
                return

            active = session.scalar(
                select(RunRow)
                .where(RunRow.finished_at.is_(None))
                .where(RunRow.heartbeat_at >= cutoff)
            )
            if active is not None:
                raise RunAlreadyActive(
                    f"another autofag watch is running (pid {active.pid} on {active.hostname})"
                )
            session.add(
                RunRow(
                    run_id=run_id,
                    hostname=socket.gethostname(),
                    pid=_current_pid(),
                    started_at=now,
                    heartbeat_at=now,
                )
            )

    def active_run(self) -> RunRow | None:
        cutoff = self._clock.now() - timedelta(seconds=self._stale_after_seconds)
        with self._session_factory() as session:
            return session.scalar(
                select(RunRow)
                .where(RunRow.finished_at.is_(None))
                .where(RunRow.heartbeat_at >= cutoff)
                .order_by(RunRow.heartbeat_at.desc())
            )

    def heartbeat(self, run_id: str) -> None:
        with self._session_factory() as session, session.begin():
            row = session.scalar(select(RunRow).where(RunRow.run_id == run_id))
            if row is not None:
                row.heartbeat_at = self._clock.now()

    def release_pid(self, pid: int) -> None:
        with self._session_factory() as session, session.begin():
            row = session.scalar(
                select(RunRow).where(RunRow.pid == pid).where(RunRow.finished_at.is_(None))
            )
            if row is not None:
                row.finished_at = self._clock.now()

    def release(self, run_id: str) -> None:
        with self._session_factory() as session, session.begin():
            row = session.scalar(select(RunRow).where(RunRow.run_id == run_id))
            if row is not None:
                row.finished_at = self._clock.now()


def _current_pid() -> int:
    import os

    return os.getpid()


def _to_entry(row: WatchEntryRow) -> WatchEntry:
    return WatchEntry(
        code=CourseCode(row.course_code),
        name=row.course_name,
        auto_enroll=bool(row.auto_enroll),
        opens_at=_as_aware(row.opens_at),
        expires_at=_as_aware(row.expires_at),
        last_status=RowStatus(row.last_status) if row.last_status else None,
        last_status_text=row.last_status_text,
        last_status_change_at=_as_aware(row.last_status_change_at),
        stopped_reason=row.stopped_reason,
        dialog_choices=_decode_choices(row.dialog_choices),
    )


def _decode_choices(raw: str | None) -> dict[str, str]:
    if not raw:
        return {}
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return (
        {str(key): str(value) for key, value in decoded.items()}
        if isinstance(decoded, dict)
        else {}
    )


def _as_aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        from datetime import UTC

        return value.replace(tzinfo=UTC)
    return value
