from __future__ import annotations

import functools
import traceback
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import typer

from autofag import strings_nb as nb
from autofag.config import default_data_dir
from autofag.presentation import RichPresenter

CRASH_LOG_FILENAME = "last-crash.log"


def guarded[T](command: Callable[..., T]) -> Callable[..., T]:
    @functools.wraps(command)
    def wrapper(*args, **kwargs):
        try:
            return command(*args, **kwargs)
        except (typer.Exit, typer.Abort):
            raise
        except KeyboardInterrupt:
            RichPresenter().info(nb.INTERRUPTED)
            raise typer.Exit(code=130) from None
        except BaseException as error:
            log_path = write_crash_log(error)
            RichPresenter().warn(nb.UNEXPECTED_ERROR.format(reason=error, log=log_path))
            raise typer.Exit(code=1) from None

    return wrapper


def write_crash_log(error: BaseException) -> Path:
    path = default_data_dir() / CRASH_LOG_FILENAME
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            f"{datetime.now(UTC).isoformat()}\n"
            + "".join(traceback.format_exception(type(error), error, error.__traceback__)),
            encoding="utf-8",
        )
    except OSError:
        return path
    return path
