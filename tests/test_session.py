from __future__ import annotations

import pytest

from autofag.models import CourseCode, EnrollOutcome, RowStatus, SearchCriteria
from autofag.studentweb.page import NotAuthenticated
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
    result = harness.session.enroll(CourseCode("IN5020"), term="2026H")
    assert result.outcome is EnrollOutcome.ABORTED
    assert "ikke ledig" in result.detail
    assert harness.page.enrolled == []


def test_enroll_confirms_when_the_row_is_takeable(harness):
    harness.page.advance_to_takeable("IN5170")
    result = harness.session.enroll(CourseCode("IN5170"), term="2026H")
    assert result.outcome is EnrollOutcome.CONFIRMED
    assert harness.page.enrolled == ["IN5170"]


def test_enroll_re_searches_before_confirming(harness):
    harness.page.advance_to_takeable("IN5170")
    harness.session.enroll(CourseCode("IN5170"), term="2026H")
    assert harness.page.actions.count("search") >= 1
    assert harness.page.actions.index("search") < harness.page.actions.index("confirm_enrollment")


def test_enrolled_course_is_no_longer_takeable(harness):
    harness.page.advance_to_takeable("IN5170")
    harness.session.enroll(CourseCode("IN5170"), term="2026H")
    row = harness.session.search_exact(CourseCode("IN5170"))
    assert row.status is RowStatus.ENROLLED
    assert row.is_takeable is False


def test_dry_run_stops_before_confirming(harness):
    harness.page.advance_to_takeable("IN5170")
    result = harness.session.enroll(CourseCode("IN5170"), term="2026H", dry_run=True)
    assert result.outcome is EnrollOutcome.ABORTED
    assert "tørrkjøring" in result.detail
    assert harness.page.enrolled == []


def test_an_ambiguous_confirm_dialog_aborts_instead_of_guessing(harness):
    harness.page.advance_to_takeable("IN5170")
    harness.page.confirm_control_count = 2
    result = harness.session.enroll(CourseCode("IN5170"), term="2026H")
    assert result.outcome is EnrollOutcome.ABORTED
    assert harness.page.enrolled == []


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
