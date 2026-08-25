from __future__ import annotations

from dataclasses import dataclass, field
from html import escape

from autofag.models import RowStatus, SearchCriteria
from autofag.studentweb.page import (
    ConfirmDialogUnrecognised,
    DialogControl,
    DialogOption,
    DialogSelect,
    DialogState,
    NotAuthenticated,
    PageUnavailable,
    RawSearchResult,
    SearchFilters,
)

TABLE_ID = "aktiveEmnerForm:sokResultatDataTable"
FORWARD_BUTTON_ID = "leggTilEmneForm:nesteKnapp"
FINAL_BUTTON_ID = "leggTilEmneForm:fullforKnapp"
DECLINE_BUTTON_ID = "leggTilEmneForm:onskerIkkeKnapp"
RELEASE = "636-2026.06.05 16:04"
PAGE_SIZE = 20

STATUS_TEXT = {
    RowStatus.TAKEABLE: "Du kan melde deg til undervisning.",
    RowStatus.NOT_OPEN_YET: "Du kan ikke velge undervisning dette semestret nå.",
    RowStatus.DEADLINE_PASSED: "Fristen for å søke plass på undervisningen gikk ut 11.08.2026.",
    RowStatus.NO_STUDY_RIGHT: "Du har ikke studierett til emnet",
    RowStatus.PREREQUISITES_MISSING: "Emnet har krav om forkunnskaper som du mangler.",
    RowStatus.ENROLLED: "Du har plass på undervisningen.",
    RowStatus.UNKNOWN: "Et helt nytt utsagn ingen har sett før.",
}


@dataclass
class FakeCourse:
    code: str
    name: str
    credits: str = "10"
    status: RowStatus = RowStatus.NOT_OPEN_YET
    has_select_button: bool = True
    subject: str = "INF"
    faculty: str = "15"


@dataclass
class FakeStudentwebPage:
    courses: list[FakeCourse] = field(default_factory=list)
    logged_in: bool = True
    fail_next_count: int = 0
    dialog_steps: int = 2
    select_options: tuple[str, ...] = ()
    full_select: bool = False
    disabled_options: tuple[str, ...] = ()
    drop_next_confirm: bool = False
    lose_race_on_confirm: bool = False
    offer_forward: bool = True

    def __post_init__(self) -> None:
        self.enrolled: list[str] = []
        self.actions: list[str] = []
        self._last_page: list[FakeCourse] = []
        self._last_matches: list[FakeCourse] = []
        self._pending: FakeCourse | None = None
        self._page_index = 0
        self._step = 0
        self._outcome = ""
        self._chosen: dict[str, str] = {}

    def log_in(self, instructions: str) -> None:
        self.logged_in = True

    def open(self) -> SearchFilters:
        self._act("open")
        return SearchFilters(release=RELEASE)

    def search(self, criteria: SearchCriteria) -> RawSearchResult:
        self._act("search")
        code_query = criteria.course_code.strip().upper()
        name_query = criteria.course_name.strip().casefold()

        self._last_matches = [
            course
            for course in self.courses
            if (not code_query or course.code.startswith(code_query))
            and (not name_query or name_query in course.name.casefold())
            and (not criteria.subject or course.subject == criteria.subject)
            and (not criteria.faculty or course.faculty == criteria.faculty)
        ]
        self._page_index = 0
        return self._render_page()

    def next_page(self) -> RawSearchResult:
        self._act("next_page")
        self._page_index += 1
        return self._render_page()

    def open_confirm_dialog(self, button_id: str) -> DialogState:
        self._act("open_confirm_dialog")
        index = _row_index(button_id)
        if index is None or index >= len(self._last_page):
            raise ConfirmDialogUnrecognised("ugyldig rad")

        self._pending = self._last_page[index]
        self._step = 1
        return self._dialog_state()

    def choose(self, select_id: str, value: str) -> DialogState:
        self._act("choose")
        self._chosen[select_id] = value
        return self._dialog_state()

    def chosen_values(self) -> tuple[str, ...]:
        return tuple(self._chosen.values())

    def advance_dialog(self, control_id: str) -> DialogState:
        self._act("advance_dialog")
        if control_id == DECLINE_BUTTON_ID:
            raise AssertionError("autofag skal aldri klikke avslagsknappen")

        if control_id == FINAL_BUTTON_ID:
            if self.lose_race_on_confirm:
                self.lose_race_on_confirm = False
                course = self._pending
                self._pending = None
                if course is not None:
                    course.status = RowStatus.DEADLINE_PASSED
                    course.has_select_button = False
                raise PageUnavailable("forbindelsen falt, og noen andre tok plassen")

            if self.drop_next_confirm:
                self.drop_next_confirm = False
                self._settle_pending()
                raise PageUnavailable("forbindelsen falt etter at forespørselen var mottatt")
            course = self._settle_pending()
            self._outcome = (
                f"Du har plass på undervisningen i {course.code}."
                if course
                else "ingen dialog var åpen"
            )
            return DialogState(html=self._outcome)

        self._step += 1
        return self._dialog_state()

    def read_outcome(self) -> str:
        return self._outcome

    def _dialog_state(self) -> DialogState:
        course = self._pending
        if course is None:
            raise ConfirmDialogUnrecognised("ingen dialog er åpen")

        is_last = self._step >= self.dialog_steps
        controls = [DialogControl(id=DECLINE_BUTTON_ID, label="ønsker ikke undervisning")]
        if is_last:
            controls.append(DialogControl(id=FINAL_BUTTON_ID, label="fullfør"))
        elif self.offer_forward:
            controls.append(DialogControl(id=FORWARD_BUTTON_ID, label="neste"))

        selects: tuple[DialogSelect, ...] = ()
        if not is_last and self.full_select:
            select_id = f"leggTilEmneForm:parti{self._step}"
            selects = (
                DialogSelect(
                    id=select_id,
                    label="undervisningsparti",
                    options=(DialogOption(value="none", label="Ingen ledig plass"),),
                    selected=self._chosen.get(select_id, ""),
                ),
            )
        elif not is_last and self.select_options:
            select_id = f"leggTilEmneForm:parti{self._step}"
            selects = (
                DialogSelect(
                    id=select_id,
                    label="undervisningsparti",
                    options=tuple(
                        DialogOption(
                            value=label, label=label, disabled=label in self.disabled_options
                        )
                        for label in self.select_options
                    ),
                    selected=self._chosen.get(select_id, ""),
                ),
            )

        return DialogState(
            html=(
                f'<div id="leggTilEmneForm">Steg {self._step}: '
                f"{escape(course.code)} {escape(course.name)}</div>"
            ),
            controls=tuple(controls),
            selects=selects,
        )

    def close(self) -> None:
        return None

    def advance_to_takeable(self, code: str) -> None:
        for course in self.courses:
            if course.code == code:
                course.status = RowStatus.TAKEABLE
                course.has_select_button = True

    def _settle_pending(self) -> FakeCourse | None:
        course = self._pending
        self._pending = None
        if course is None:
            return None
        course.status = RowStatus.ENROLLED
        course.has_select_button = False
        self.enrolled.append(course.code)
        return course

    def _act(self, name: str) -> None:
        self.actions.append(name)
        if not self.logged_in:
            raise NotAuthenticated("Studentweb sendte oss til innloggingssiden")
        if self.fail_next_count > 0:
            self.fail_next_count -= 1
            raise PageUnavailable("midlertidig feil")

    def _render_page(self) -> RawSearchResult:
        first = self._page_index * PAGE_SIZE
        self._last_page = self._last_matches[first : first + PAGE_SIZE]
        rows = "".join(
            self._render_row(course, index) for index, course in enumerate(self._last_page)
        )
        has_next = first + PAGE_SIZE < len(self._last_matches)
        return RawSearchResult(
            result_html=f'<table id="{TABLE_ID}"><tbody>{rows}</tbody></table>',
            hit_count_html=(
                f"<span>Resultat - søk etter emner ({len(self._last_matches)} emner)</span>"
            ),
            page_index=self._page_index,
            extra={"has_next": str(has_next)},
        )

    def _render_row(self, course: FakeCourse, index: int) -> str:
        button = ""
        if course.has_select_button:
            button = f'<button id="{TABLE_ID}:{index}:frittEmneVelgKnapp">Velg</button>'
        return (
            "<tr>"
            f'<td><div class="header">Emne</div>{escape(course.code)} {escape(course.name)}</td>'
            f'<td><div class="header">stp.</div>{course.credits}</td>'
            '<td><div class="header">Informasjon</div>'
            '<span class="block bold">Undervisning</span>'
            f"<div><span>{escape(STATUS_TEXT[course.status])}</span></div>"
            '<span class="bold line-break">Eksamen</span>'
            "<div><span>Du kan melde deg til eksamen.</span></div></td>"
            f"<td>{button}</td>"
            "</tr>"
        )


def _row_index(button_id: str) -> int | None:
    parts = button_id.split(":")
    for part in reversed(parts):
        if part.isdigit():
            return int(part)
    return None


def default_courses() -> list[FakeCourse]:
    return [
        FakeCourse("IN5020", "Distribuerte systemer", status=RowStatus.DEADLINE_PASSED),
        FakeCourse("IN5040", "Advanced Database Systems", status=RowStatus.NOT_OPEN_YET),
        FakeCourse("IN5170", "Models of concurrency", status=RowStatus.NOT_OPEN_YET),
        FakeCourse(
            "HIS2010",
            "Samers rettigheter",
            status=RowStatus.NO_STUDY_RIGHT,
            has_select_button=False,
            subject="HIST",
            faculty="14",
        ),
    ]
