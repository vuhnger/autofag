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


class NoFreePlace(PageUnavailable):
    pass


@dataclass(frozen=True, slots=True)
class SearchFilters:
    release: str = "unknown"


@dataclass(frozen=True, slots=True)
class DialogControl:
    id: str
    label: str


@dataclass(frozen=True, slots=True)
class DialogOption:
    value: str
    label: str
    disabled: bool = False


@dataclass(frozen=True, slots=True)
class DialogSelect:
    id: str
    label: str
    options: tuple[DialogOption, ...]
    selected: str

    @property
    def needs_a_choice(self) -> bool:
        return not self.selected

    def available_options(self, unavailable_labels: tuple[str, ...]) -> tuple[DialogOption, ...]:
        return tuple(
            option
            for option in self.options
            if not option.disabled
            and not any(word in option.label.casefold() for word in unavailable_labels)
        )

    def option_matching(self, wanted: str) -> DialogOption | None:
        needle = wanted.casefold()
        for option in self.options:
            if needle in (option.value.casefold(), option.label.casefold()):
                return option
        for option in self.options:
            if needle in option.label.casefold():
                return option
        return None


@dataclass(frozen=True, slots=True)
class DialogState:
    html: str
    controls: tuple[DialogControl, ...] = ()
    selects: tuple[DialogSelect, ...] = ()

    @property
    def unresolved_selects(self) -> tuple[DialogSelect, ...]:
        return tuple(item for item in self.selects if item.needs_a_choice)

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

    def choose(self, select_id: str, value: str) -> DialogState: ...

    def advance_dialog(self, control_id: str) -> DialogState: ...

    def read_outcome(self) -> str: ...

    def close(self) -> None: ...
