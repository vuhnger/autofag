from __future__ import annotations

from collections.abc import Callable
from logging import Logger

from autofag import strings_nb as nb
from autofag.clock import Clock
from autofag.config import EnrollConfig
from autofag.models import (
    CourseCode,
    CourseRow,
    EnrollOutcome,
    EnrollResult,
    Notification,
    NotificationKind,
    RowStatus,
    Severity,
)
from autofag.notify.dispatcher import NotificationDispatcher
from autofag.storage.repos import (
    LEDGER_ATTEMPTED,
    LEDGER_CONFIRMED,
    LEDGER_FAILED,
    LEDGER_UNVERIFIED,
    EnrollmentLedger,
)
from autofag.studentweb.session import StudentwebSession
from autofag.transport.errors import TransportError

SETTLED_STATES = (LEDGER_CONFIRMED,)


class AutoEnroller:
    def __init__(
        self,
        session: StudentwebSession,
        ledger: EnrollmentLedger,
        dispatcher: NotificationDispatcher,
        clock: Clock,
        logger: Logger,
        config: EnrollConfig,
        run_id: str,
        dry_run: bool = False,
    ) -> None:
        self._session = session
        self._ledger = ledger
        self._dispatcher = dispatcher
        self._clock = clock
        self._logger = logger
        self._config = config
        self._run_id = run_id
        self._dry_run = dry_run
        self._spot_announced = False

    def enroll(
        self,
        row: CourseRow,
        term: str,
        choices: dict[str, str] | None = None,
        on_spot_confirmed: Callable[[], None] | None = None,
    ) -> EnrollResult:
        code = row.code
        self._spot_announced = False

        if not self._config.enabled:
            return EnrollResult(code, EnrollOutcome.ABORTED, nb.ENROLL_DISABLED)
        if self._ledger.has_record(code, self._run_id, SETTLED_STATES):
            return EnrollResult(code, EnrollOutcome.ABORTED, nb.ENROLL_ALREADY_DONE)
        if self._unverified_limit_reached(code):
            return EnrollResult(code, EnrollOutcome.ABORTED, nb.ENROLL_TOO_MANY_UNVERIFIED)

        def announce() -> None:
            self._spot_announced = True
            if on_spot_confirmed is not None:
                on_spot_confirmed()

        result = self._attempt_sequence(code, term, choices or {}, announce)
        if result.outcome is EnrollOutcome.FULL and not self._spot_announced:
            self._logger.info(
                "%s så ledig ut, men hadde ingen ledig plass: %s", code, result.detail
            )
            return result

        self._dispatcher.dispatch(self._outcome_notification(row, result))
        return result

    def _attempt_sequence(
        self,
        code: CourseCode,
        term: str,
        choices: dict[str, str],
        announce: Callable[[], None],
    ) -> EnrollResult:
        last = EnrollResult(code, EnrollOutcome.ABORTED, nb.ENROLL_NO_ATTEMPT)

        for attempt in range(self._config.max_sequence_attempts):
            ledger_id = self._ledger.record_attempt(code, term, self._run_id)
            try:
                last = self._session.enroll(
                    code,
                    term,
                    dry_run=self._dry_run,
                    choices=choices,
                    on_spot_confirmed=announce,
                )
            except TransportError as error:
                self._ledger.settle(ledger_id, LEDGER_UNVERIFIED, str(error))
                self._logger.warning(
                    "enroll attempt %s for %s failed: %s", attempt + 1, code, error
                )
                last = self._verify_after_unverified(code, str(error))
                if last.outcome is EnrollOutcome.CONFIRMED:
                    return last
                continue

            self._ledger.settle(ledger_id, _ledger_state_for(last.outcome), last.detail)
            if last.outcome is not EnrollOutcome.UNVERIFIED:
                return last

            last = self._verify_after_unverified(code, last.detail)
            if last.outcome is EnrollOutcome.CONFIRMED:
                return last

        return last

    def _verify_after_unverified(self, code: CourseCode, detail: str) -> EnrollResult:
        try:
            row = self._session.search_exact(code)
        except TransportError as error:
            return EnrollResult(
                code,
                EnrollOutcome.UNVERIFIED,
                nb.ENROLL_COULD_NOT_VERIFY.format(detail=detail, error=error),
            )

        if row is None:
            return EnrollResult(
                code, EnrollOutcome.UNVERIFIED, nb.ENROLL_COURSE_MISSING.format(detail=detail)
            )
        if row.status is RowStatus.ENROLLED:
            return EnrollResult(code, EnrollOutcome.CONFIRMED, nb.ENROLL_VERIFIED_AFTER_DROP)
        return EnrollResult(
            code,
            EnrollOutcome.UNVERIFIED,
            nb.ENROLL_STILL_UNVERIFIED.format(detail=detail, status=row.status.value),
        )

    def _unverified_limit_reached(self, code: CourseCode) -> bool:
        unverified = self._ledger.count_state(code, self._run_id, LEDGER_UNVERIFIED)
        return unverified >= self._config.max_unverified_before_stop

    def _outcome_notification(self, row: CourseRow, result: EnrollResult) -> Notification:
        confirmed = result.outcome is EnrollOutcome.CONFIRMED
        needs_human = result.outcome in (EnrollOutcome.UNVERIFIED, EnrollOutcome.FULL)
        severity = Severity.IMPORTANT if confirmed else Severity.CRITICAL

        titles = {
            EnrollOutcome.CONFIRMED: nb.ENROLL_CONFIRMED.format(code=row.code),
            EnrollOutcome.WAITLISTED: nb.ENROLL_WAITLISTED.format(code=row.code),
            EnrollOutcome.FULL: nb.ENROLL_FULL.format(code=row.code),
            EnrollOutcome.REJECTED: nb.ENROLL_REJECTED.format(code=row.code),
            EnrollOutcome.UNVERIFIED: nb.ENROLL_UNVERIFIED.format(code=row.code),
            EnrollOutcome.ABORTED: nb.ENROLL_ABORTED.format(code=row.code),
        }

        return Notification(
            kind=NotificationKind.NEEDS_MANUAL_CHECK
            if needs_human
            else NotificationKind.ENROLL_OUTCOME,
            severity=severity,
            title=titles[result.outcome],
            body=f"{row.code} {row.name}\n{result.detail}",
            course_code=row.code,
        )


def _ledger_state_for(outcome: EnrollOutcome) -> str:
    if outcome is EnrollOutcome.CONFIRMED:
        return LEDGER_CONFIRMED
    if outcome is EnrollOutcome.UNVERIFIED:
        return LEDGER_UNVERIFIED
    if outcome is EnrollOutcome.ABORTED:
        return LEDGER_ATTEMPTED
    return LEDGER_FAILED
