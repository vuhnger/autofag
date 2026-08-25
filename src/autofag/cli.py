from __future__ import annotations

import signal
import socket
from pathlib import Path
from typing import Annotated

import typer

from autofag import __version__
from autofag import strings_nb as nb
from autofag.app import Services, build_services
from autofag.config import load_config
from autofag.daemon import (
    DaemonError,
    running_watch,
    start_detached,
    stop_process,
)
from autofag.errors import guarded
from autofag.init_flow import InitWizard, WizardAborted
from autofag.models import CourseCode, SearchCriteria
from autofag.presentation import RichPresenter
from autofag.prompts import PromptAborted, QuestionaryPrompter
from autofag.storage.repos import RunAlreadyActive
from autofag.studentweb.page import (
    ConfirmDialogUnrecognised,
    NotAuthenticated,
    PageUnavailable,
)
from autofag.transport.errors import TransportError
from autofag.watch.enroller import AutoEnroller
from autofag.watch.watcher import Watcher

app = typer.Typer(add_completion=False, help="Overvåker emner på UiO Studentweb.")

ConfigOption = Annotated[Path | None, typer.Option("--config", help="Sti til config.yaml")]
DryRunOption = Annotated[
    bool, typer.Option("--dry-run", help="Stopp før bekreftelsen, meld aldri på")
]
VerboseOption = Annotated[bool, typer.Option("--verbose", help="Mer logging")]
DetachOption = Annotated[
    bool,
    typer.Option("--detach", "-d", help="Kjør i bakgrunnen og gi terminalen tilbake"),
]


@app.command()
@guarded
def init(
    config_path: ConfigOption = None,
    dry_run: DryRunOption = False,
    detach: DetachOption = False,
    verbose: VerboseOption = False,
) -> None:
    services = build_services(load_config(config_path), verbose)
    _authenticate(services)

    prompter = QuestionaryPrompter()
    wizard = InitWizard(
        session=services.session,
        prompter=prompter,
        presenter=services.presenter,
        watchlist=services.watchlist,
        secrets=services.secrets,
        config=services.config,
        clock=services.clock,
        logger=services.logger,
        dispatcher_factory=services.dispatcher,
        dry_run=dry_run,
    )

    try:
        outcome = wizard.run()
    except (WizardAborted, PromptAborted) as error:
        services.presenter.warn(str(error))
        raise typer.Exit(code=1) from error
    finally:
        prompter.close()

    if not outcome.started:
        return

    if detach:
        _detach(services, config_path, dry_run, verbose)
        return

    _run_watcher(services, dry_run)


@app.command()
@guarded
def watch(
    config_path: ConfigOption = None,
    dry_run: DryRunOption = False,
    detach: DetachOption = False,
    verbose: VerboseOption = False,
) -> None:
    config = load_config(config_path)
    services = build_services(config, verbose)
    if not services.watchlist.active_entries():
        services.presenter.warn(nb.WATCH_NOTHING_TO_DO)
        raise typer.Exit(code=1)

    if detach:
        _detach(services, config_path, dry_run, verbose)
        return

    _authenticate(services)
    _run_watcher(services, dry_run)


@app.command()
@guarded
def stop(config_path: ConfigOption = None) -> None:
    services = build_services(load_config(config_path))
    active = running_watch(services.run_lock)

    if active is None:
        services.presenter.warn(nb.STOP_NOT_RUNNING)
        raise typer.Exit(code=1)
    if active.hostname != socket.gethostname():
        services.presenter.warn(nb.STOP_OTHER_HOST.format(host=active.hostname))
        raise typer.Exit(code=1)

    services.presenter.info(nb.STOP_SENT.format(pid=active.pid))
    try:
        stopped = stop_process(active.pid, services.clock)
    except DaemonError as error:
        services.presenter.warn(str(error))
        raise typer.Exit(code=1) from error

    if not stopped:
        services.presenter.warn(nb.STOP_STILL_RUNNING.format(pid=active.pid, seconds=30))
        raise typer.Exit(code=1)

    services.run_lock.release_pid(active.pid)
    services.presenter.info(nb.STOP_STOPPED)


@app.command()
@guarded
def status(config_path: ConfigOption = None) -> None:
    services = build_services(load_config(config_path))
    entries = services.watchlist.all_entries()
    if not entries:
        services.presenter.warn(nb.STATUS_EMPTY)
        raise typer.Exit(code=1)

    services.presenter.table(
        "Watchlist",
        ("Emne", "Navn", "Status", "Auto", "Stoppet"),
        [
            (
                entry.code.value,
                entry.name,
                entry.last_status.value if entry.last_status else "-",
                "ja" if entry.auto_enroll else "nei",
                entry.stopped_reason or "-",
            )
            for entry in entries
        ],
    )


@app.command()
@guarded
def doctor(
    config_path: ConfigOption = None,
    course: Annotated[str, typer.Option(help="Emnekode å teste mot")] = "IN5",
) -> None:
    services = build_services(load_config(config_path))
    _authenticate(services)

    try:
        filters = services.session.filters()
        result = services.session.search(SearchCriteria(course_code=course))
    except (PageUnavailable, TransportError) as error:
        services.presenter.warn(str(error))
        raise typer.Exit(code=2) from error

    recognised = [row for row in result.rows if row.status.value != "unknown"]
    if not recognised:
        services.presenter.warn(nb.DOCTOR_NO_ROWS)
        raise typer.Exit(code=2)

    services.presenter.info(nb.DOCTOR_OK.format(release=filters.release, rows=len(recognised)))
    services.presenter.info(
        nb.DOCTOR_CHANNELS.format(channels=", ".join(services.dispatcher().channel_names) or "-")
    )


@app.command()
@guarded
def preview(
    course: Annotated[str, typer.Argument(help="Emnekode å åpne dialogen for")],
    config_path: ConfigOption = None,
) -> None:
    services = build_services(load_config(config_path))
    _authenticate(services)

    code = CourseCode(course)
    entry = next((item for item in services.watchlist.all_entries() if item.code == code), None)
    try:
        steps = services.session.preview_enrollment(code, entry.dialog_choices if entry else None)
    except (ConfirmDialogUnrecognised, PageUnavailable, TransportError) as error:
        services.presenter.warn(str(error))
        raise typer.Exit(code=1) from error

    services.presenter.info(nb.PREVIEW_HEADER.format(code=code))
    for number, state in enumerate(steps, start=1):
        services.presenter.table(
            nb.PREVIEW_STEP.format(step=number),
            (nb.PREVIEW_CONTROLS, nb.PREVIEW_CHOICES),
            [
                (
                    state.labels(),
                    "; ".join(
                        f"{item.label}: {', '.join(option.label for option in item.options)}"
                        for item in state.selects
                    )
                    or "-",
                )
            ],
        )
    services.presenter.info(nb.PREVIEW_HOWTO.format(code=code))


@app.command()
@guarded
def choose(
    course: Annotated[str, typer.Argument(help="Emnekode")],
    field: Annotated[str, typer.Argument(help="Feltet i dialogen")],
    value: Annotated[str, typer.Argument(help="Verdien autofag skal velge")],
    config_path: ConfigOption = None,
) -> None:
    services = build_services(load_config(config_path))
    code = CourseCode(course)
    entry = next((item for item in services.watchlist.all_entries() if item.code == code), None)
    if entry is None:
        services.presenter.warn(nb.CHOICE_UNKNOWN_COURSE.format(code=code))
        raise typer.Exit(code=1)

    entry.dialog_choices[field.strip().casefold()] = value
    services.watchlist.upsert(entry)
    services.presenter.info(nb.CHOICE_SAVED.format(code=code, field=field, value=value))


@app.command()
@guarded
def logout(config_path: ConfigOption = None) -> None:
    config = load_config(config_path)
    _remove_directory(config.browser_profile_dir())
    RichPresenter().info(nb.LOGOUT_DONE)


def _remove_directory(path: Path) -> None:
    if not path.exists():
        return
    for child in sorted(path.rglob("*"), reverse=True):
        if child.is_file() or child.is_symlink():
            child.unlink(missing_ok=True)
        else:
            child.rmdir()
    path.rmdir()


@app.command()
@guarded
def version() -> None:
    typer.echo(__version__)


def _detach(services: Services, config_path: Path | None, dry_run: bool, verbose: bool) -> None:
    active = running_watch(services.run_lock)
    if active is not None:
        services.presenter.warn(
            nb.DETACHED_ALREADY_RUNNING.format(pid=active.pid, host=active.hostname)
        )
        raise typer.Exit(code=1)

    arguments = ["watch"]
    if config_path is not None:
        arguments += ["--config", str(config_path.resolve())]
    if dry_run:
        arguments.append("--dry-run")
    if verbose:
        arguments.append("--verbose")

    started = start_detached(arguments, services.config.storage.resolved_data_dir())
    services.presenter.info(nb.DETACHED_STARTED.format(pid=started.pid, log=started.log_path))


def _authenticate(services: Services) -> None:
    if services.config.studentweb.transport == "fake":
        return

    try:
        services.session.keepalive()
        services.presenter.info(nb.LOGIN_DONE)
        return
    except NotAuthenticated:
        services.logger.info("ingen brukbar økt, åpner nettleseren")
    except PageUnavailable as error:
        services.presenter.warn(str(error))
        raise typer.Exit(code=2) from error

    try:
        services.page.log_in(nb.LOGIN_INSTRUCTIONS)
        services.session.keepalive()
    except PageUnavailable as error:
        services.presenter.warn(nb.LOGIN_FAILED.format(reason=error))
        raise typer.Exit(code=2) from error

    services.presenter.info(nb.LOGIN_DONE)


def _run_watcher(services: Services, dry_run: bool) -> None:
    dispatcher = services.dispatcher()
    enroller = AutoEnroller(
        session=services.session,
        ledger=services.ledger,
        dispatcher=dispatcher,
        clock=services.clock,
        logger=services.logger,
        config=services.config.enroll,
        run_id=services.run_id,
        dry_run=dry_run,
    )
    watcher = Watcher(
        session=services.session,
        watchlist=services.watchlist,
        enroller=enroller,
        dispatcher=dispatcher,
        run_lock=services.run_lock,
        clock=services.clock,
        logger=services.logger,
        config=services.config,
        run_id=services.run_id,
    )

    _install_stop_handler(watcher)

    try:
        watcher.run()
    except RunAlreadyActive as error:
        services.presenter.warn(str(error))
        raise typer.Exit(code=1) from error
    except KeyboardInterrupt:
        services.presenter.info(nb.INTERRUPTED)
    except (PageUnavailable, TransportError) as error:
        services.presenter.warn(nb.WATCH_CRASHED.format(reason=error))
        raise typer.Exit(code=1) from error
    finally:
        _close_quietly(services)


def _install_stop_handler(watcher: Watcher) -> None:
    def handle(signal_number, frame) -> None:
        watcher.request_stop()

    for received in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(received, handle)
        except ValueError:
            return


def _close_quietly(services: Services) -> None:
    try:
        services.page.close()
    except Exception:  # noqa: BLE001
        services.logger.debug("kunne ikke lukke nettleseren", exc_info=True)


if __name__ == "__main__":
    app()
