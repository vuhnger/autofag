from __future__ import annotations

from typing import Protocol

from autofag.models import DeliveryResult, Notification


class NotificationChannel(Protocol):
    @property
    def name(self) -> str: ...

    def send(self, notification: Notification) -> DeliveryResult: ...


class CommandRunner(Protocol):
    def run(self, command: list[str], timeout: float) -> int: ...


class SmtpSender(Protocol):
    def send(
        self,
        host: str,
        port: int,
        use_starttls: bool,
        username: str,
        password: str,
        sender: str,
        recipients: tuple[str, ...],
        subject: str,
        body: str,
        timeout: float,
    ) -> None: ...
