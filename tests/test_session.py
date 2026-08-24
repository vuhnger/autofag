from __future__ import annotations

import pytest

from autofag.models import CourseCode, EnrollOutcome, RowStatus, SearchCriteria
from autofag.studentweb.session import AuthenticationLost
from autofag.transport.errors import BudgetExhausted
from tests.conftest import build_harness


def test_search_reads_courses_and_release(harness):
    result = harness.session.search(SearchCriteria(course_code="IN5"))
    assert [row.code.value for row in result.rows] == ["IN5020", "IN5040", "IN5170"]
    assert harness.session.release == "636-2026.06.05 16:04"


def test_search_by_name_works_for_any_faculty(harness):
    result = harness.session.search(SearchCriteria(course_name="samers"))
    assert [row.code.value for row in result.rows] == ["HIS2010"]


def test_select_button_without_teaching_phrase_is_not_takeable(harness):
    row = harness.session.search_exact(CourseCode("IN5020"))
    assert row.select_button_id is not None
    assert row.is_takeable is False


def test_one_token_invariant_survives_a_view_capacity_of_two(config):
    harness = build_harness(config, view_capacity=2)
    for _ in range(25):
        result = harness.session.search(SearchCriteria(course_code="IN5"))
        assert len(result.rows) == 3


def test_expired_view_is_recovered_without_losing_the_search(config):
    harness = build_harness(config, expire_view_after=1)
    harness.session.search(SearchCriteria(course_code="IN5"))
    result = harness.session.search(SearchCriteria(course_code="IN5"))
    assert len(result.rows) == 3


def test_enroll_refuses_when_the_row_is_not_takeable(harness):
    result = harness.session.enroll(CourseCode("IN5020"), term="2026H")
    assert result.outcome is EnrollOutcome.ABORTED
    assert "not takeable" in result.detail
    assert harness.server.enrolled == []


def test_enroll_confirms_when_the_row_is_takeable(harness):
    harness.server.advance_to_takeable("IN5170")
    result = harness.session.enroll(CourseCode("IN5170"), term="2026H")
    assert result.outcome is EnrollOutcome.CONFIRMED
    assert harness.server.enrolled == ["IN5170"]


def test_enrolled_course_is_no_longer_takeable(harness):
    harness.server.advance_to_takeable("IN5170")
    harness.session.enroll(CourseCode("IN5170"), term="2026H")
    row = harness.session.search_exact(CourseCode("IN5170"))
    assert row.status is RowStatus.ENROLLED
    assert row.is_takeable is False


def test_dry_run_stops_before_the_confirm_postback(harness):
    harness.server.advance_to_takeable("IN5170")
    result = harness.session.enroll(CourseCode("IN5170"), term="2026H", dry_run=True)
    assert result.outcome is EnrollOutcome.ABORTED
    assert "dry-run" in result.detail
    assert harness.server.enrolled == []


def test_lost_login_is_reported_not_swallowed(harness):
    harness.server.logged_in = False
    with pytest.raises(AuthenticationLost):
        harness.session.search(SearchCriteria(course_code="IN5"))


def test_transient_failure_is_retried(config):
    harness = build_harness(config, fail_next_count=2)
    result = harness.session.search(SearchCriteria(course_code="IN5"))
    assert len(result.rows) == 3


def test_hourly_cap_stops_the_gate(config):
    config.budget.requests_per_hour = 3
    harness = build_harness(config)
    with pytest.raises(BudgetExhausted):
        for _ in range(10):
            harness.session.search(SearchCriteria(course_code="IN5"))
