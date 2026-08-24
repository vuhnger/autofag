from __future__ import annotations

import threading
from collections.abc import Mapping
from logging import Logger

from bs4 import BeautifulSoup, Tag

from autofag.auth.cookies import CookieProvider
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
from autofag.studentweb.anchor import SessionUnavailable, ViewAnchor, ViewExpired
from autofag.studentweb.components import AjaxBinding, ComponentMap, ComponentMapScraper
from autofag.studentweb.faces import AJAX_HEADERS, build_ajax_body
from autofag.studentweb.parsing import (
    ParsedRow,
    PartialResponse,
    extract_view_state_from_html,
    looks_like_login_page,
    looks_like_view_expired,
    parse_partial_response,
    parse_search_results,
)
from autofag.studentweb.status import StatusClassifier
from autofag.transport.gate import GateRequest, StudentwebGate


class AuthenticationLost(RuntimeError):
    pass


class ConfirmDialogUnrecognised(RuntimeError):
    pass


class StudentwebSession:
    def __init__(
        self,
        gate: StudentwebGate,
        scraper: ComponentMapScraper,
        classifier: StatusClassifier,
        cookies: CookieProvider,
        clock: Clock,
        logger: Logger,
        config: AppConfig,
    ) -> None:
        self._gate = gate
        self._scraper = scraper
        self._classifier = classifier
        self._cookies = cookies
        self._clock = clock
        self._logger = logger
        self._config = config
        self._lock = threading.RLock()
        self._anchor: ViewAnchor | None = None
        self._last_page_index = 0

    @property
    def release(self) -> str:
        return self._anchor.components.release if self._anchor else "unknown"

    def components(self) -> ComponentMap:
        with self._lock:
            return self._ensure_anchored().components

    def search(self, criteria: SearchCriteria) -> SearchResult:
        with self._lock:
            anchor = self._ensure_anchored()
            fields = self._search_fields(anchor.components, criteria)
            response = self._postback_with_recovery(anchor.components.search, fields)
            self._last_page_index = 0
            return self._search_result_from(response, page_index=0)[0]

    def search_exact(self, code: CourseCode) -> CourseRow | None:
        result = self.search(SearchCriteria(course_code=code.value))
        return result.single_row_for(code)

    def next_page(self) -> SearchResult:
        with self._lock:
            anchor = self._ensure_anchored()
            binding = AjaxBinding(
                source=anchor.components.result_table_id,
                form=anchor.components.form_id,
                process=anchor.components.result_table_id,
                render=anchor.components.result_table_id,
            )
            fields = {
                f"{anchor.components.result_table_id}_pagination": "true",
                f"{anchor.components.result_table_id}_first": str((self._last_page_index + 1) * 20),
                f"{anchor.components.result_table_id}_rows": "20",
                f"{anchor.components.result_table_id}_encodeFeature": "true",
            }
            response = self._postback_with_recovery(binding, fields)
            self._last_page_index += 1
            return self._search_result_from(response, page_index=self._last_page_index)[0]

    def keepalive(self) -> None:
        with self._lock:
            self._ensure_anchored()

    def enroll(self, code: CourseCode, term: str, dry_run: bool = False) -> EnrollResult:
        with self._lock:
            return self._enroll_locked(code, term, dry_run)

    def _enroll_locked(self, code: CourseCode, term: str, dry_run: bool) -> EnrollResult:
        anchor = self._ensure_anchored()
        fields = self._search_fields(anchor.components, SearchCriteria(course_code=code.value))
        search_response = self._postback_with_recovery(anchor.components.search, fields)
        result, parsed_rows = self._search_result_from(search_response, page_index=0)

        if len(result.rows) != 1:
            return EnrollResult(
                code, EnrollOutcome.ABORTED, f"expected exactly one row, got {len(result.rows)}"
            )

        parsed = parsed_rows[0]
        if parsed.row.code != code:
            return EnrollResult(
                code, EnrollOutcome.ABORTED, f"row was {parsed.row.code}, expected {code}"
            )
        if not parsed.row.is_takeable:
            return EnrollResult(
                code, EnrollOutcome.ABORTED, f"row not takeable: {parsed.row.status.value}"
            )

        dialog_response = self._postback_with_recovery(
            self._select_binding(parsed), self._search_field_values(anchor.components, code)
        )
        dialog_html = dialog_response.update_containing(self._config.selectors.confirm_form_marker)
        if dialog_html is None:
            return EnrollResult(code, EnrollOutcome.ABORTED, "no confirm dialog was rendered")
        if code.value.casefold() not in dialog_html.casefold():
            return EnrollResult(
                code, EnrollOutcome.ABORTED, "confirm dialog did not name the course"
            )

        try:
            confirm = self._confirm_binding(dialog_html)
        except ConfirmDialogUnrecognised as error:
            return EnrollResult(code, EnrollOutcome.ABORTED, str(error))

        if dry_run:
            return EnrollResult(
                code,
                EnrollOutcome.ABORTED,
                f"dry-run stopped before confirming via {confirm.source}",
            )

        confirm_response = self._postback_with_recovery(confirm, {})
        return self._enroll_outcome(code, confirm_response)

    def _select_binding(self, parsed: ParsedRow) -> AjaxBinding:
        if parsed.select_binding is not None:
            return parsed.select_binding

        button_id = parsed.row.select_button_id or ""
        anchor = self._require_anchor()
        return AjaxBinding(
            source=button_id,
            form=anchor.components.form_id,
            process=button_id,
            render=self._config.selectors.confirm_form_marker,
        )

    def _confirm_binding(self, dialog_html: str) -> AjaxBinding:
        soup = BeautifulSoup(dialog_html, "lxml")
        candidates: list[AjaxBinding] = []

        for element in soup.find_all(["button", "input", "a"]):
            if not isinstance(element, Tag):
                continue
            element_id = element.get("id")
            if not isinstance(element_id, str) or not element_id:
                continue
            label = (
                element.get_text(" ", strip=True).casefold()
                or str(element.get("value") or "").casefold()
            )
            if any(word in label for word in self._config.selectors.confirm_negative_labels):
                continue
            if not any(word in label for word in self._config.selectors.confirm_positive_labels):
                continue
            candidates.append(
                AjaxBinding(
                    source=element_id,
                    form=element_id.split(":", 1)[0],
                    process=element_id,
                    render=self._config.selectors.confirm_form_marker,
                )
            )

        if len(candidates) != 1:
            raise ConfirmDialogUnrecognised(
                f"expected exactly one confirm control, found {len(candidates)}"
            )
        return candidates[0]

    def _enroll_outcome(self, code: CourseCode, response: PartialResponse) -> EnrollResult:
        text = " ".join(
            BeautifulSoup(html, "lxml").get_text(" ") for html in response.updates.values()
        )
        haystack = " ".join(text.split()).casefold()
        vocabulary = self._config.enroll_vocabulary

        for phrase in vocabulary.confirmed:
            if phrase in haystack:
                return EnrollResult(code, EnrollOutcome.CONFIRMED, phrase)
        for phrase in vocabulary.waitlisted:
            if phrase in haystack:
                return EnrollResult(code, EnrollOutcome.WAITLISTED, phrase)
        for phrase in vocabulary.full:
            if phrase in haystack:
                return EnrollResult(code, EnrollOutcome.FULL, phrase)
        for phrase in vocabulary.rejected:
            if phrase in haystack:
                return EnrollResult(code, EnrollOutcome.REJECTED, phrase)

        return EnrollResult(code, EnrollOutcome.UNVERIFIED, "confirm response was not recognised")

    def _search_fields(self, components: ComponentMap, criteria: SearchCriteria) -> dict[str, str]:
        return {
            components.course_code_input: criteria.course_code,
            components.course_name_input: criteria.course_name,
            components.subject_select: criteria.subject,
            components.faculty_select: criteria.faculty,
        }

    def _search_field_values(self, components: ComponentMap, code: CourseCode) -> dict[str, str]:
        return self._search_fields(components, SearchCriteria(course_code=code.value))

    def _search_result_from(
        self, response: PartialResponse, page_index: int
    ) -> tuple[SearchResult, list[ParsedRow]]:
        table_html = response.update_containing(self._config.selectors.search_update_marker)
        if table_html is None:
            table_html = response.update_containing(self._config.selectors.result_table_suffix)
        hit_html = response.update_containing(self._config.selectors.hit_count_marker)
        return parse_search_results(
            table_html or "",
            self._config.selectors,
            self._classifier,
            hit_count_html=hit_html,
            page_index=page_index,
        )

    def _require_anchor(self) -> ViewAnchor:
        if self._anchor is None:
            raise SessionUnavailable("session has no anchored view")
        return self._anchor

    def _ensure_anchored(self) -> ViewAnchor:
        now = self._clock.now()
        if self._anchor is None or self._anchor.is_stale(
            now,
            self._config.session.reanchor_after_postbacks,
            self._config.session.reanchor_after_minutes,
        ):
            self._reanchor()
        return self._require_anchor()

    def _reanchor(self) -> None:
        response = self._gate.send(
            GateRequest(
                method="GET",
                url=self._config.studentweb.courses_url,
                cookies=self._cookies.current(),
            )
        )
        if looks_like_login_page(response.text, self._config.selectors):
            raise AuthenticationLost("Studentweb returned the login page")

        view_state = extract_view_state_from_html(response.text, self._config.selectors)
        if view_state is None:
            raise SessionUnavailable("no ViewState on the courses page")

        components = self._scraper.scrape(response.text)
        previous = self._anchor
        self._anchor = ViewAnchor(
            view_state=view_state, components=components, anchored_at=self._clock.now()
        )
        self._last_page_index = 0

        if previous is not None and (
            previous.components.structural_signature() != components.structural_signature()
        ):
            self._logger.warning(
                "Studentweb component layout changed (release %s -> %s)",
                previous.components.release,
                components.release,
            )

    def _postback_with_recovery(
        self, binding: AjaxBinding, fields: Mapping[str, str]
    ) -> PartialResponse:
        try:
            return self._postback(binding, fields)
        except ViewExpired:
            self._logger.info("view expired, re-anchoring")
            self._reanchor()
            return self._postback(self._rebind(binding), fields)

    def _rebind(self, binding: AjaxBinding) -> AjaxBinding:
        anchor = self._require_anchor()
        if binding.source == anchor.components.search.source:
            return anchor.components.search
        return binding

    def _postback(self, binding: AjaxBinding, fields: Mapping[str, str]) -> PartialResponse:
        anchor = self._require_anchor()
        body = build_ajax_body(binding, anchor.view_state, fields)

        response = self._gate.send(
            GateRequest(
                method="POST",
                url=self._config.studentweb.courses_url,
                data=body,
                headers=dict(AJAX_HEADERS),
                cookies=self._cookies.current(),
            )
        )

        if looks_like_login_page(response.text, self._config.selectors):
            raise AuthenticationLost("Studentweb returned the login page")
        if looks_like_view_expired(response.text, self._config.selectors):
            raise ViewExpired("server reported an expired view")

        parsed = parse_partial_response(response.text, self._config.selectors)
        if parsed.error_name and looks_like_view_expired(parsed.error_name, self._config.selectors):
            raise ViewExpired(parsed.error_name)
        if parsed.redirect:
            raise ViewExpired(f"server redirected to {parsed.redirect}")

        self._anchor = anchor.with_view_state(parsed.view_state)
        return parsed
