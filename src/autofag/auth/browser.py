from __future__ import annotations

import contextlib
import os
from logging import Logger
from pathlib import Path

from playwright.sync_api import BrowserContext, Page, Playwright, sync_playwright
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from autofag import strings_nb as nb
from autofag.config import AppConfig
from autofag.models import SearchCriteria
from autofag.studentweb.page import (
    ConfirmDialogUnrecognised,
    NotAuthenticated,
    PageUnavailable,
    ProfileInUse,
    RawSearchResult,
    SearchFilters,
    SelectOption,
)

FIND_SEARCH_BUTTON = """
(marker) => {
  const el = [...document.querySelectorAll('[onclick]')]
    .find(node => /PrimeFaces\\.ab/.test(node.getAttribute('onclick'))
               && node.getAttribute('onclick').includes(marker));
  return el ? el.id : null;
}
"""

READ_OPTIONS = """
(suffix) => {
  const select = [...document.querySelectorAll('select')].find(s => s.id.endsWith(suffix));
  if (!select) return [];
  return [...select.options].filter(o => o.value).map(o => ({value: o.value, label: o.text}));
}
"""

READ_RELEASE = """
(pattern) => {
  const match = document.body.innerText.match(new RegExp(pattern));
  return match ? match[1].trim() : 'unknown';
}
"""

READ_REGION = """
(suffix) => {
  const el = [...document.querySelectorAll('[id]')].find(node => node.id.endsWith(suffix));
  return el ? el.outerHTML : '';
}
"""

READ_REGION_CONTAINING = """
(marker) => {
  const el = [...document.querySelectorAll('[id]')].find(node => node.id.includes(marker));
  return el ? el.outerHTML : '';
}
"""

DIALOG_IS_READY = """
(marker) => {
  return [...document.querySelectorAll('[id]')]
    .filter(node => node.id.includes(marker))
    .some(node => node.offsetParent !== null && (node.innerText || '').trim().length > 0);
}
"""

READ_VISIBLE_DIALOG = """
(marker) => {
  const node = [...document.querySelectorAll('[id]')]
    .filter(el => el.id.includes(marker))
    .find(el => el.offsetParent !== null && (el.innerText || '').trim().length > 0);
  if (!node) return '';
  return (node.closest('.ui-dialog') || node).outerHTML;
}
"""

DESCRIBE_DIALOG_CANDIDATES = """
(marker) => {
  return [...document.querySelectorAll('[id]')]
    .filter(el => el.id.includes(marker))
    .map(el => ({
      id: el.id,
      visible: el.offsetParent !== null,
      text: (el.innerText || '').replace(/\\s+/g, ' ').trim().slice(0, 80),
    }));
}
"""

HAS_NEXT_PAGE = """
(className) => {
  return [...document.getElementsByClassName(className)]
    .some(el => !el.className.includes('ui-state-disabled'));
}
"""

CLICK_NEXT_PAGE = """
(className) => {
  const el = [...document.getElementsByClassName(className)]
    .find(node => !node.className.includes('ui-state-disabled'));
  if (!el) return false;
  el.click();
  return true;
}
"""

FIND_CONFIRM_CONTROL = """
(args) => {
  const owner = [...document.querySelectorAll('[id]')]
    .filter(node => node.id.includes(args.marker))
    .find(node => node.offsetParent !== null && (node.innerText || '').trim().length > 0);
  if (!owner) return [];
  const dialog = owner.closest('.ui-dialog') || owner;
  return [...dialog.querySelectorAll('button, input[type=submit], a[id]')]
    .filter(el => el.id && el.offsetParent !== null)
    .map(el => ({id: el.id, label: (el.innerText || el.value || '').trim().toLowerCase()}));
}
"""


class PlaywrightStudentwebPage:
    def __init__(self, config: AppConfig, logger: Logger, presenter) -> None:
        self._config = config
        self._logger = logger
        self._presenter = presenter
        self._playwright: Playwright | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    def log_in(self, instructions: str) -> None:
        page = self._ensure_page()
        if self._is_on_courses_page(page):
            return

        self._presenter.info(instructions)
        page.goto(self._config.studentweb.base_url, wait_until="domcontentloaded")
        try:
            page.wait_for_url(
                f"**{self._config.auth.logged_in_marker}**",
                timeout=self._config.auth.login_timeout_seconds * 1000,
            )
        except PlaywrightTimeout as error:
            raise NotAuthenticated("innloggingen tok for lang tid") from error

    def open(self) -> SearchFilters:
        page = self._ensure_page()
        if not self._is_on_courses_page(page):
            page.goto(self._config.studentweb.courses_url, wait_until="domcontentloaded")
        if not self._is_on_courses_page(page):
            raise NotAuthenticated("Studentweb sendte oss til innloggingssiden")

        selectors = self._config.selectors
        return SearchFilters(
            subjects=self._options(page, selectors.subject_select_suffix),
            faculties=self._options(page, selectors.faculty_select_suffix),
            release=page.evaluate(READ_RELEASE, selectors.release_pattern),
        )

    def search(self, criteria: SearchCriteria) -> RawSearchResult:
        page = self._ensure_page()
        self.open()
        selectors = self._config.selectors

        self._fill(page, selectors.course_code_input_suffix, criteria.course_code)
        self._fill(page, selectors.course_name_input_suffix, criteria.course_name)
        self._choose(page, selectors.subject_select_suffix, criteria.subject)
        self._choose(page, selectors.faculty_select_suffix, criteria.faculty)

        button_id = page.evaluate(FIND_SEARCH_BUTTON, selectors.search_update_marker)
        if not button_id:
            raise PageUnavailable("fant ikke søkeknappen på siden")

        self._click_and_wait(page, button_id)
        return self._read_result(page, page_index=0)

    def next_page(self) -> RawSearchResult:
        page = self._ensure_page()
        selectors = self._config.selectors
        with page.expect_response(self._is_postback):
            moved = page.evaluate(CLICK_NEXT_PAGE, selectors.paginator_next_class)
        if not moved:
            raise PageUnavailable("det finnes ingen neste side")
        return self._read_result(page, page_index=1)

    def open_confirm_dialog(self, button_id: str) -> str:
        page = self._ensure_page()
        marker = self._config.selectors.confirm_form_marker
        self._click_and_wait(page, button_id)

        try:
            page.wait_for_function(DIALOG_IS_READY, arg=marker, timeout=15000)
        except PlaywrightTimeout as error:
            seen = page.evaluate(DESCRIBE_DIALOG_CANDIDATES, marker)
            raise ConfirmDialogUnrecognised(
                f"bekreftelsesdialogen ble aldri synlig. Noder med {marker!r}: {seen}"
            ) from error

        dialog = page.evaluate(READ_VISIBLE_DIALOG, marker)
        if not dialog:
            raise ConfirmDialogUnrecognised("bekreftelsesdialogen dukket aldri opp")
        return dialog

    def find_confirm_control(self) -> str:
        page = self._ensure_page()
        selectors = self._config.selectors
        controls = page.evaluate(FIND_CONFIRM_CONTROL, {"marker": selectors.confirm_form_marker})
        self._logger.debug("kontroller i bekreftelsesdialogen: %s", controls)
        candidates = [
            control["id"]
            for control in controls
            if any(word in control["label"] for word in selectors.confirm_positive_labels)
            and not any(word in control["label"] for word in selectors.confirm_negative_labels)
        ]
        if len(candidates) != 1:
            seen = ", ".join(sorted({c["label"] or c["id"] for c in controls})) or "ingen"
            raise ConfirmDialogUnrecognised(
                f"forventet nøyaktig én bekreftknapp, fant {len(candidates)}. "
                f"Kontroller i dialogen: {seen}"
            )
        return candidates[0]

    def confirm_enrollment(self, confirm_button_id: str) -> str:
        page = self._ensure_page()
        self._click_and_wait(page, confirm_button_id)
        return page.inner_text("body")

    def close(self) -> None:
        if self._context is not None:
            with contextlib.suppress(PlaywrightError):
                self._context.close()
            self._context = None
        self._stop_playwright()
        self._page = None

    def _stop_playwright(self) -> None:
        if self._playwright is not None:
            with contextlib.suppress(PlaywrightError):
                self._playwright.stop()
            self._playwright = None

    def _ensure_page(self) -> Page:
        if self._page is not None:
            return self._page

        profile_dir = self._config.browser_profile_dir()
        profile_dir.mkdir(parents=True, exist_ok=True)
        profile_dir.chmod(0o700)

        holder = release_stale_profile_lock(profile_dir)
        if holder is not None:
            raise ProfileInUse(nb.BROWSER_PROFILE_IN_USE.format(pid=holder))

        try:
            playwright = sync_playwright().start()
            self._playwright = playwright
            self._context = playwright.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                headless=self._config.auth.headless,
                args=["--no-first-run", "--no-default-browser-check"],
            )
        except PlaywrightError as error:
            self._stop_playwright()
            if _is_profile_in_use(error):
                raise ProfileInUse(nb.BROWSER_PROFILE_IN_USE_UNKNOWN) from error
            raise PageUnavailable(nb.BROWSER_FAILED.format(reason=error)) from error

        context = self._context
        if context is None:
            raise PageUnavailable("nettleseren har ingen aktiv kontekst")
        self._page = context.pages[0] if context.pages else context.new_page()
        return self._page

    def _is_on_courses_page(self, page: Page) -> bool:
        return self._config.auth.logged_in_marker in page.url

    def _postback_url(self) -> str:
        return self._config.studentweb.courses_path

    def _is_postback(self, response) -> bool:
        return response.request.method == "POST" and self._postback_url() in response.url

    def _click_and_wait(self, page: Page, element_id: str) -> None:
        try:
            with page.expect_response(self._is_postback, timeout=30000):
                page.evaluate("(id) => document.getElementById(id).click()", element_id)
        except PlaywrightTimeout as error:
            raise PageUnavailable(f"Studentweb svarte ikke på klikk mot {element_id}") from error
        page.wait_for_timeout(250)

    def _fill(self, page: Page, suffix: str, value: str) -> None:
        page.evaluate(
            """(args) => {
                const el = [...document.querySelectorAll('input')]
                    .find(node => node.id.endsWith(args.suffix));
                if (el) { el.value = args.value; }
            }""",
            {"suffix": suffix, "value": value},
        )

    def _choose(self, page: Page, suffix: str, value: str) -> None:
        page.evaluate(
            """(args) => {
                const el = [...document.querySelectorAll('select')]
                    .find(node => node.id.endsWith(args.suffix));
                if (el) { el.value = args.value; }
            }""",
            {"suffix": suffix, "value": value},
        )

    def _options(self, page: Page, suffix: str) -> tuple[SelectOption, ...]:
        raw = page.evaluate(READ_OPTIONS, suffix)
        return tuple(SelectOption(value=item["value"], label=item["label"]) for item in raw)

    def _read_result(self, page: Page, page_index: int) -> RawSearchResult:
        selectors = self._config.selectors
        return RawSearchResult(
            result_html=page.evaluate(READ_REGION, selectors.result_table_suffix),
            hit_count_html=page.evaluate(READ_REGION_CONTAINING, selectors.hit_count_marker),
            page_index=page_index,
            extra={"has_next": str(page.evaluate(HAS_NEXT_PAGE, selectors.paginator_next_class))},
        )


SINGLETON_FILES = ("SingletonLock", "SingletonCookie", "SingletonSocket")


def release_stale_profile_lock(profile_dir: Path) -> int | None:
    lock = profile_dir / "SingletonLock"
    if not lock.is_symlink() and not lock.exists():
        return None

    holder = _lock_holder_pid(lock)
    if holder is not None and _process_is_alive(holder):
        return holder

    for name in SINGLETON_FILES:
        path = profile_dir / name
        try:
            path.unlink(missing_ok=True)
        except OSError:
            continue
    return None


def _lock_holder_pid(lock: Path) -> int | None:
    try:
        target = os.readlink(lock)
    except OSError:
        return None
    _, _, pid_text = target.rpartition("-")
    try:
        return int(pid_text)
    except ValueError:
        return None


def _process_is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _is_profile_in_use(error: Exception) -> bool:
    text = str(error)
    return "already in use" in text or "Opening in existing browser session" in text
