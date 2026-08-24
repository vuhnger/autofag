from __future__ import annotations

import json
import smtplib
import subprocess
from email.message import EmailMessage

from autofag.config import EmailConfig, MacosConfig, NtfyConfig, SmsConfig
from autofag.models import DeliveryResult, Notification, Severity
from autofag.notify.http import OutboundHttpClient, OutboundHttpError
from autofag.notify.protocol import CommandRunner, SmtpSender
from autofag.storage.secrets import (
    SECRET_NTFY_TOKEN,
    SECRET_NTFY_TOPIC,
    SECRET_SMTP_PASSWORD,
    SECRET_TWILIO_ACCOUNT_SID,
    SECRET_TWILIO_AUTH_TOKEN,
    SecretStore,
)

NTFY_PRIORITY = {Severity.INFO: 3, Severity.IMPORTANT: 4, Severity.CRITICAL: 5}


class NtfyChannel:
    def __init__(self, http: OutboundHttpClient, config: NtfyConfig, secrets: SecretStore) -> None:
        self._http = http
        self._config = config
        self._secrets = secrets

    @property
    def name(self) -> str:
        return "ntfy"

    def send(self, notification: Notification) -> DeliveryResult:
        topic = self._secrets.get(SECRET_NTFY_TOPIC)
        if not topic:
            return DeliveryResult(self.name, False, "no ntfy topic configured")

        payload = {
            "topic": topic,
            "title": notification.title,
            "message": notification.body,
            "priority": NTFY_PRIORITY[notification.severity],
        }
        if notification.tags:
            payload["tags"] = list(notification.tags)

        headers = {"Content-Type": "application/json; charset=utf-8"}
        token = self._secrets.get(SECRET_NTFY_TOKEN)
        if token:
            headers["Authorization"] = f"Bearer {token}"

        try:
            self._http.post(
                self._config.server_url.rstrip("/"),
                content=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                headers=headers,
            )
        except OutboundHttpError as error:
            return DeliveryResult(self.name, False, str(error))
        return DeliveryResult(self.name, True)


class SmtplibSender:
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
    ) -> None:
        message = EmailMessage()
        message["From"] = sender
        message["To"] = ", ".join(recipients)
        message["Subject"] = subject
        message.set_content(body)

        with smtplib.SMTP(host, port, timeout=timeout) as server:
            if use_starttls:
                server.starttls()
            if username and password:
                server.login(username, password)
            server.send_message(message)


class SmtpEmailChannel:
    def __init__(
        self,
        sender: SmtpSender,
        config: EmailConfig,
        secrets: SecretStore,
        timeout_seconds: float = 15.0,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._sender = sender
        self._config = config
        self._secrets = secrets

    @property
    def name(self) -> str:
        return "email"

    def send(self, notification: Notification) -> DeliveryResult:
        if not self._config.recipients or not self._config.host:
            return DeliveryResult(self.name, False, "email is not configured")

        password = self._secrets.get(SECRET_SMTP_PASSWORD) or ""
        try:
            self._sender.send(
                host=self._config.host,
                port=self._config.port,
                use_starttls=self._config.use_starttls,
                username=self._config.username,
                password=password,
                sender=self._config.sender or self._config.username,
                recipients=self._config.recipients,
                subject=notification.title,
                body=notification.body,
                timeout=self._timeout_seconds,
            )
        except OSError as error:
            return DeliveryResult(self.name, False, str(error))
        except smtplib.SMTPException as error:
            return DeliveryResult(self.name, False, str(error))
        return DeliveryResult(self.name, True)


class TwilioSmsChannel:
    def __init__(self, http: OutboundHttpClient, config: SmsConfig, secrets: SecretStore) -> None:
        self._http = http
        self._config = config
        self._secrets = secrets

    @property
    def name(self) -> str:
        return "sms"

    def send(self, notification: Notification) -> DeliveryResult:
        account_sid = self._secrets.get(SECRET_TWILIO_ACCOUNT_SID)
        auth_token = self._secrets.get(SECRET_TWILIO_AUTH_TOKEN)
        if not account_sid or not auth_token:
            return DeliveryResult(self.name, False, "twilio credentials are missing")
        if not self._config.to_numbers or not self._config.from_number:
            return DeliveryResult(self.name, False, "sms numbers are not configured")

        base = self._config.api_base_url.rstrip("/")
        url = f"{base}/2010-04-01/Accounts/{account_sid}/Messages.json"
        text = f"{notification.title}\n{notification.body}"[:1500]
        failures = []

        for number in self._config.to_numbers:
            try:
                self._http.post(
                    url,
                    data={"From": self._config.from_number, "To": number, "Body": text},
                    auth=(account_sid, auth_token),
                )
            except OutboundHttpError as error:
                failures.append(f"{number}: {error}")

        if failures:
            return DeliveryResult(self.name, False, "; ".join(failures))
        return DeliveryResult(self.name, True)


class SubprocessRunner:
    def run(self, command: list[str], timeout: float) -> int:
        completed = subprocess.run(command, timeout=timeout, capture_output=True, check=False)
        return completed.returncode


class MacOsNotificationChannel:
    def __init__(self, runner: CommandRunner, config: MacosConfig) -> None:
        self._runner = runner
        self._config = config

    @property
    def name(self) -> str:
        return "macos"

    def send(self, notification: Notification) -> DeliveryResult:
        script = (
            f"display notification {_applescript_quote(notification.body)} "
            f"with title {_applescript_quote(notification.title)} "
            f"sound name {_applescript_quote(self._config.sound)}"
        )
        try:
            code = self._runner.run(["osascript", "-e", script], timeout=10.0)
        except OSError as error:
            return DeliveryResult(self.name, False, str(error))
        if code != 0:
            return DeliveryResult(self.name, False, f"osascript exited with {code}")
        return DeliveryResult(self.name, True)


class RecordingChannel:
    def __init__(self, name: str = "recording", healthy: bool = True) -> None:
        self._name = name
        self._healthy = healthy
        self.sent: list[Notification] = []

    @property
    def name(self) -> str:
        return self._name

    def send(self, notification: Notification) -> DeliveryResult:
        self.sent.append(notification)
        if not self._healthy:
            return DeliveryResult(self._name, False, "channel is unhealthy")
        return DeliveryResult(self._name, True)


def _applescript_quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
