from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...

    def monotonic(self) -> float: ...

    def sleep_until(self, monotonic_deadline: float) -> None: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)

    def monotonic(self) -> float:
        return time.monotonic()

    def sleep_until(self, monotonic_deadline: float) -> None:
        remaining = monotonic_deadline - self.monotonic()
        while remaining > 0:
            time.sleep(min(remaining, 1.0))
            remaining = monotonic_deadline - self.monotonic()


class FakeClock:
    def __init__(self, start: datetime | None = None) -> None:
        self._now = start or datetime(2026, 8, 24, 12, 0, tzinfo=UTC)
        self._monotonic = 0.0

    def now(self) -> datetime:
        return self._now

    def monotonic(self) -> float:
        return self._monotonic

    def sleep_until(self, monotonic_deadline: float) -> None:
        self.advance(max(0.0, monotonic_deadline - self._monotonic))

    def advance(self, seconds: float) -> None:
        self._monotonic += seconds
        self._now += timedelta(seconds=seconds)
