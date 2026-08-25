from __future__ import annotations

import pytest

from autofag.models import CourseCode, EnrollOutcome, RowStatus, SearchCriteria
from autofag.studentweb.page import NoFreePlace, NotAuthenticated
from autofag.transport.errors import BudgetExhausted, RequestFailed
from tests.conftest import build_harness


def test_search_reads_courses_and_release(harness):
    result = harness.session.search(SearchCriteria(course_code="IN5"))
    assert [row.code.value for row in result.rows] == ["IN5020", "IN5040", "IN5170"]
    assert harness.session.filters().release == "636-2026.06.05 16:04"


def test_search_by_name_reaches_other_faculties(harness):
    result = harness.session.search(SearchCriteria(course_name="samers"))
    assert [row.code.value for row in result.rows] == ["HIS2010"]


def test_search_can_be_filtered_by_faculty(harness):
    result = harness.session.search(SearchCriteria(faculty="14"))
    assert [row.code.value for row in result.rows] == ["HIS2010"]


def test_select_button_without_teaching_phrase_is_not_takeable(harness):
    row = harness.session.search_exact(CourseCode("IN5020"))
    assert row.select_button_id is not None
    assert row.is_takeable is False


def test_enroll_refuses_when_the_row_is_not_takeable(harness):
    result = harness.session.enroll(CourseCode("IN5020"))
    assert result.outcome is EnrollOutcome.ABORTED
    assert "ikke ledig" in result.detail
    assert harness.page.enrolled == []


def test_enroll_confirms_when_the_row_is_takeable(harness):
    harness.page.advance_to_takeable("IN5170")
    result = harness.session.enroll(CourseCode("IN5170"))
    assert result.outcome is EnrollOutcome.CONFIRMED
    assert harness.page.enrolled == ["IN5170"]


def test_enroll_re_searches_before_confirming(harness):
    harness.page.advance_to_takeable("IN5170")
    harness.session.enroll(CourseCode("IN5170"))
    assert harness.page.actions.count("search") >= 1
    assert harness.page.actions.index("search") < harness.page.actions.index("open_confirm_dialog")


def test_enrolled_course_is_no_longer_takeable(harness):
    harness.page.advance_to_takeable("IN5170")
    harness.session.enroll(CourseCode("IN5170"))
    row = harness.session.search_exact(CourseCode("IN5170"))
    assert row.status is RowStatus.ENROLLED
    assert row.is_takeable is False


def test_dry_run_stops_before_confirming(harness):
    harness.page.advance_to_takeable("IN5170")
    result = harness.session.enroll(CourseCode("IN5170"), dry_run=True)
    assert result.outcome is EnrollOutcome.ABORTED
    assert "tørrkjøring" in result.detail
    assert harness.page.enrolled == []


def test_a_dialog_with_no_safe_way_forward_aborts(harness):
    harness.page.advance_to_takeable("IN5170")
    harness.page.offer_forward = False
    result = harness.session.enroll(CourseCode("IN5170"))
    assert result.outcome is EnrollOutcome.ABORTED
    assert "ingen trygg knapp" in result.detail
    assert harness.page.enrolled == []


def test_a_single_option_dropdown_is_filled_in_automatically(harness):
    harness.page.advance_to_takeable("IN5170")
    harness.page.select_options = ("Parti 1",)
    result = harness.session.enroll(CourseCode("IN5170"))
    assert result.outcome is EnrollOutcome.CONFIRMED
    assert harness.page.enrolled == ["IN5170"]


def test_a_choice_defaults_to_the_first_option_and_says_so(harness):
    harness.page.advance_to_takeable("IN5170")
    harness.page.select_options = ("Parti 1", "Parti 2")
    result = harness.session.enroll(CourseCode("IN5170"))
    assert result.outcome is EnrollOutcome.CONFIRMED
    assert "Valgte Parti 1 for undervisningsparti" in result.detail
    assert harness.page.enrolled == ["IN5170"]


def test_a_recorded_preference_resolves_the_choice(harness):
    harness.page.advance_to_takeable("IN5170")
    harness.page.select_options = ("Parti 1", "Parti 2")
    result = harness.session.enroll(CourseCode("IN5170"), choices={"undervisningsparti": "Parti 2"})
    assert result.outcome is EnrollOutcome.CONFIRMED
    assert "Valgte Parti 2 for undervisningsparti" in result.detail
    assert harness.page.enrolled == ["IN5170"]


def test_a_multi_step_dialog_is_walked_to_the_end(harness):
    harness.page.advance_to_takeable("IN5170")
    harness.page.dialog_steps = 3
    result = harness.session.enroll(CourseCode("IN5170"))
    assert result.outcome is EnrollOutcome.CONFIRMED
    assert harness.page.actions.count("advance_dialog") == 3


def test_lost_login_is_reported_not_swallowed(config):
    harness = build_harness(config)
    harness.page.logged_in = False
    with pytest.raises((NotAuthenticated, RequestFailed)):
        harness.session.search(SearchCriteria(course_code="IN5"))


def test_transient_failure_is_retried(config):
    harness = build_harness(config, fail_next_count=2)
    result = harness.session.search(SearchCriteria(course_code="IN5"))
    assert len(result.rows) == 3


def test_hourly_cap_stops_the_paced_page(config):
    config.budget.requests_per_hour = 3
    harness = build_harness(config)
    with pytest.raises(BudgetExhausted):
        for _ in range(10):
            harness.session.search(SearchCriteria(course_code="IN5"))


def test_a_dialog_that_names_another_course_aborts_and_says_what_it_saw(harness, monkeypatch):
    harness.page.advance_to_takeable("IN5170")
    from autofag.studentweb.page import DialogControl, DialogState

    monkeypatch.setattr(
        harness.page,
        "open_confirm_dialog",
        lambda button_id: DialogState(
            html='<div id="leggTilEmneForm">Meld deg til IN9999?</div>',
            controls=(DialogControl(id="x", label="fullfør"),),
        ),
    )

    result = harness.session.enroll(CourseCode("IN5170"))

    assert result.outcome is EnrollOutcome.ABORTED
    assert "IN9999" in result.detail
    assert harness.page.enrolled == []


def test_a_dialog_that_never_appears_aborts_without_enrolling(harness, monkeypatch):
    from autofag.studentweb.page import ConfirmDialogUnrecognised

    harness.page.advance_to_takeable("IN5170")

    def never(button_id: str) -> str:
        raise ConfirmDialogUnrecognised("bekreftelsesdialogen ble aldri synlig")

    monkeypatch.setattr(harness.page, "open_confirm_dialog", never)

    result = harness.session.enroll(CourseCode("IN5170"))

    assert result.outcome is EnrollOutcome.ABORTED
    assert "aldri synlig" in result.detail
    assert harness.page.enrolled == []


def test_a_back_button_is_never_treated_as_a_way_forward(config):
    from autofag.studentweb.page import DialogControl, DialogState

    state = DialogState(
        html="IN5170",
        controls=(
            DialogControl(id="a", label="forrige"),
            DialogControl(id="b", label="ønsker ikke eksamen"),
            DialogControl(id="c", label="neste"),
        ),
    )
    harness = build_harness(config)
    forward = harness.session._pick(state, config.selectors.confirm_forward_labels)

    assert forward is not None
    assert forward.id == "c"


def test_a_step_with_only_back_and_decline_has_no_way_forward(config):
    from autofag.studentweb.page import DialogControl, DialogState

    state = DialogState(
        html="IN5170",
        controls=(
            DialogControl(id="a", label="forrige"),
            DialogControl(id="b", label="ønsker ikke undervisning"),
        ),
    )
    harness = build_harness(config)

    assert harness.session._pick(state, config.selectors.confirm_forward_labels) is None
    assert harness.session._pick(state, config.selectors.confirm_final_labels) is None


def test_a_full_dropdown_is_reported_as_full_not_as_a_free_spot(harness):
    harness.page.advance_to_takeable("IN5170")
    harness.page.full_select = True

    result = harness.session.enroll(CourseCode("IN5170"))

    assert result.outcome is EnrollOutcome.FULL
    assert "Ingen ledig plass" in result.detail
    assert harness.page.enrolled == []


def test_the_spot_callback_fires_only_when_a_place_really_exists(harness):
    harness.page.advance_to_takeable("IN5170")
    harness.page.full_select = True
    fired = []

    harness.session.enroll(CourseCode("IN5170"), on_spot_confirmed=lambda: fired.append(1))

    assert fired == []


def test_preview_reports_a_full_dropdown_instead_of_choosing_it(harness):
    harness.page.advance_to_takeable("IN5170")
    harness.page.full_select = True

    with pytest.raises(NoFreePlace) as error:
        harness.session.preview_enrollment(CourseCode("IN5170"))

    assert "Ingen ledig plass" in str(error.value)
    assert harness.page.enrolled == []


def test_preview_uses_the_saved_choice_for_the_course(harness):
    harness.page.advance_to_takeable("IN5170")
    harness.page.select_options = ("Parti 1", "Parti 2")

    harness.session.preview_enrollment(CourseCode("IN5170"), {"undervisningsparti": "Parti 2"})

    assert "Parti 2" in harness.page.chosen_values()


def test_the_one_free_option_among_several_full_ones_is_the_one_chosen(harness):
    harness.page.advance_to_takeable("IN5170")
    harness.page.select_options = (
        "Parti 1 Ingen ledig plass",
        "Parti 2 fullt",
        "Parti 3 Ingen ledige plasser",
        "Parti 4 Onsdag 10:15",
    )

    result = harness.session.enroll(CourseCode("IN5170"))

    assert result.outcome is EnrollOutcome.CONFIRMED
    assert harness.page.chosen_values() == ("Parti 4 Onsdag 10:15",)


def test_a_saved_choice_is_ignored_when_that_option_is_full(harness):
    harness.page.advance_to_takeable("IN5170")
    harness.page.select_options = ("Parti 1 fullt", "Parti 2 Onsdag 10:15")

    harness.session.enroll(CourseCode("IN5170"), choices={"undervisningsparti": "Parti 1 fullt"})

    assert harness.page.chosen_values() == ("Parti 2 Onsdag 10:15",)


def test_an_option_disabled_by_studentweb_is_never_chosen(harness):
    harness.page.advance_to_takeable("IN5170")
    harness.page.disabled_options = ("Parti 1 Onsdag 10:15",)
    harness.page.select_options = ("Parti 1 Onsdag 10:15", "Parti 2 Torsdag 12:15")

    harness.session.enroll(CourseCode("IN5170"))

    assert harness.page.chosen_values() == ("Parti 2 Torsdag 12:15",)
