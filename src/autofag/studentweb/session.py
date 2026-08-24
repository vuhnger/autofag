from __future__ import annotations

import threading
from dataclasses import replace
from logging import Logger

from autofag import strings_nb as nb
from autofag.clock import Clock
from autofag.config import AppConfig
from autofag.models import (
    CourseCode,
    CourseRow,
    EnrollOutcome,
    EnrollResult,
    SearchCriteria,
    SearchResult,
)
from autofag.studentweb.page import (
    ConfirmDialogUnrecognised,
    RawSearchResult,
    SearchFilters,
    StudentwebPage,
)
from autofag.studentweb.parsing import ParsedRow, parse_search_results
from autofag.studentweb.status import StatusClassifier


class StudentwebSession:
    def __init__(
        self,
        page: StudentwebPage,
        classifier: StatusClassifier,
        clock: Clock,
        logger: Logger,
        config: AppConfig,
    ) -> None:
        self._page = page
        self._classifier = classifier
        self._clock = clock
        self._logger = logger
        self._config = config
        self._lock = threading.RLock()
        self._filters = SearchFilters()

    @property
    def release(self) -> str:
        return self._filters.release

    def filters(self) -> SearchFilters:
        with self._lock:
            self._filters = self._page.open()
            return self._filters

    def keepalive(self) -> None:
        self.filters()

    def search(self, criteria: SearchCriteria) -> SearchResult:
        with self._lock:
            return self._parse(self._page.search(criteria))[0]

    def search_exact(self, code: CourseCode) -> CourseRow | None:
        return self.search(SearchCriteria(course_code=code.value)).single_row_for(code)

    def next_page(self) -> SearchResult:
        with self._lock:
            return self._parse(self._page.next_page())[0]

    def enroll(self, code: CourseCode, term: str, dry_run: bool = False) -> EnrollResult:
        with self._lock:
            return self._enroll_locked(code, term, dry_run)

    def _enroll_locked(self, code: CourseCode, term: str, dry_run: bool) -> EnrollResult:
        result, parsed_rows = self._parse(self._page.search(SearchCriteria(course_code=code.value)))

        if len(result.rows) != 1:
            return EnrollResult(
                code, EnrollOutcome.ABORTED, nb.ENROLL_NOT_ONE_ROW.format(count=len(result.rows))
            )

        parsed = parsed_rows[0]
        if parsed.row.code != code:
            return EnrollResult(
                code,
                EnrollOutcome.ABORTED,
                nb.ENROLL_WRONG_ROW.format(found=parsed.row.code, wanted=code),
            )
        if not parsed.row.is_takeable:
            return EnrollResult(
                code,
                EnrollOutcome.ABORTED,
                nb.ENROLL_NOT_TAKEABLE.format(status=parsed.row.status.value),
            )

        dialog = self._page.open_confirm_dialog(parsed.row.select_button_id or "")
        if code.value.casefold() not in dialog.casefold():
            return EnrollResult(code, EnrollOutcome.ABORTED, nb.ENROLL_DIALOG_MISMATCH)

        try:
            confirm_id = self._page.find_confirm_control()
        except ConfirmDialogUnrecognised as error:
            return EnrollResult(code, EnrollOutcome.ABORTED, str(error))

        if dry_run:
            return EnrollResult(
                code, EnrollOutcome.ABORTED, nb.ENROLL_DRY_RUN.format(control=confirm_id)
            )

        return self._classify_outcome(code, self._page.confirm_enrollment(confirm_id))

    def _classify_outcome(self, code: CourseCode, outcome_text: str) -> EnrollResult:
        haystack = " ".join(outcome_text.split()).casefold()
        vocabulary = self._config.enroll_vocabulary

        for outcome, phrases in (
            (EnrollOutcome.CONFIRMED, vocabulary.confirmed),
            (EnrollOutcome.WAITLISTED, vocabulary.waitlisted),
            (EnrollOutcome.FULL, vocabulary.full),
            (EnrollOutcome.REJECTED, vocabulary.rejected),
        ):
            for phrase in phrases:
                if phrase in haystack:
                    return EnrollResult(code, outcome, phrase)

        return EnrollResult(code, EnrollOutcome.UNVERIFIED, nb.ENROLL_UNRECOGNISED_RESPONSE)

    def _parse(self, raw: RawSearchResult) -> tuple[SearchResult, list[ParsedRow]]:
        result, parsed_rows = parse_search_results(
            raw.result_html,
            self._config.selectors,
            self._classifier,
            hit_count_html=raw.hit_count_html or None,
            page_index=raw.page_index,
        )
        declared_next = raw.extra.get("has_next")
        if declared_next is not None:
            result = replace(result, has_next_page=declared_next.lower() == "true")
        return result, parsed_rows
