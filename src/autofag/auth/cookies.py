from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

SESSION_COOKIE_NAME = "JSESSIONID"


class NoSessionCookie(RuntimeError):
    pass


class CookieProvider(Protocol):
    def current(self) -> dict[str, str]: ...

    def refresh(self) -> dict[str, str]: ...


class StaticCookies:
    def __init__(self, cookies: dict[str, str] | None = None) -> None:
        self._cookies = dict(cookies or {})

    def current(self) -> dict[str, str]:
        return dict(self._cookies)

    def refresh(self) -> dict[str, str]:
        return self.current()

    def replace(self, cookies: dict[str, str]) -> None:
        self._cookies = dict(cookies)


class BrowserProfileCookies:
    def __init__(self, storage_state_path: Path, cookie_domain: str) -> None:
        self._storage_state_path = storage_state_path
        self._cookie_domain = cookie_domain
        self._cached: dict[str, str] = {}

    def current(self) -> dict[str, str]:
        return dict(self._cached) if self._cached else self.refresh()

    def refresh(self) -> dict[str, str]:
        if not self._storage_state_path.exists():
            raise NoSessionCookie(f"no browser session at {self._storage_state_path}")

        payload = json.loads(self._storage_state_path.read_text(encoding="utf-8"))
        cookies = {
            cookie["name"]: cookie["value"]
            for cookie in payload.get("cookies", [])
            if self._cookie_domain in cookie.get("domain", "")
        }
        if SESSION_COOKIE_NAME not in cookies:
            raise NoSessionCookie(f"{SESSION_COOKIE_NAME} not present in browser session")

        self._cached = cookies
        return dict(cookies)
