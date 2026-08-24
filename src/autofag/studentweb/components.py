from __future__ import annotations

import re
from dataclasses import dataclass

from bs4 import BeautifulSoup, Tag

from autofag.config import SelectorConfig

PRIMEFACES_AB_PATTERN = re.compile(r"PrimeFaces\.ab\(\s*\{(?P<body>.*?)\}", re.DOTALL)
AB_FIELD_PATTERN = re.compile(r'(?P<key>[a-z]+)\s*:\s*"(?P<value>[^"]*)"')


class ComponentMapError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class AjaxBinding:
    source: str
    form: str
    process: str
    render: str


@dataclass(frozen=True, slots=True)
class SelectOption:
    value: str
    label: str


@dataclass(frozen=True, slots=True)
class ComponentMap:
    form_id: str
    course_code_input: str
    course_name_input: str
    subject_select: str
    faculty_select: str
    result_table_id: str
    search: AjaxBinding
    subjects: tuple[SelectOption, ...]
    faculties: tuple[SelectOption, ...]
    release: str

    def structural_signature(self) -> tuple[str, ...]:
        return (
            self.form_id,
            self.course_code_input,
            self.search.source,
            self.search.process,
            self.search.render,
            self.result_table_id,
        )


class ComponentMapScraper:
    def __init__(self, selectors: SelectorConfig) -> None:
        self._selectors = selectors
        self._release_pattern = re.compile(selectors.release_pattern)

    def scrape(self, html: str) -> ComponentMap:
        soup = BeautifulSoup(html, "lxml")

        course_code_input = self._require_id_suffix(soup, self._selectors.course_code_input_suffix)
        form_id = self._owning_form_id(soup, course_code_input)
        search = self._search_binding(soup)

        return ComponentMap(
            form_id=form_id,
            course_code_input=course_code_input,
            course_name_input=self._require_id_suffix(
                soup, self._selectors.course_name_input_suffix
            ),
            subject_select=self._require_id_suffix(soup, self._selectors.subject_select_suffix),
            faculty_select=self._require_id_suffix(soup, self._selectors.faculty_select_suffix),
            result_table_id=self._optional_id_suffix(soup, self._selectors.result_table_suffix)
            or form_id + self._selectors.result_table_suffix,
            search=search,
            subjects=self._options(soup, self._selectors.subject_select_suffix),
            faculties=self._options(soup, self._selectors.faculty_select_suffix),
            release=self._release(soup),
        )

    def _require_id_suffix(self, soup: BeautifulSoup, suffix: str) -> str:
        found = self._optional_id_suffix(soup, suffix)
        if found is None:
            raise ComponentMapError(f"no element with id ending in {suffix!r}")
        return found

    def _optional_id_suffix(self, soup: BeautifulSoup, suffix: str) -> str | None:
        element = soup.find(id=lambda value: bool(value) and value.endswith(suffix))
        if isinstance(element, Tag):
            element_id = element.get("id")
            if isinstance(element_id, str):
                return element_id
        return None

    def _owning_form_id(self, soup: BeautifulSoup, input_id: str) -> str:
        element = soup.find(id=input_id)
        if isinstance(element, Tag):
            for parent in element.parents:
                if isinstance(parent, Tag) and parent.name == "form":
                    form_id = parent.get("id")
                    if isinstance(form_id, str):
                        return form_id
        return input_id.rsplit(":", 1)[0]

    def _search_binding(self, soup: BeautifulSoup) -> AjaxBinding:
        for element in soup.find_all(attrs={"onclick": True}):
            onclick = element.get("onclick")
            if not isinstance(onclick, str):
                continue
            binding = parse_ajax_binding(onclick)
            if binding is None:
                continue
            if self._selectors.search_update_marker in binding.render:
                return binding
        raise ComponentMapError(
            f"no PrimeFaces.ab call rendering {self._selectors.search_update_marker!r}"
        )

    def _options(self, soup: BeautifulSoup, suffix: str) -> tuple[SelectOption, ...]:
        select = soup.find(
            lambda tag: tag.name == "select"
            and isinstance(tag.get("id"), str)
            and tag.get("id", "").endswith(suffix)
        )
        if not isinstance(select, Tag):
            return ()
        options = []
        for option in select.find_all("option"):
            value = option.get("value")
            if not isinstance(value, str) or not value:
                continue
            options.append(SelectOption(value=value, label=option.get_text(strip=True)))
        return tuple(options)

    def _release(self, soup: BeautifulSoup) -> str:
        match = self._release_pattern.search(soup.get_text(" "))
        return match.group(1).strip() if match else "unknown"


def parse_ajax_binding(onclick: str) -> AjaxBinding | None:
    match = PRIMEFACES_AB_PATTERN.search(onclick)
    if match is None:
        return None

    fields = {
        found.group("key"): found.group("value")
        for found in AB_FIELD_PATTERN.finditer(match.group("body"))
    }
    source = fields.get("s")
    form = fields.get("f")
    if not source or not form:
        return None

    return AjaxBinding(
        source=source,
        form=form,
        process=fields.get("p", source),
        render=fields.get("u", ""),
    )
