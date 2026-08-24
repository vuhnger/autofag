from __future__ import annotations

import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup, Tag
from lxml import etree  # ty: ignore[unresolved-import]

from autofag.config import SelectorConfig
from autofag.models import CourseCode, CourseRow, InvalidCourseCode, RowStatus, SearchResult
from autofag.studentweb.status import Classification, StatusClassifier

HIT_COUNT_PATTERN = re.compile(r"\((\d+)\s")
ROW_INDEX_PATTERN = re.compile(r":(\d+):")


class PartialResponseError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class PartialResponse:
    updates: dict[str, str] = field(default_factory=dict)
    view_state: str | None = None
    redirect: str | None = None
    error_name: str | None = None
    error_message: str | None = None

    def update_containing(self, marker: str) -> str | None:
        for update_id, html in self.updates.items():
            if marker in update_id:
                return html
        return None


def parse_partial_response(xml_text: str, selectors: SelectorConfig) -> PartialResponse:
    try:
        root = etree.fromstring(xml_text.encode("utf-8"))
    except etree.XMLSyntaxError as error:
        raise PartialResponseError(f"not a partial-response document: {error}") from error

    updates: dict[str, str] = {}
    view_state: str | None = None

    for update in root.iter("update"):
        update_id = update.get("id") or ""
        content = update.text or ""
        if selectors.view_state_marker in update_id:
            view_state = content.strip()
            continue
        updates[update_id] = content

    redirect_element = root.find(".//redirect")
    redirect = redirect_element.get("url") if redirect_element is not None else None

    error_element = root.find(".//error")
    error_name = None
    error_message = None
    if error_element is not None:
        name_element = error_element.find("error-name")
        message_element = error_element.find("error-message")
        error_name = (name_element.text or "").strip() if name_element is not None else None
        error_message = (
            (message_element.text or "").strip() if message_element is not None else None
        )

    return PartialResponse(
        updates=updates,
        view_state=view_state,
        redirect=redirect,
        error_name=error_name,
        error_message=error_message,
    )


def extract_view_state_from_html(html: str, selectors: SelectorConfig) -> str | None:
    soup = BeautifulSoup(html, "lxml")
    field = soup.find("input", attrs={"name": selectors.view_state_marker})
    if isinstance(field, Tag):
        value = field.get("value")
        if isinstance(value, str) and value:
            return value
    return None


@dataclass(frozen=True, slots=True)
class ParsedRow:
    row: CourseRow
    classification: Classification
    row_index: int | None


def parse_search_results(
    html: str,
    selectors: SelectorConfig,
    classifier: StatusClassifier,
    hit_count_html: str | None = None,
    page_index: int = 0,
) -> tuple[SearchResult, list[ParsedRow]]:
    soup = BeautifulSoup(html, "lxml")
    table = soup.find(
        id=lambda value: bool(value) and value.endswith(selectors.result_table_suffix)
    )
    parsed_rows: list[ParsedRow] = []

    if isinstance(table, Tag):
        body = table.find("tbody") or table
        for row_element in body.find_all("tr", recursive=True):
            parsed = _parse_row(row_element, selectors, classifier)
            if parsed is not None:
                parsed_rows.append(parsed)

    total_hits = _parse_hit_count(hit_count_html) if hit_count_html else len(parsed_rows)
    result = SearchResult(
        rows=tuple(parsed.row for parsed in parsed_rows),
        total_hits=total_hits,
        page_index=page_index,
        has_next_page=_has_next_page(soup, selectors),
    )
    return result, parsed_rows


def _parse_row(
    row_element: Tag, selectors: SelectorConfig, classifier: StatusClassifier
) -> ParsedRow | None:
    cells = row_element.find_all("td", recursive=False)
    if len(cells) < 3:
        return None

    code_and_name = _cell_text(cells[0], selectors)
    if not code_and_name:
        return None

    code_text, _, name = code_and_name.partition(" ")
    try:
        code = CourseCode(code_text)
    except InvalidCourseCode:
        return None

    teaching_text = _teaching_section_text(cells[2], selectors)
    classification = classifier.classify(teaching_text)
    button_id, row_index = _select_button(row_element, selectors)

    row = CourseRow(
        code=code,
        name=name.strip(),
        credits=_cell_text(cells[1], selectors),
        status=classification.status,
        status_text=teaching_text,
        select_button_id=button_id,
    )
    return ParsedRow(row=row, classification=classification, row_index=row_index)


def _teaching_section_text(cell: Tag, selectors: SelectorConfig) -> str:
    fragments: list[str] = []
    inside_teaching = False

    for node in cell.descendants:
        if isinstance(node, Tag):
            if _is_header_label(node, selectors) or _is_inside_detail_toggle(node, selectors):
                continue
            label = _bold_label(node)
            if label in selectors.teaching_section_labels:
                inside_teaching = True
                continue
            if label in selectors.exam_section_labels:
                inside_teaching = False
            continue

        if not inside_teaching:
            continue
        parent = node.parent
        if isinstance(parent, Tag) and (
            parent.name in {"script", "style", "button"}
            or _bold_label(parent)
            or _is_header_label(parent, selectors)
            or _is_inside_detail_toggle(parent, selectors)
        ):
            continue
        text = str(node).strip()
        if text:
            fragments.append(text)

    return " ".join(" ".join(fragments).split())


def _bold_label(node: Tag) -> str:
    classes = _class_list(node)
    if node.name != "span" or "bold" not in classes:
        return ""
    return node.get_text(strip=True)


def _is_header_label(node: Tag, selectors: SelectorConfig) -> bool:
    return selectors.header_label_class in _class_list(node)


def _is_inside_detail_toggle(node: Tag, selectors: SelectorConfig) -> bool:
    for parent in node.parents:
        if isinstance(parent, Tag) and selectors.detail_toggle_class in _class_list(parent):
            return True
    return selectors.detail_toggle_class in _class_list(node)


def _select_button(row_element: Tag, selectors: SelectorConfig) -> tuple[str | None, int | None]:
    button = row_element.find(lambda tag: selectors.select_button_marker in _element_id(tag))
    if not isinstance(button, Tag):
        return None, None

    button_id = button.get("id")
    if not isinstance(button_id, str):
        return None, None

    match = ROW_INDEX_PATTERN.search(button_id)
    return button_id, int(match.group(1)) if match else None


def _cell_text(cell: Tag, selectors: SelectorConfig) -> str:
    clone = BeautifulSoup(str(cell), "lxml")
    for header in clone.find_all(class_=selectors.header_label_class):
        header.decompose()
    for script in clone.find_all(["script", "style"]):
        script.decompose()
    return " ".join(clone.get_text(" ").split())


def _parse_hit_count(hit_count_html: str) -> int:
    text = BeautifulSoup(hit_count_html, "lxml").get_text(" ")
    match = HIT_COUNT_PATTERN.search(text)
    return int(match.group(1)) if match else 0


def _has_next_page(soup: BeautifulSoup, selectors: SelectorConfig) -> bool:
    for element in soup.find_all(class_=selectors.paginator_next_class):
        if isinstance(element, Tag) and "ui-state-disabled" not in _class_list(element):
            return True
    return False


def _class_list(node: Tag) -> list[str]:
    value = node.get("class")
    if value is None:
        return []
    if isinstance(value, str):
        return value.split()
    return [str(item) for item in value]


def _element_id(node: Tag) -> str:
    value = node.get("id")
    return value if isinstance(value, str) else ""


def looks_like_login_page(html: str, selectors: SelectorConfig) -> bool:
    return any(marker in html for marker in selectors.login_markers)


def looks_like_view_expired(text: str, selectors: SelectorConfig) -> bool:
    return any(marker in text for marker in selectors.view_expired_markers)


def parse_status_only(text: str, classifier: StatusClassifier) -> RowStatus:
    return classifier.classify(text).status
