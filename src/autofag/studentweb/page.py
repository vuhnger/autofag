from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from autofag.models import SearchCriteria


class PageUnavailable(RuntimeError):
    pass


class NotAuthenticated(PageUnavailable):
    pass


class ConfirmDialogUnrecognised(PageUnavailable):
    pass


class ProfileInUse(PageUnavailable):
    pass


@dataclass(frozen=True, slots=True)
class SelectOption:
    value: str
    label: str


@dataclass(frozen=True, slots=True)
class SearchFilters:
    subjects: tuple[SelectOption, ...] = ()
    faculties: tuple[SelectOption, ...] = ()
    release: str = "unknown"


@dataclass(frozen=True, slots=True)
class DialogControl:
    id: str
    label: str


@dataclass(frozen=True, slots=True)
class DialogState:
    html: str
    controls: tuple[DialogControl, ...] = ()
    pending_choices: tuple[str, ...] = ()

    def control_matching(self, labels: tuple[str, ...]) -> DialogControl | None:
        matches = [
            control for control in self.controls if any(word in control.label for word in labels)
        ]
        return matches[0] if len(matches) == 1 else None

    def labels(self) -> str:
        return ", ".join(control.label or control.id for control in self.controls) or "ingen"


@dataclass(frozen=True, slots=True)
class RawSearchResult:
    result_html: str
    hit_count_html: str = ""
    page_index: int = 0
    extra: dict[str, str] = field(default_factory=dict)


class StudentwebPage(Protocol):
    def log_in(self, instructions: str) -> None: ...

    def open(self) -> SearchFilters: ...

    def search(self, criteria: SearchCriteria) -> RawSearchResult: ...

    def next_page(self) -> RawSearchResult: ...

    def open_confirm_dialog(self, button_id: str) -> DialogState: ...

    def advance_dialog(self, control_id: str) -> DialogState: ...

    def read_outcome(self) -> str: ...

    def close(self) -> None: ...
