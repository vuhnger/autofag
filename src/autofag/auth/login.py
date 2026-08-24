from __future__ import annotations

from logging import Logger
from pathlib import Path
from typing import Protocol

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

from autofag.clock import Clock
from autofag.config import AppConfig

STORAGE_STATE_FILENAME = "storage-state.json"


class LoginFailed(RuntimeError):
    pass


class Presenter(Protocol):
    def info(self, message: str) -> None: ...


class BrowserLogin:
    def __init__(
        self, config: AppConfig, clock: Clock, logger: Logger, presenter: Presenter
    ) -> None:
        self._config = config
        self._clock = clock
        self._logger = logger
        self._presenter = presenter

    @property
    def storage_state_path(self) -> Path:
        return self._config.browser_profile_dir() / STORAGE_STATE_FILENAME

    def log_in(self, instructions: str) -> Path:
        profile_dir = self._config.browser_profile_dir()
        profile_dir.mkdir(parents=True, exist_ok=True)
        profile_dir.chmod(0o700)

        self._presenter.info(instructions)

        try:
            with sync_playwright() as playwright:
                context = playwright.chromium.launch_persistent_context(
                    user_data_dir=str(profile_dir),
                    headless=self._config.auth.headless,
                    args=["--no-first-run", "--no-default-browser-check"],
                )
                try:
                    page = context.pages[0] if context.pages else context.new_page()
                    page.goto(self._config.studentweb.base_url, wait_until="domcontentloaded")
                    page.wait_for_url(
                        f"**{self._config.auth.logged_in_marker}**",
                        timeout=self._config.auth.login_timeout_seconds * 1000,
                    )
                    context.storage_state(path=str(self.storage_state_path))
                finally:
                    context.close()
        except PlaywrightTimeout as error:
            raise LoginFailed("innloggingen tok for lang tid") from error
        except PlaywrightError as error:
            raise LoginFailed(f"nettleseren feilet: {error}") from error

        self.storage_state_path.chmod(0o600)
        self._logger.info("stored browser session in %s", self.storage_state_path)
        return self.storage_state_path

    def forget(self) -> None:
        profile_dir = self._config.browser_profile_dir()
        if not profile_dir.exists():
            return
        for path in sorted(profile_dir.rglob("*"), reverse=True):
            if path.is_file() or path.is_symlink():
                path.unlink(missing_ok=True)
            else:
                path.rmdir()
        profile_dir.rmdir()
