from __future__ import annotations

import threading
from collections.abc import Mapping
from dataclasses import dataclass, field
from logging import Logger
from random import Random
from typing import Protocol

import httpx

from autofag.clock import Clock
from autofag.config import BudgetConfig, StudentwebConfig
from autofag.storage.repos import BudgetStore
from autofag.transport.errors import BudgetExhausted, ForbiddenTarget, RequestFailed
from autofag.transport.retry import RetryPolicy


@dataclass(frozen=True, slots=True)
class HttpResponse:
    status_code: int
    text: str
    headers: Mapping[str, str] = field(default_factory=dict)
    url: str = ""

    @property
    def is_success(self) -> bool:
        return 200 <= self.status_code < 300


@dataclass(frozen=True, slots=True)
class GateRequest:
    method: str
    url: str
    data: Mapping[str, str] | None = None
    headers: Mapping[str, str] | None = None
    cookies: Mapping[str, str] | None = None


class HttpTransport(Protocol):
    def request(
        self,
        method: str,
        url: str,
        *,
        data: Mapping[str, str] | None,
        headers: Mapping[str, str] | None,
        cookies: Mapping[str, str] | None,
        timeout: float,
    ) -> HttpResponse: ...


class HttpxTransport:
    def __init__(self, config: StudentwebConfig) -> None:
        self._config = config
        self._client = httpx.Client(
            timeout=httpx.Timeout(
                config.request_timeout_seconds, connect=config.connect_timeout_seconds
            ),
            follow_redirects=True,
            headers={"User-Agent": config.user_agent},
        )

    def request(
        self,
        method: str,
        url: str,
        *,
        data: Mapping[str, str] | None,
        headers: Mapping[str, str] | None,
        cookies: Mapping[str, str] | None,
        timeout: float,
    ) -> HttpResponse:
        try:
            response = self._client.request(
                method,
                url,
                data=dict(data) if data else None,
                headers=dict(headers) if headers else None,
                cookies=dict(cookies) if cookies else None,
                timeout=timeout,
            )
        except httpx.TimeoutException as error:
            raise RequestFailed(f"timeout for {method} {url}: {error}") from error
        except httpx.HTTPError as error:
            raise RequestFailed(f"transport failure for {method} {url}: {error}") from error

        return HttpResponse(
            status_code=response.status_code,
            text=response.text,
            headers=dict(response.headers),
            url=str(response.url),
        )

    def close(self) -> None:
        self._client.close()


class StudentwebGate:
    def __init__(
        self,
        transport: HttpTransport,
        budget_store: BudgetStore,
        retry: RetryPolicy,
        clock: Clock,
        logger: Logger,
        config: StudentwebConfig,
        budget_config: BudgetConfig,
        random: Random | None = None,
    ) -> None:
        self._transport = transport
        self._budget_store = budget_store
        self._retry = retry
        self._clock = clock
        self._logger = logger
        self._config = config
        self._budget_config = budget_config
        self._random = random or Random()
        self._lock = threading.Lock()
        self._next_allowed_monotonic = 0.0

    def send(self, request: GateRequest) -> HttpResponse:
        self._reject_foreign_target(request.url)

        with self._lock:
            return self._send_with_retries(request)

    def budget_remaining(self) -> int:
        return max(0, self._budget_config.requests_per_hour - self._budget_store.used_this_hour())

    def _reject_foreign_target(self, url: str) -> None:
        if not url.startswith(self._config.base_url):
            raise ForbiddenTarget(f"gate only serves {self._config.base_url}, refused {url}")

    def _send_with_retries(self, request: GateRequest) -> HttpResponse:
        delays = list(self._retry.backoff_delays())
        last_error: Exception | None = None

        for attempt in range(self._retry.max_attempts):
            self._wait_for_slot()
            if not self._budget_store.consume(self._budget_config.requests_per_hour):
                raise BudgetExhausted(
                    f"hourly cap of {self._budget_config.requests_per_hour} requests reached"
                )

            try:
                response = self._transport.request(
                    request.method,
                    request.url,
                    data=request.data,
                    headers=request.headers,
                    cookies=request.cookies,
                    timeout=self._config.request_timeout_seconds,
                )
            except RequestFailed as error:
                last_error = error
                self._logger.warning("request failed (attempt %s): %s", attempt + 1, error)
            else:
                if not self._retry.is_retryable_status(response.status_code):
                    return response
                last_error = RequestFailed(
                    f"retryable status {response.status_code}", response.status_code
                )
                self._logger.warning(
                    "retryable status %s (attempt %s)", response.status_code, attempt + 1
                )

            if attempt < len(delays):
                self._clock.sleep_until(self._clock.monotonic() + delays[attempt])

        raise RequestFailed(f"giving up after {self._retry.max_attempts} attempts: {last_error}")

    def _wait_for_slot(self) -> None:
        now = self._clock.monotonic()
        if now < self._next_allowed_monotonic:
            self._clock.sleep_until(self._next_allowed_monotonic)

        spacing = self._budget_config.min_seconds_between_requests
        jitter = spacing * self._budget_config.jitter_fraction * self._random.random()
        self._next_allowed_monotonic = self._clock.monotonic() + spacing + jitter
