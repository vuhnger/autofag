from __future__ import annotations

from logging import Logger

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

    def enroll(self, row: CourseRow, term: str) -> EnrollResult:
        code = row.code

        if not self._config.enabled:
            return EnrollResult(code, EnrollOutcome.ABORTED, "auto-påmelding er slått av")
        if self._ledger.has_record(code, self._run_id, SETTLED_STATES):
            return EnrollResult(code, EnrollOutcome.ABORTED, "allerede meldt på i denne kjøringen")
        if self._unverified_limit_reached(code):
            return EnrollResult(code, EnrollOutcome.ABORTED, "for mange ubekreftede forsøk")

        result = self._attempt_sequence(code, term)
        self._dispatcher.dispatch(self._outcome_notification(row, result))
        return result

    def _attempt_sequence(self, code: CourseCode, term: str) -> EnrollResult:
        last = EnrollResult(code, EnrollOutcome.ABORTED, "ingen forsøk ble gjort")

        for attempt in range(self._config.max_sequence_attempts):
            ledger_id = self._ledger.record_attempt(code, term, self._run_id)
            try:
                last = self._session.enroll(code, term, dry_run=self._dry_run)
            except TransportError as error:
                self._ledger.settle(ledger_id, LEDGER_UNVERIFIED, str(error))
                self._logger.warning("enroll attempt %s for %s failed: %s", attempt + 1, code, error)
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
            return EnrollResult(code, EnrollOutcome.UNVERIFIED, f"{detail}; kunne ikke verifisere: {error}")

        if row is None:
            return EnrollResult(code, EnrollOutcome.UNVERIFIED, f"{detail}; emnet ble ikke funnet")
        if row.status is RowStatus.ENROLLED or not row.is_takeable:
            return EnrollResult(code, EnrollOutcome.CONFIRMED, "verifisert etter avbrutt forsøk")
        return EnrollResult(code, EnrollOutcome.UNVERIFIED, detail)

    def _unverified_limit_reached(self, code: CourseCode) -> bool:
        unverified = self._ledger.count_state(code, self._run_id, LEDGER_UNVERIFIED)
        return unverified >= self._config.max_unverified_before_stop

    def _outcome_notification(self, row: CourseRow, result: EnrollResult) -> Notification:
        confirmed = result.outcome is EnrollOutcome.CONFIRMED
        needs_human = result.outcome in (EnrollOutcome.UNVERIFIED, EnrollOutcome.FULL)
        severity = Severity.IMPORTANT if confirmed else Severity.CRITICAL

        titles = {
            EnrollOutcome.CONFIRMED: f"Påmeldt {row.code}",
            EnrollOutcome.WAITLISTED: f"Venteliste på {row.code}",
            EnrollOutcome.FULL: f"{row.code} ble fullt før vi rakk det",
            EnrollOutcome.REJECTED: f"{row.code} avviste påmeldingen",
            EnrollOutcome.UNVERIFIED: f"{row.code}: bekreft manuelt",
            EnrollOutcome.ABORTED: f"{row.code}: påmelding avbrutt",
        }

        return Notification(
            kind=NotificationKind.NEEDS_MANUAL_CHECK if needs_human else NotificationKind.ENROLL_OUTCOME,
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
