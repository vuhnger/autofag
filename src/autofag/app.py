from __future__ import annotations

import uuid
from dataclasses import dataclass
from logging import Logger
from random import Random

from autofag.clock import Clock, SystemClock
from autofag.config import AppConfig
from autofag.logging_setup import configure_logging
from autofag.notify.channels import (
    MacOsNotificationChannel,
    NtfyChannel,
    SmtpEmailChannel,
    SmtplibSender,
    SubprocessRunner,
    TwilioSmsChannel,
)
from autofag.notify.dispatcher import NotificationDispatcher
from autofag.notify.http import OutboundHttpClient
from autofag.notify.protocol import NotificationChannel
from autofag.presentation import Presenter, RichPresenter
from autofag.storage.db import create_database
from autofag.storage.repos import (
    BudgetStore,
    DeliveryLog,
    EnrollmentLedger,
    RunLock,
    WatchlistRepository,
)
from autofag.storage.secrets import KeyringSecretStore, SecretStore
from autofag.studentweb.page import StudentwebPage
from autofag.studentweb.session import StudentwebSession
from autofag.studentweb.status import StatusClassifier
from autofag.transport.pace import PacedStudentwebPage
from autofag.transport.retry import RetryPolicy


@dataclass(slots=True)
class Services:
    config: AppConfig
    clock: Clock
    logger: Logger
    secrets: SecretStore
    page: StudentwebPage
    session: StudentwebSession
    watchlist: WatchlistRepository
    ledger: EnrollmentLedger
    delivery_log: DeliveryLog
    run_lock: RunLock
    presenter: Presenter
    run_id: str

    def dispatcher(self, channel_names: list[str] | None = None) -> NotificationDispatcher:
        return NotificationDispatcher(
            channels=build_channels(self.config, self.secrets, channel_names),
            delivery_log=self.delivery_log,
            config=self.config.notify,
            clock=self.clock,
            logger=self.logger,
            fallback=_macos_fallback(self.config),
        )


def build_services(config: AppConfig, verbose: bool = False) -> Services:
    clock = SystemClock()
    secrets = KeyringSecretStore(config.secret_service_name)
    logger = configure_logging(secrets, verbose)
    presenter = RichPresenter()

    _, session_factory = create_database(config.storage)
    page = PacedStudentwebPage(
        page=_build_page(config, logger, presenter),
        budget_store=BudgetStore(session_factory, clock),
        retry=RetryPolicy(config.retry, Random()),
        clock=clock,
        logger=logger,
        budget_config=config.budget,
        random=Random(),
    )
    session = StudentwebSession(
        page=page,
        classifier=StatusClassifier(config.status_vocabulary),
        clock=clock,
        logger=logger,
        config=config,
    )

    return Services(
        config=config,
        clock=clock,
        logger=logger,
        secrets=secrets,
        page=page,
        session=session,
        watchlist=WatchlistRepository(session_factory, clock),
        ledger=EnrollmentLedger(session_factory, clock),
        delivery_log=DeliveryLog(session_factory, clock),
        run_lock=RunLock(session_factory, clock),
        presenter=presenter,
        run_id=uuid.uuid4().hex,
    )


def _build_page(config: AppConfig, logger: Logger, presenter: Presenter) -> StudentwebPage:
    if config.studentweb.transport == "fake":
        from autofag.studentweb.fake_page import FakeStudentwebPage, default_courses

        return FakeStudentwebPage(courses=default_courses())

    from autofag.auth.browser import PlaywrightStudentwebPage

    return PlaywrightStudentwebPage(config, logger, presenter)


def build_channels(
    config: AppConfig, secrets: SecretStore, only: list[str] | None = None
) -> list[NotificationChannel]:
    http = OutboundHttpClient(config.studentweb, config.notify.channel_timeout_seconds)
    candidates: dict[str, NotificationChannel] = {
        "ntfy": NtfyChannel(http, config.notify.ntfy, secrets),
        "email": SmtpEmailChannel(SmtplibSender(), config.notify.email, secrets),
        "sms": TwilioSmsChannel(http, config.notify.sms, secrets),
        "macos": MacOsNotificationChannel(SubprocessRunner(), config.notify.macos),
    }
    enabled = {
        "ntfy": config.notify.ntfy.enabled,
        "email": config.notify.email.enabled,
        "sms": config.notify.sms.enabled,
        "macos": config.notify.macos.enabled,
    }
    wanted = only if only is not None else [name for name, on in enabled.items() if on]
    return [candidates[name] for name in wanted if name in candidates]


def _macos_fallback(config: AppConfig) -> NotificationChannel | None:
    if config.notify.macos.enabled:
        return None
    return MacOsNotificationChannel(SubprocessRunner(), config.notify.macos)
