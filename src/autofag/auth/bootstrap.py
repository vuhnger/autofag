from __future__ import annotations

import subprocess
import sys
from logging import Logger

from autofag import strings_nb as nb

MISSING_BROWSER_MARKERS = ("executable doesn't exist", "playwright install")


class BrowserInstallFailed(RuntimeError):
    pass


def looks_like_missing_browser(reason: str) -> bool:
    haystack = reason.casefold()
    return any(marker in haystack for marker in MISSING_BROWSER_MARKERS)


def install_chromium(logger: Logger, timeout_seconds: float) -> None:
    logger.info(nb.BROWSER_INSTALLING)
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise BrowserInstallFailed(nb.BROWSER_INSTALL_FAILED.format(reason=error)) from error

    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip().splitlines()
        raise BrowserInstallFailed(
            nb.BROWSER_INSTALL_FAILED.format(reason=detail[-1] if detail else completed.returncode)
        )
