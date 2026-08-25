from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from logging import Logger
from pathlib import Path

from autofag import strings_nb as nb
from autofag.clock import Clock
from autofag.config import AppConfig, save_config
from autofag.models import (
    CourseRow,
    Notification,
    NotificationKind,
    SearchCriteria,
    Severity,
    WatchEntry,
)
from autofag.notify.dispatcher import NotificationDispatcher
from autofag.presentation import Presenter
from autofag.prompts import Prompter
from autofag.storage.repos import WatchlistRepository
from autofag.storage.secrets import (
    SECRET_NTFY_TOPIC,
    SECRET_SMTP_PASSWORD,
    SECRET_TWILIO_ACCOUNT_SID,
    SECRET_TWILIO_AUTH_TOKEN,
    SecretStore,
)
from autofag.studentweb.page import PageUnavailable
from autofag.studentweb.session import StudentwebSession
from autofag.transport.errors import TransportError

CHANNEL_ORDER = ("ntfy", "email", "sms", "macos")
TIMESTAMP_FORMATS = ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M")


class WizardAborted(RuntimeError):
    pass


@dataclass(slots=True)
class InitOutcome:
    entries: list[WatchEntry] = field(default_factory=list)
    channels: list[str] = field(default_factory=list)
    started: bool = False


class InitWizard:
    def __init__(
        self,
        session: StudentwebSession,
        prompter: Prompter,
        presenter: Presenter,
        watchlist: WatchlistRepository,
        secrets: SecretStore,
        config: AppConfig,
        clock: Clock,
        logger: Logger,
        dispatcher_factory,
        config_path: Path | None = None,
        dry_run: bool = False,
    ) -> None:
        self._session = session
        self._prompter = prompter
        self._presenter = presenter
        self._watchlist = watchlist
        self._secrets = secrets
        self._config = config
        self._clock = clock
        self._logger = logger
        self._dispatcher_factory = dispatcher_factory
        self._config_path = config_path
        self._dry_run = dry_run

    def run(self) -> InitOutcome:
        kept = self._settle_existing_watchlist()
        selected = self._collect_courses()
        if not selected:
            raise WizardAborted(nb.SELECT_NONE_YET)

        entries = kept + [self._configure_watch(row) for row in selected]
        channels = self._configure_channels()
        if not self._review(entries, channels):
            self._presenter.info(nb.REVIEW_ABORTED)
            return InitOutcome(entries=entries, channels=channels, started=False)

        for entry in entries:
            self._watchlist.upsert(entry)
        save_config(self._config, self._config_path)

        self._presenter.info(nb.WATCH_STARTED.format(count=len(entries)))
        return InitOutcome(entries=entries, channels=channels, started=True)

    def _settle_existing_watchlist(self) -> list[WatchEntry]:
        existing = self._watchlist.all_entries()
        if not existing:
            return []

        codes = ", ".join(entry.code.value for entry in existing)
        self._presenter.info(nb.INIT_EXISTING_WATCHLIST.format(codes=codes))
        if self._prompter.confirm(nb.INIT_KEEP_EXISTING, default=False):
            return existing

        for entry in existing:
            self._watchlist.remove(entry.code)
        self._presenter.info(nb.INIT_REMOVED_EXISTING.format(codes=codes))
        return []

    def _collect_courses(self) -> list[CourseRow]:
        selected: dict[str, CourseRow] = {}

        while True:
            query = self._prompter.text(nb.SEARCH_PROMPT).strip()
            if not query:
                if selected:
                    return list(selected.values())
                self._presenter.warn(nb.SELECT_NONE_YET)
                continue

            try:
                result = self._search(query)
            except (PageUnavailable, TransportError) as error:
                self._presenter.warn(nb.SEARCH_FAILED.format(reason=error))
                continue

            if not result.rows:
                self._presenter.warn(nb.SEARCH_NO_HITS)
                continue

            self._show(result.rows, result.total_hits)
            if result.has_next_page:
                self._presenter.warn(nb.SEARCH_MORE_PAGES)

            picked = self._pick(result.rows)
            for row in picked:
                selected[row.code.value] = row

            if picked:
                self._presenter.info(
                    nb.SELECT_ADDED.format(codes=", ".join(row.code.value for row in picked))
                )
            if selected:
                self._presenter.info(nb.SELECT_SO_FAR.format(codes=", ".join(sorted(selected))))

    def _pick(self, rows) -> list[CourseRow]:
        if len(rows) == 1:
            row = rows[0]
            question = nb.SELECT_SINGLE.format(code=row.code.value, name=row.name)
            return [row] if self._prompter.confirm(question, default=True) else []

        codes = self._prompter.checkbox(
            nb.SELECT_COURSES,
            [(row.code.value, self._choice_label(row)) for row in rows],
        )
        if not codes:
            self._presenter.warn(nb.SELECT_NOTHING_PICKED)
        by_code = {row.code.value: row for row in rows}
        return [by_code[code] for code in codes if code in by_code]

    def _search(self, query: str):
        by_code = self._session.search(SearchCriteria(course_code=query))
        if by_code.rows:
            return by_code
        return self._session.search(SearchCriteria(course_name=query))

    def _show(self, rows, total_hits: int) -> None:
        self._presenter.table(
            nb.SEARCH_HITS.format(shown=len(rows), total=total_hits),
            ("Emne", "Navn", "stp.", "Status"),
            [(row.code.value, row.name, row.credits, self._status_label(row)) for row in rows],
        )

    def _status_label(self, row: CourseRow) -> str:
        return "LEDIG NÅ" if row.is_takeable else row.status_text or row.status.value

    def _choice_label(self, row: CourseRow) -> str:
        marker = "  <-- ledig nå" if row.is_takeable else ""
        return f"{row.code.value}  {row.name}{marker}"

    def _configure_watch(self, row: CourseRow) -> WatchEntry:
        answer = self._prompter.text(nb.WATCH_OPENS_AT.format(code=row.code.value)).strip()
        opens_at = _parse_timestamp(answer) if answer else None
        if answer and opens_at is None:
            self._presenter.warn(nb.WATCH_BAD_TIMESTAMP)
        return WatchEntry(
            code=row.code, name=row.name, auto_enroll=not self._dry_run, opens_at=opens_at
        )

    def _configure_channels(self) -> list[str]:
        while True:
            chosen = self._prompter.checkbox(
                nb.CHANNELS_SELECT,
                [(name, nb.CHANNEL_LABELS[name]) for name in CHANNEL_ORDER],
            )
            if not chosen:
                self._presenter.warn(nb.CHANNELS_NEED_ONE)
                continue

            working = [name for name in chosen if self._set_up_channel(name)]
            if working:
                return working

            self._presenter.warn(nb.CHANNEL_NONE_WORKING_RETRY)

    def _set_up_channel(self, name: str) -> bool:
        while True:
            self._gather_channel_config(name)
            if self._verify_channel(name):
                return True
            if not self._prompter.confirm(nb.CHANNEL_TEST_RETRY.format(channel=name), default=True):
                self._disable_channel(name)
                return False

    def _gather_channel_config(self, name: str) -> None:
        notify = self._config.notify
        if name == "ntfy":
            notify.ntfy.enabled = True
            notify.ntfy.server_url = self._prompter.text(
                nb.CHANNEL_NTFY_SERVER, default=notify.ntfy.server_url
            )
            self._secrets.set(SECRET_NTFY_TOPIC, self._prompter.secret(nb.CHANNEL_NTFY_TOPIC))
        elif name == "email":
            notify.email.enabled = True
            notify.email.host = self._prompter.text(nb.CHANNEL_EMAIL_HOST, notify.email.host)
            notify.email.port = self._ask_port(notify.email.port)
            notify.email.username = self._prompter.text(nb.CHANNEL_EMAIL_USERNAME)
            notify.email.sender = notify.email.username
            notify.email.recipients = (self._prompter.text(nb.CHANNEL_EMAIL_RECIPIENT),)
            self._secrets.set(
                SECRET_SMTP_PASSWORD, self._prompter.secret(nb.CHANNEL_EMAIL_PASSWORD)
            )
        elif name == "sms":
            notify.sms.enabled = True
            self._secrets.set(SECRET_TWILIO_ACCOUNT_SID, self._prompter.secret(nb.CHANNEL_SMS_SID))
            self._secrets.set(SECRET_TWILIO_AUTH_TOKEN, self._prompter.secret(nb.CHANNEL_SMS_TOKEN))
            notify.sms.from_number = self._prompter.text(nb.CHANNEL_SMS_FROM)
            notify.sms.to_numbers = (self._prompter.text(nb.CHANNEL_SMS_TO),)
        elif name == "macos":
            notify.macos.enabled = True

    def _ask_port(self, current: int) -> int:
        while True:
            answer = self._prompter.text(nb.CHANNEL_EMAIL_PORT, str(current)).strip()
            if not answer:
                return current
            try:
                return int(answer)
            except ValueError:
                self._presenter.warn(nb.CHANNEL_PORT_NOT_A_NUMBER.format(answer=answer))

    def _disable_channel(self, name: str) -> None:
        notify = self._config.notify
        if name == "ntfy":
            notify.ntfy.enabled = False
        elif name == "email":
            notify.email.enabled = False
        elif name == "sms":
            notify.sms.enabled = False
        elif name == "macos":
            notify.macos.enabled = False

    def _verify_channel(self, name: str) -> bool:
        self._presenter.info(nb.CHANNEL_TEST_SENDING.format(channel=name))
        dispatcher: NotificationDispatcher = self._dispatcher_factory([name])
        results = dispatcher.dispatch(
            Notification(
                kind=NotificationKind.TEST,
                severity=Severity.INFO,
                title=nb.TEST_NOTIFICATION_TITLE,
                body=nb.TEST_NOTIFICATION_BODY,
            )
        )
        failures = [result for result in results if not result.delivered]
        for failure in failures:
            self._presenter.warn(nb.CHANNEL_TEST_FAILED.format(channel=name, detail=failure.detail))
        if failures:
            return False

        if self._prompter.confirm(nb.CHANNEL_TEST_CONFIRM.format(channel=name), default=True):
            return True

        self._presenter.warn(nb.CHANNEL_DELIVERED_BUT_UNSEEN.format(channel=name))
        return self._prompter.confirm(nb.CHANNEL_USE_ANYWAY.format(channel=name), default=True)

    def _review(self, entries: list[WatchEntry], channels: list[str]) -> bool:
        self._presenter.table(
            nb.REVIEW_HEADER,
            (nb.REVIEW_COURSES, nb.REVIEW_CHANNELS, nb.REVIEW_AUTO_ENROLL),
            [
                (
                    ", ".join(entry.code.value for entry in entries),
                    ", ".join(channels),
                    nb.REVIEW_AUTO_ENROLL_DRY if self._dry_run else nb.REVIEW_AUTO_ENROLL_ON,
                )
            ],
        )
        return self._prompter.confirm(nb.REVIEW_CONFIRM, default=True)


def _parse_timestamp(value: str) -> datetime | None:
    for pattern in TIMESTAMP_FORMATS:
        try:
            naive = datetime.strptime(value, pattern)
        except ValueError:
            continue
        return naive.astimezone()
    return None
