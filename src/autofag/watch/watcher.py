from __future__ import annotations

from dataclasses import dataclass
from logging import Logger

from autofag import strings_nb as nb
from autofag.clock import Clock
from autofag.config import AppConfig
from autofag.models import (
    CourseRow,
    Notification,
    NotificationKind,
    RowStatus,
    Severity,
    TempoClass,
    WatchEntry,
)
from autofag.notify.dispatcher import NotificationDispatcher, available_notification
from autofag.storage.repos import RunLock, WatchlistRepository
from autofag.studentweb.page import NotAuthenticated
from autofag.studentweb.session import StudentwebSession
from autofag.transport.errors import BudgetExhausted, TransportError
from autofag.watch.enroller import AutoEnroller
from autofag.watch.tempo import TempoDecision, decide


@dataclass(slots=True)
class ScheduledCourse:
    entry: WatchEntry
    due_at_monotonic: float
    tempo: TempoClass


class Watcher:
    def __init__(
        self,
        session: StudentwebSession,
        watchlist: WatchlistRepository,
        enroller: AutoEnroller,
        dispatcher: NotificationDispatcher,
        run_lock: RunLock,
        clock: Clock,
        logger: Logger,
        config: AppConfig,
        run_id: str,
        term: str = "",
    ) -> None:
        self._session = session
        self._watchlist = watchlist
        self._enroller = enroller
        self._dispatcher = dispatcher
        self._run_lock = run_lock
        self._clock = clock
        self._logger = logger
        self._config = config
        self._run_id = run_id
        self._term = term
        self._scheduled: dict[str, ScheduledCourse] = {}
        self._started_at = clock.now()
        self._stop_requested = False
        self._last_postback_monotonic = clock.monotonic()

    def request_stop(self) -> None:
        self._stop_requested = True

    def run(self, max_cycles: int | None = None) -> None:
        self._run_lock.acquire(self._run_id)
        try:
            self._loop(max_cycles)
        finally:
            self._run_lock.release(self._run_id)

    def _loop(self, max_cycles: int | None) -> None:
        cycles = 0
        self._seed_schedule()

        while self._scheduled and (max_cycles is None or cycles < max_cycles):
            if self._stop_requested:
                self._logger.info("stopper etter forespørsel")
                return
            cycles += 1
            self._run_lock.heartbeat(self._run_id)
            self._reconcile_schedule()

            course = self._next_due()
            if course is None:
                break

            self._clock.sleep_until(course.due_at_monotonic)
            self._run_lock.heartbeat(self._run_id)
            self._keepalive_if_idle()

            try:
                self._check(course)
            except NotAuthenticated:
                self._notify_session_expired()
                if not self._wait_for_new_login():
                    return
            except BudgetExhausted as error:
                self._notify_budget_exhausted(str(error))
                return
            except TransportError as error:
                self._logger.warning("check for %s failed: %s", course.entry.code, error)
                self._reschedule(course)

    def _seed_schedule(self) -> None:
        self._reconcile_schedule()

    def _reconcile_schedule(self) -> None:
        now_monotonic = self._clock.monotonic()
        active = {entry.code.value: entry for entry in self._watchlist.active_entries()}

        for code in list(self._scheduled):
            if code not in active:
                self._scheduled.pop(code)
                self._logger.info("slutter å overvåke %s: den er ute av watchlisten", code)

        for code, entry in active.items():
            scheduled = self._scheduled.get(code)
            if scheduled is None:
                self._scheduled[code] = ScheduledCourse(
                    entry=entry, due_at_monotonic=now_monotonic, tempo=TempoClass.WARM
                )
                self._logger.info("begynner å overvåke %s", code)
            else:
                scheduled.entry.auto_enroll = entry.auto_enroll
                scheduled.entry.opens_at = entry.opens_at
                scheduled.entry.expires_at = entry.expires_at
                scheduled.entry.dialog_choices = entry.dialog_choices

    def _next_due(self) -> ScheduledCourse | None:
        if not self._scheduled:
            return None
        return min(self._scheduled.values(), key=lambda item: item.due_at_monotonic)

    def _check(self, course: ScheduledCourse) -> None:
        entry = course.entry
        row = self._session.search_exact(entry.code)
        self._last_postback_monotonic = self._clock.monotonic()

        if row is None:
            self._logger.warning("no row returned for %s", entry.code)
            self._reschedule(course)
            return

        self._apply_observation(entry, row)

        if row.status is RowStatus.UNKNOWN:
            self._notify_vocabulary_miss(row)

        if row.is_takeable:
            self._dispatcher.dispatch(available_notification(row.code.value, row.name))
            if entry.auto_enroll:
                result = self._enroller.enroll(row, self._term, entry.dialog_choices)
                self._logger.info(
                    "enroll %s -> %s (%s)", row.code, result.outcome.value, result.detail
                )

        self._reschedule(course)

    def _apply_observation(self, entry: WatchEntry, row: CourseRow) -> None:
        changed = entry.last_status is not None and entry.last_status is not row.status
        entry.last_status = row.status
        entry.last_status_text = row.status_text
        if changed:
            entry.last_status_change_at = self._clock.now()
        self._watchlist.record_observation(entry.code, row.status, row.status_text)
        self._watchlist.upsert(entry)

    def _reschedule(self, course: ScheduledCourse) -> None:
        decision = self._decide(course)
        if decision.is_stopped or decision.interval_seconds is None:
            course.entry.stopped_reason = decision.reason
            self._watchlist.upsert(course.entry)
            self._scheduled.pop(course.entry.code.value, None)
            self._logger.info("stopped watching %s: %s", course.entry.code, decision.reason)
            return

        course.tempo = decision.tempo
        course.due_at_monotonic = self._clock.monotonic() + decision.interval_seconds

    def _decide(self, course: ScheduledCourse) -> TempoDecision:
        return decide(
            entry=course.entry,
            now=self._clock.now(),
            config=self._config.watch.tempo,
            max_duration_days=self._config.watch.max_duration_days,
            previous_tempo=course.tempo,
            watch_started_at=self._started_at,
        )

    def _keepalive_if_idle(self) -> None:
        idle_seconds = self._clock.monotonic() - self._last_postback_monotonic
        if idle_seconds < self._config.session.keepalive_after_idle_minutes * 60:
            return
        self._session.keepalive()
        self._last_postback_monotonic = self._clock.monotonic()

    def _wait_for_new_login(self) -> bool:
        for attempt in range(self._config.session.max_reprobe_attempts):
            self._clock.sleep_until(
                self._clock.monotonic() + self._config.session.reprobe_minutes * 60
            )
            try:
                self._session.keepalive()
            except NotAuthenticated:
                self._logger.info("still logged out (probe %s)", attempt + 1)
                continue
            except TransportError as error:
                self._logger.warning("probe failed: %s", error)
                continue
            self._logger.info("session is back")
            return True
        return False

    def _notify_session_expired(self) -> None:
        self._dispatcher.dispatch(
            Notification(
                kind=NotificationKind.SESSION_EXPIRED,
                severity=Severity.CRITICAL,
                title=nb.NOTIFY_SESSION_EXPIRED_TITLE,
                body=nb.NOTIFY_SESSION_EXPIRED_BODY,
            )
        )

    def _notify_budget_exhausted(self, detail: str) -> None:
        self._dispatcher.dispatch(
            Notification(
                kind=NotificationKind.BUDGET_EXHAUSTED,
                severity=Severity.CRITICAL,
                title=nb.NOTIFY_BUDGET_TITLE,
                body=nb.NOTIFY_BUDGET_BODY.format(detail=detail),
            )
        )

    def _notify_vocabulary_miss(self, row: CourseRow) -> None:
        self._dispatcher.dispatch(
            Notification(
                kind=NotificationKind.STATUS_VOCABULARY_MISS,
                severity=Severity.IMPORTANT,
                title=nb.NOTIFY_UNKNOWN_STATUS_TITLE.format(code=row.code),
                body=nb.NOTIFY_UNKNOWN_STATUS_BODY.format(text=row.status_text),
                course_code=row.code,
            )
        )
