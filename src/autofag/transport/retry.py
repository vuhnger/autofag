from __future__ import annotations

from collections.abc import Iterator
from random import Random

from autofag.config import RetryConfig


class RetryPolicy:
    def __init__(self, config: RetryConfig, random: Random | None = None) -> None:
        self._config = config
        self._random = random or Random()

    @property
    def max_attempts(self) -> int:
        return self._config.max_attempts

    def backoff_delays(self) -> Iterator[float]:
        delay = self._config.initial_backoff_seconds
        for _ in range(max(0, self._config.max_attempts - 1)):
            jittered = delay * (0.5 + self._random.random())
            yield min(jittered, self._config.max_backoff_seconds)
            delay = min(delay * self._config.backoff_multiplier, self._config.max_backoff_seconds)
