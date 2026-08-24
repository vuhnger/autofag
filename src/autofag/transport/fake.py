from __future__ import annotations

from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import dataclass, field
from html import escape

from autofag.clock import Clock
from autofag.models import RowStatus
from autofag.transport.errors import RequestFailed
from autofag.transport.gate import HttpResponse

FORM_ID = "aktiveEmnerForm"
SEARCH_BUTTON_ID = f"{FORM_ID}:j_idt465"
TABLE_ID = f"{FORM_ID}:sokResultatDataTable"
RESULT_REGION = f"{FORM_ID}:frittSokResultat"
HITS_REGION = f"{FORM_ID}:frittSokMsgTreff"
CONFIRM_FORM = "leggTilEmneForm"
CONFIRM_BUTTON_ID = f"{CONFIRM_FORM}:leggTilEmneKnapp"
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
    becomes_takeable_at: float | None = None


@dataclass
class FakeStudentwebServer:
    clock: Clock
    courses: list[FakeCourse] = field(default_factory=list)
    view_capacity: int = 15
    logged_in: bool = True
    fail_next_count: int = 0
    fail_next_status: int = 503
    expire_view_after: int | None = None
    drop_response_after_receiving: bool = False

    def __post_init__(self) -> None:
        self._views: OrderedDict[str, int] = OrderedDict()
        self._next_view_serial = 0
        self._postbacks_on_current_view = 0
        self.enrolled: list[str] = []
        self._last_page: list[FakeCourse] = []
        self.request_log: list[str] = []

    def request(
        self,
        method: str,
        url: str,
        *,
        data: Mapping[str, str] | None,
        headers: Mapping[str, str] | None,
        cookies: Mapping[str, str] | None,
        timeout: float,
    ) -> HttpResponse:
        self.request_log.append(f"{method} {url}")

        if self.fail_next_count > 0:
            self.fail_next_count -= 1
            return HttpResponse(status_code=self.fail_next_status, text="upstream unavailable")

        if not self.logged_in:
            return HttpResponse(status_code=200, text="<html>login.jsf</html>")

        if method.upper() == "GET":
            return HttpResponse(status_code=200, text=self._render_page())
        return self._handle_postback(data or {})

    def advance_to_takeable(self, code: str) -> None:
        for course in self.courses:
            if course.code == code:
                course.status = RowStatus.TAKEABLE

    def _issue_view(self) -> str:
        self._next_view_serial += 1
        token = f"-{1000000000 + self._next_view_serial}:{self._next_view_serial}"
        self._views[token] = self._next_view_serial
        self._views.move_to_end(token)
        while len(self._views) > self.view_capacity:
            self._views.popitem(last=False)
        self._postbacks_on_current_view = 0
        return token

    def _render_page(self) -> str:
        token = self._issue_view()
        return f"""<html><body>
<form id="{FORM_ID}" action="/studentweb/aktiveemner.jsf" method="post">
  <input id="{FORM_ID}:emnekode" name="{FORM_ID}:emnekode" value="" />
  <input id="{FORM_ID}:emnenavn" name="{FORM_ID}:emnenavn" value="" />
  <select id="{FORM_ID}:emnefag" name="{FORM_ID}:emnefag">
    <option value="">Velg fra lista</option>
    <option value="INF">Informatikk</option>
    <option value="HIST">Historie</option>
  </select>
  <select id="{FORM_ID}:emnefakultet" name="{FORM_ID}:emnefakultet">
    <option value="">Velg fra lista</option>
    <option value="15">Det matematisk-naturvitenskapelige fakultet</option>
    <option value="14">Det humanistiske fakultet</option>
  </select>
  <button id="{SEARCH_BUTTON_ID}" onclick='PrimeFaces.ab({{s:"{SEARCH_BUTTON_ID}",f:"{FORM_ID}",p:"{FORM_ID}:frittSokKriteria",u:"{RESULT_REGION} {HITS_REGION}"}});return false;'>Søk</button>
  <div id="{RESULT_REGION}"></div>
  <span id="{HITS_REGION}"></span>
  <table id="{TABLE_ID}"><tbody></tbody></table>
  <input type="hidden" name="javax.faces.ViewState" value="{token}" />
</form>
<footer>Studentweb {RELEASE}</footer>
</body></html>"""

    def _handle_postback(self, data: Mapping[str, str]) -> HttpResponse:
        token = data.get("javax.faces.ViewState", "")
        if token not in self._views:
            return HttpResponse(status_code=200, text=self._view_expired())

        self._views.move_to_end(token)
        self._postbacks_on_current_view += 1
        if (
            self.expire_view_after is not None
            and self._postbacks_on_current_view > self.expire_view_after
        ):
            del self._views[token]
            return HttpResponse(status_code=200, text=self._view_expired())

        source = data.get("javax.faces.source", "")
        if source == CONFIRM_BUTTON_ID:
            return self._confirm(data)
        if "frittEmneVelgKnapp" in source:
            return self._open_dialog(source)
        return self._search(data, token)

    def _search(self, data: Mapping[str, str], token: str) -> HttpResponse:
        code_query = data.get(f"{FORM_ID}:emnekode", "").strip().upper()
        name_query = data.get(f"{FORM_ID}:emnenavn", "").strip().casefold()

        matches = [
            course
            for course in self.courses
            if (not code_query or course.code.startswith(code_query))
            and (not name_query or name_query in course.name.casefold())
        ]
        first = int(data.get(f"{TABLE_ID}_first", "0") or 0)
        page = matches[first : first + PAGE_SIZE]
        self._last_page = page

        rows = "".join(self._render_row(course, index) for index, course in enumerate(page))
        has_next = first + PAGE_SIZE < len(matches)
        next_class = "ui-paginator-next" + ("" if has_next else " ui-state-disabled")
        table = (
            f'<table id="{TABLE_ID}"><tbody>{rows}</tbody></table>'
            f'<div class="ui-paginator"><span class="{next_class}">Neste</span></div>'
        )
        hits = f"Resultat - søk etter emner ({len(matches)} emner)"

        return self._partial(
            {RESULT_REGION: table, HITS_REGION: hits}, view_state=self._rotate(token)
        )

    def _render_row(self, course: FakeCourse, index: int) -> str:
        status_text = STATUS_TEXT[course.status]
        button = ""
        if course.has_select_button:
            button_id = f"{TABLE_ID}:{index}:frittEmneVelgKnapp"
            onclick = (
                f'PrimeFaces.ab({{s:"{button_id}",f:"{FORM_ID}",'
                f'p:"{button_id}",u:"{CONFIRM_FORM}"}});return false;'
            )
            button = f'<button id="{button_id}" onclick=\'{onclick}\'>Velg</button>'
        return (
            "<tr>"
            f'<td><div class="header">Emne</div>{escape(course.code)} {escape(course.name)}</td>'
            f'<td><div class="header">stp.</div>{course.credits}</td>'
            f'<td><div class="header">Informasjon</div>'
            f'<span class="block bold">Undervisning</span>'
            f"<div><span>{escape(status_text)}</span></div>"
            f'<span class="bold line-break">Eksamen</span>'
            "<div><span>Du kan melde deg til eksamen.</span></div></td>"
            f"<td>{button}</td>"
            "</tr>"
        )

    def _open_dialog(self, source: str) -> HttpResponse:
        index = int(source.split(":")[-2])
        if index >= len(self._last_page):
            return self._partial(
                {CONFIRM_FORM: "<div>ugyldig rad</div>"}, view_state=self._rotate_current()
            )
        course = self._last_page[index]
        dialog = (
            f'<div id="{CONFIRM_FORM}"><p>Meld deg til undervisning i '
            f"{escape(course.code)} {escape(course.name)}?</p>"
            f'<button id="{CONFIRM_BUTTON_ID}">Bekreft</button>'
            f'<button id="{CONFIRM_FORM}:avbrytKnapp">Avbryt</button></div>'
        )
        self._pending_confirm = course
        return self._partial({CONFIRM_FORM: dialog}, view_state=self._rotate_current())

    def _confirm(self, data: Mapping[str, str]) -> HttpResponse:
        if self.drop_response_after_receiving:
            raise RequestFailed("connection dropped after the request was received")

        course = getattr(self, "_pending_confirm", None)
        if course is None:
            return self._partial({CONFIRM_FORM: "<div>ingen dialog</div>"}, self._rotate_current())

        course.status = RowStatus.ENROLLED
        course.has_select_button = False
        self.enrolled.append(course.code)
        message = f"<div id='{CONFIRM_FORM}'>Du har plass på undervisningen i {course.code}.</div>"
        return self._partial({CONFIRM_FORM: message}, view_state=self._rotate_current())

    def _rotate(self, token: str) -> str:
        del self._views[token]
        return self._issue_view_keeping_count()

    def _rotate_current(self) -> str:
        if self._views:
            self._views.popitem(last=True)
        return self._issue_view_keeping_count()

    def _issue_view_keeping_count(self) -> str:
        postbacks = self._postbacks_on_current_view
        token = self._issue_view()
        self._postbacks_on_current_view = postbacks
        return token

    def _partial(self, updates: Mapping[str, str], view_state: str) -> HttpResponse:
        changes = "".join(
            f'<update id="{update_id}"><![CDATA[{html}]]></update>'
            for update_id, html in updates.items()
        )
        changes += (
            '<update id="j_id__v_0:javax.faces.ViewState:0">'
            f"<![CDATA[{view_state}]]></update>"
        )
        body = f"<?xml version='1.0' encoding='UTF-8'?><partial-response><changes>{changes}</changes></partial-response>"
        return HttpResponse(status_code=200, text=body)

    def _view_expired(self) -> str:
        return (
            "<?xml version='1.0' encoding='UTF-8'?><partial-response><error>"
            "<error-name>class javax.faces.application.ViewExpiredException</error-name>"
            "<error-message>View could not be restored</error-message>"
            "</error></partial-response>"
        )


def default_courses() -> list[FakeCourse]:
    return [
        FakeCourse("IN5020", "Distribuerte systemer", status=RowStatus.DEADLINE_PASSED),
        FakeCourse("IN5040", "Advanced Database Systems", status=RowStatus.NOT_OPEN_YET),
        FakeCourse("IN5170", "Models of concurrency", status=RowStatus.NOT_OPEN_YET),
        FakeCourse(
            "HIS2010", "Samers rettigheter", status=RowStatus.NO_STUDY_RIGHT,
            has_select_button=False,
        ),
    ]
