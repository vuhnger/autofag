from __future__ import annotations

import threading
from collections.abc import Callable
from logging import Logger
from random import Random
from typing import TypeVar

from autofag.clock import Clock
from autofag.config import BudgetConfig
from autofag.models import SearchCriteria
from autofag.storage.repos import BudgetStore
from autofag.studentweb.page import (
    NotAuthenticated,
    PageUnavailable,
    RawSearchResult,
    SearchFilters,
    StudentwebPage,
)
from autofag.transport.errors import BudgetExhausted, RequestFailed
from autofag.transport.retry import RetryPolicy

T = TypeVar("T")


class PacedStudentwebPage:
    def __init__(
        self,
        page: StudentwebPage,
        budget_store: BudgetStore,
        retry: RetryPolicy,
        clock: Clock,
        logger: Logger,
        budget_config: BudgetConfig,
        random: Random | None = None,
    ) -> None:
        self._page = page
        self._budget_store = budget_store
        self._retry = retry
        self._clock = clock
        self._logger = logger
        self._budget_config = budget_config
        self._random = random or Random()
        self._lock = threading.Lock()
        self._next_allowed_monotonic = 0.0

    def budget_remaining(self) -> int:
        return max(0, self._budget_config.requests_per_hour - self._budget_store.used_this_hour())

    def log_in(self, instructions: str) -> None:
        self._page.log_in(instructions)

    def open(self) -> SearchFilters:
        return self._paced("open", self._page.open)

    def search(self, criteria: SearchCriteria) -> RawSearchResult:
        return self._paced("search", lambda: self._page.search(criteria))

    def next_page(self) -> RawSearchResult:
        return self._paced("next_page", self._page.next_page)

    def open_confirm_dialog(self, button_id: str) -> str:
        return self._paced("open_confirm_dialog", lambda: self._page.open_confirm_dialog(button_id))

    def find_confirm_control(self) -> str:
        return self._page.find_confirm_control()

    def confirm_enrollment(self, confirm_button_id: str) -> str:
        return self._paced(
            "confirm_enrollment", lambda: self._page.confirm_enrollment(confirm_button_id)
        )

    def close(self) -> None:
        self._page.close()

    def _paced(self, label: str, action: Callable[[], T]) -> T:
        with self._lock:
            return self._with_retries(label, action)

    def _with_retries(self, label: str, action: Callable[[], T]) -> T:
        delays = list(self._retry.backoff_delays())
        last_error: Exception | None = None

        for attempt in range(self._retry.max_attempts):
            self._wait_for_slot()
            if not self._budget_store.consume(self._budget_config.requests_per_hour):
                raise BudgetExhausted(
                    f"hourly cap of {self._budget_config.requests_per_hour} actions reached"
                )

            try:
                return action()
            except NotAuthenticated:
                raise
            except PageUnavailable as error:
                last_error = error
                self._logger.warning("%s failed (attempt %s): %s", label, attempt + 1, error)

            if attempt < len(delays):
                self._clock.sleep_until(self._clock.monotonic() + delays[attempt])

        raise RequestFailed(
            f"{label} gave up after {self._retry.max_attempts} attempts: {last_error}"
        )

    def _wait_for_slot(self) -> None:
        if self._clock.monotonic() < self._next_allowed_monotonic:
            self._clock.sleep_until(self._next_allowed_monotonic)

        spacing = self._budget_config.min_seconds_between_requests
        jitter = spacing * self._budget_config.jitter_fraction * self._random.random()
        self._next_allowed_monotonic = self._clock.monotonic() + spacing + jitter
