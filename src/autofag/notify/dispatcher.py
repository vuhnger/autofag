from __future__ import annotations

from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from logging import Logger

from autofag.clock import Clock
from autofag.config import NotifyConfig
from autofag.models import DeliveryResult, Notification, NotificationKind, Severity
from autofag.notify.protocol import NotificationChannel
from autofag.storage.repos import DeliveryLog

ALWAYS_DELIVER = frozenset(
    {NotificationKind.TEST, NotificationKind.AVAILABLE, NotificationKind.ENROLL_OUTCOME}
)


class NotificationDispatcher:
    def __init__(
        self,
        channels: Sequence[NotificationChannel],
        delivery_log: DeliveryLog,
        config: NotifyConfig,
        clock: Clock,
        logger: Logger,
        fallback: NotificationChannel | None = None,
    ) -> None:
        self._channels = list(channels)
        self._delivery_log = delivery_log
        self._config = config
        self._clock = clock
        self._logger = logger
        self._fallback = fallback

    @property
    def channel_names(self) -> list[str]:
        return [channel.name for channel in self._channels]

    def dispatch(self, notification: Notification) -> list[DeliveryResult]:
        if self._should_skip(notification):
            return []
        if not self._channels:
            self._logger.error("no notification channels configured: %s", notification.title)
            return []

        results = self._fan_out(notification)
        self._delivery_log.record(notification, results)

        if not any(result.delivered for result in results):
            results.extend(self._escalate(notification))

        return results

    def _should_skip(self, notification: Notification) -> bool:
        if notification.kind in ALWAYS_DELIVER:
            return False
        return self._delivery_log.was_delivered_recently(
            notification, self._config.dedupe_window_seconds
        )

    def _fan_out(self, notification: Notification) -> list[DeliveryResult]:
        results: list[DeliveryResult] = []
        with ThreadPoolExecutor(max_workers=max(1, len(self._channels))) as pool:
            futures = {
                pool.submit(self._send_one, channel, notification): channel
                for channel in self._channels
            }
            for future, channel in futures.items():
                try:
                    results.append(future.result(timeout=self._config.channel_timeout_seconds))
                except FutureTimeout:
                    results.append(DeliveryResult(channel.name, False, "timed out"))
                except Exception as error:
                    results.append(DeliveryResult(channel.name, False, repr(error)))
        return results

    def _send_one(
        self, channel: NotificationChannel, notification: Notification
    ) -> DeliveryResult:
        try:
            return channel.send(notification)
        except Exception as error:
            self._logger.warning("channel %s raised: %s", channel.name, error)
            return DeliveryResult(channel.name, False, repr(error))

    def _escalate(self, notification: Notification) -> list[DeliveryResult]:
        self._logger.error(
            "every notification channel failed for %s: %s", notification.kind.value, notification.title
        )
        if self._fallback is None:
            return []
        return [self._send_one(self._fallback, notification)]


def available_notification(course_code: str, course_name: str) -> Notification:
    from autofag.models import CourseCode

    return Notification(
        kind=NotificationKind.AVAILABLE,
        severity=Severity.CRITICAL,
        title=f"Ledig plass: {course_code}",
        body=f"{course_code} {course_name} har ledig plass på undervisningen nå.",
        course_code=CourseCode(course_code),
        tags=("rotating_light",),
    )
