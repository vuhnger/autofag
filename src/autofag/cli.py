from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from autofag import __version__
from autofag import strings_nb as nb
from autofag.app import Services, build_services
from autofag.config import load_config
from autofag.init_flow import InitWizard, WizardAborted
from autofag.models import SearchCriteria
from autofag.presentation import RichPresenter
from autofag.prompts import PromptAborted, QuestionaryPrompter
from autofag.storage.repos import RunAlreadyActive
from autofag.studentweb.page import NotAuthenticated, PageUnavailable
from autofag.transport.errors import TransportError
from autofag.watch.enroller import AutoEnroller
from autofag.watch.watcher import Watcher

app = typer.Typer(add_completion=False, help="Overvåker emner på UiO Studentweb.")

ConfigOption = Annotated[Path | None, typer.Option("--config", help="Sti til config.yaml")]
DryRunOption = Annotated[
    bool, typer.Option("--dry-run", help="Stopp før bekreftelsen, meld aldri på")
]
VerboseOption = Annotated[bool, typer.Option("--verbose", help="Mer logging")]


@app.command()
def init(
    config_path: ConfigOption = None,
    dry_run: DryRunOption = False,
    verbose: VerboseOption = False,
) -> None:
    services = build_services(load_config(config_path), verbose)
    _authenticate(services)

    wizard = InitWizard(
        session=services.session,
        prompter=QuestionaryPrompter(),
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

    if outcome.started:
        _run_watcher(services, dry_run)


@app.command()
def watch(
    config_path: ConfigOption = None,
    dry_run: DryRunOption = False,
    verbose: VerboseOption = False,
) -> None:
    services = build_services(load_config(config_path), verbose)
    if not services.watchlist.active_entries():
        services.presenter.warn(nb.WATCH_NOTHING_TO_DO)
        raise typer.Exit(code=1)
    _authenticate(services)
    _run_watcher(services, dry_run)


@app.command()
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
def version() -> None:
    typer.echo(__version__)


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

    try:
        watcher.run()
    except RunAlreadyActive as error:
        services.presenter.warn(str(error))
        raise typer.Exit(code=1) from error
    except KeyboardInterrupt:
        services.presenter.info("Stoppet.")


if __name__ == "__main__":
    app()
