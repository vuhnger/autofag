from __future__ import annotations

from pathlib import Path

import pytest

from autofag.config import SelectorConfig, StatusVocabularyConfig
from autofag.models import CourseCode, RowStatus
from autofag.studentweb.parsing import parse_partial_response, parse_search_results
from autofag.studentweb.status import StatusClassifier

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def selectors() -> SelectorConfig:
    return SelectorConfig()


@pytest.fixture
def classifier() -> StatusClassifier:
    return StatusClassifier(StatusVocabularyConfig())


@pytest.fixture
def parsed(selectors, classifier):
    html = (FIXTURES / "search_results.html").read_text(encoding="utf-8")
    hits = (FIXTURES / "hit_count.html").read_text(encoding="utf-8")
    return parse_search_results(html, selectors, classifier, hit_count_html=hits)


def test_parses_every_row(parsed):
    result, _ = parsed
    assert [row.code.value for row in result.rows] == ["IN5020", "IN5040", "IN5060", "IN5070"]


def test_reads_total_hits_not_page_size(parsed):
    result, _ = parsed
    assert result.total_hits == 59
    assert result.has_next_page is True


def test_course_name_and_credits_exclude_responsive_header_labels(parsed):
    result, _ = parsed
    row = result.single_row_for(CourseCode("IN5040"))
    assert row.name == "Advanced Database Systems for Big Data"
    assert row.credits == "10"


def test_takeable_row_is_detected(parsed):
    result, _ = parsed
    row = result.single_row_for(CourseCode("IN5040"))
    assert row.status is RowStatus.TAKEABLE
    assert row.is_takeable is True
    assert row.select_button_id == "aktiveEmnerForm:sokResultatDataTable:4:frittEmneVelgKnapp"


def test_select_button_alone_does_not_mean_takeable(parsed):
    result, _ = parsed
    row = result.single_row_for(CourseCode("IN5020"))
    assert row.select_button_id is not None
    assert row.status is RowStatus.DEADLINE_PASSED
    assert row.is_takeable is False


def test_exam_section_text_never_leaks_into_teaching_status(parsed):
    result, _ = parsed
    row = result.single_row_for(CourseCode("IN5020"))
    assert "eksamen" not in row.status_text.casefold()


def test_detail_toggle_text_is_excluded_from_teaching_status(parsed):
    result, _ = parsed
    row = result.single_row_for(CourseCode("IN5040"))
    assert row.status_text == "Du kan melde deg til undervisning."


def test_remaining_statuses(parsed):
    result, _ = parsed
    assert result.single_row_for(CourseCode("IN5060")).status is RowStatus.NOT_OPEN_YET
    assert result.single_row_for(CourseCode("IN5070")).status is RowStatus.NO_STUDY_RIGHT


def test_row_index_comes_from_the_button_id(parsed):
    _, parsed_rows = parsed
    by_code = {parsed.row.code.value: parsed.row_index for parsed in parsed_rows}
    assert by_code["IN5040"] == 4
    assert by_code["IN5060"] is None


def test_unknown_status_text_is_not_an_exception(classifier):
    assert classifier.classify("noe helt nytt fra 2027").status is RowStatus.UNKNOWN


PARTIAL = """<?xml version='1.0' encoding='UTF-8'?>
<partial-response><changes>
<update id="aktiveEmnerForm:frittSokResultat"><![CDATA[<b>hei</b>]]></update>
<update id="j_id__v_0:javax.faces.ViewState:0"><![CDATA[-1234567890123:987]]></update>
</changes></partial-response>"""


def test_view_state_is_matched_by_suffix_not_exact_id(selectors):
    response = parse_partial_response(PARTIAL, selectors)
    assert response.view_state == "-1234567890123:987"
    assert response.update_containing("frittSokResultat") == "<b>hei</b>"


def test_partial_response_without_viewstate_reports_none(selectors):
    xml = "<partial-response><changes><update id='x'><![CDATA[y]]></update></changes></partial-response>"
    assert parse_partial_response(xml, selectors).view_state is None
