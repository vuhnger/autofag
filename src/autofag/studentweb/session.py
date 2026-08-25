from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import replace
from logging import Logger

from bs4 import BeautifulSoup

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
    DialogSelect,
    DialogState,
    NoFreePlace,
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

    def enroll(
        self,
        code: CourseCode,
        term: str,
        dry_run: bool = False,
        choices: dict[str, str] | None = None,
        on_spot_confirmed: Callable[[], None] | None = None,
    ) -> EnrollResult:
        with self._lock:
            return self._enroll_locked(code, term, dry_run, choices or {}, on_spot_confirmed)

    def _enroll_locked(
        self,
        code: CourseCode,
        term: str,
        dry_run: bool,
        choices: dict[str, str],
        on_spot_confirmed: Callable[[], None] | None,
    ) -> EnrollResult:
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

        try:
            state = self._page.open_confirm_dialog(parsed.row.select_button_id or "")
        except ConfirmDialogUnrecognised as error:
            return EnrollResult(code, EnrollOutcome.ABORTED, str(error))

        return self._walk_dialog(code, state, dry_run, choices, on_spot_confirmed)

    def preview_enrollment(
        self, code: CourseCode, choices: dict[str, str] | None = None
    ) -> list[DialogState]:
        with self._lock:
            row = self.search_exact(code)
            if row is None or not row.is_takeable:
                raise ConfirmDialogUnrecognised(nb.PREVIEW_NOT_TAKEABLE.format(code=code))

            state = self._page.open_confirm_dialog(row.select_button_id or "")
            steps = [state]

            for _ in range(self._config.selectors.max_dialog_steps):
                if self._pick(state, self._config.selectors.confirm_final_labels) is not None:
                    return steps
                state = self._preview_selects(code, state, choices or {})
                forward = self._pick(state, self._config.selectors.confirm_forward_labels)
                if forward is None:
                    return steps
                state = self._page.advance_dialog(forward.id)
                steps.append(state)

            return steps

    def _preview_selects(
        self, code: CourseCode, state: DialogState, choices: dict[str, str]
    ) -> DialogState:
        for select in state.unresolved_selects:
            option = self._option_for(select, choices)
            if option is None:
                raise NoFreePlace(
                    nb.PREVIEW_NO_FREE_PLACE.format(
                        code=code,
                        field=select.label or select.id,
                        options=", ".join(item.label for item in select.options) or "ingen",
                    )
                )
            state = self._page.choose(select.id, option.value)
        return state

    def _walk_dialog(
        self,
        code: CourseCode,
        state: DialogState,
        dry_run: bool,
        choices: dict[str, str],
        on_spot_confirmed: Callable[[], None] | None = None,
    ) -> EnrollResult:
        selectors = self._config.selectors
        made: list[str] = []
        announced = False

        for _ in range(selectors.max_dialog_steps):
            if code.value.casefold() not in state.html.casefold():
                return EnrollResult(
                    code,
                    EnrollOutcome.ABORTED,
                    nb.ENROLL_DIALOG_MISMATCH.format(code=code, excerpt=_excerpt(state.html)),
                )

            resolved = self._resolve_selects(code, state, choices, made)
            if isinstance(resolved, EnrollResult):
                return resolved
            state = resolved

            if not announced:
                announced = True
                if on_spot_confirmed is not None:
                    on_spot_confirmed()

            final = self._pick(state, selectors.confirm_final_labels)
            if final is not None:
                if dry_run:
                    return EnrollResult(
                        code, EnrollOutcome.ABORTED, nb.ENROLL_DRY_RUN.format(control=final.label)
                    )
                try:
                    self._page.advance_dialog(final.id)
                except ConfirmDialogUnrecognised as error:
                    return EnrollResult(code, EnrollOutcome.ABORTED, str(error))
                return self._with_choices(
                    self._classify_outcome(code, self._page.read_outcome()), made
                )

            forward = self._pick(state, selectors.confirm_forward_labels)
            if forward is None:
                return EnrollResult(
                    code,
                    EnrollOutcome.ABORTED,
                    nb.ENROLL_NO_WAY_FORWARD.format(labels=state.labels()),
                )

            if dry_run:
                return EnrollResult(
                    code, EnrollOutcome.ABORTED, nb.ENROLL_DRY_RUN.format(control=forward.label)
                )

            try:
                state = self._page.advance_dialog(forward.id)
            except ConfirmDialogUnrecognised as error:
                return EnrollResult(code, EnrollOutcome.ABORTED, str(error))

        return EnrollResult(
            code,
            EnrollOutcome.ABORTED,
            nb.ENROLL_TOO_MANY_STEPS.format(steps=selectors.max_dialog_steps),
        )

    def _resolve_selects(
        self,
        code: CourseCode,
        state: DialogState,
        choices: dict[str, str],
        made: list[str],
    ) -> DialogState | EnrollResult:
        for select in state.unresolved_selects:
            field = select.label or select.id
            option = self._option_for(select, choices)
            if option is None:
                return EnrollResult(
                    code,
                    EnrollOutcome.FULL,
                    nb.ENROLL_NO_FREE_PLACE.format(
                        field=field,
                        options=", ".join(item.label for item in select.options) or "ingen",
                    ),
                )
            try:
                state = self._page.choose(select.id, option.value)
            except ConfirmDialogUnrecognised as error:
                return EnrollResult(code, EnrollOutcome.ABORTED, str(error))
            made.append(nb.ENROLL_CHOICE_MADE.format(field=field, value=option.label))
        return state

    def _option_for(self, select: DialogSelect, choices: dict[str, str]):
        available = select.available_options(self._config.selectors.unavailable_option_labels)
        if not available:
            return None

        wanted = choices.get(select.label) or choices.get(select.id)
        if wanted:
            preferred = select.option_matching(wanted)
            if preferred in available:
                return preferred
        return available[0]

    def _with_choices(self, result: EnrollResult, made: list[str]) -> EnrollResult:
        if not made:
            return result
        return EnrollResult(result.code, result.outcome, f"{result.detail}. {' '.join(made)}")

    def _pick(self, state: DialogState, labels: tuple[str, ...]):
        negatives = self._config.selectors.confirm_negative_labels
        safe = tuple(
            control
            for control in state.controls
            if not any(word in control.label for word in negatives)
        )
        return DialogState(html=state.html, controls=safe).control_matching(labels)

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


def _excerpt(html: str, limit: int = 160) -> str:
    text = " ".join(BeautifulSoup(html, "lxml").get_text(" ").split())
    return text[:limit] or "(tom)"
