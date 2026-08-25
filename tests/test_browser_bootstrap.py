from __future__ import annotations

import logging

import pytest

from autofag.auth.bootstrap import (
    BrowserInstallFailed,
    install_chromium,
    looks_like_missing_browser,
)


@pytest.mark.parametrize(
    "reason",
    [
        "Executable doesn't exist at /Users/x/ms-playwright/chromium-1140/chrome",
        "Please run the following command to download new browsers: playwright install",
    ],
)
def test_a_missing_browser_is_recognised(reason):
    assert looks_like_missing_browser(reason)


def test_a_profile_lock_is_not_mistaken_for_a_missing_browser():
    assert not looks_like_missing_browser("ProcessSingleton: failed to lock the profile")


def test_a_failed_download_says_what_to_run_by_hand(monkeypatch):
    def refuse(*args, **kwargs):
        raise OSError("nettverket er nede")

    monkeypatch.setattr("autofag.auth.bootstrap.subprocess.run", refuse)

    with pytest.raises(BrowserInstallFailed) as error:
        install_chromium(logging.getLogger("test"), timeout_seconds=1.0)

    assert "playwright install chromium" in str(error.value)
