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
    DialogControl,
    DialogOption,
    DialogSelect,
    DialogState,
    NotAuthenticated,
    PageUnavailable,
    ProfileInUse,
    RawSearchResult,
    SearchFilters,
)

FIND_SEARCH_BUTTON = """
(marker) => {
  const el = [...document.querySelectorAll('[onclick]')]
    .find(node => /PrimeFaces\\.ab/.test(node.getAttribute('onclick'))
               && node.getAttribute('onclick').includes(marker));
  return el ? el.id : null;
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

DISMISS_IDLE_DIALOG = """
(args) => {
  const owner = [...document.querySelectorAll('div, section, form')]
    .filter(node => node.offsetParent !== null)
    .find(node => {
      const text = (node.innerText || '').toLowerCase();
      return args.markers.some(marker => text.includes(marker));
    });
  if (!owner) return null;

  const control = [...owner.querySelectorAll('button, input[type=submit], a[id]')]
    .filter(el => el.offsetParent !== null)
    .find(el => {
      const label = (el.innerText || el.value || '').trim().toLowerCase();
      return args.labels.some(word => label.includes(word));
    });
  if (!control) return 'seen';

  control.click();
  return control.id || 'clicked';
}
"""

IS_SIGNED_IN = """
(selector) => !!document.querySelector(selector)
"""


CLICK_BY_ID = """
(id) => {
  const el = document.getElementById(id);
  if (!el) throw new Error('elementet ' + id + ' finnes ikke lenger');
  el.click();
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

READ_DIALOG_STATE = """
(marker) => {
  const owner = [...document.querySelectorAll('[id]')]
    .filter(node => node.id.includes(marker))
    .find(node => node.offsetParent !== null && (node.innerText || '').trim().length > 0);
  if (!owner) return null;
  const dialog = owner.closest('.ui-dialog') || owner;

  const controls = [...dialog.querySelectorAll('button, input[type=submit], a[id]')]
    .filter(el => el.id && el.offsetParent !== null)
    .map(el => ({id: el.id, label: (el.innerText || el.value || '').trim().toLowerCase()}));

  const labelFor = (select) => {
    const labelled = select.labels && select.labels.length ? select.labels[0].innerText : '';
    const described = select.getAttribute('aria-label') || '';
    const text = (labelled || described || select.name || select.id).trim();
    return text.replace(/[:\\s]+$/, '').toLowerCase();
  };

  const selects = [...dialog.querySelectorAll('select')]
    .filter(el => el.id || el.name)
    .map(el => ({
      id: el.id || el.name,
      label: labelFor(el),
      selected: el.value || '',
      options: [...el.options]
        .filter(option => option.value)
        .map(option => ({
          value: option.value,
          label: option.text.trim(),
          disabled: option.disabled || option.hasAttribute('disabled'),
        })),
    }));

  return {html: dialog.outerHTML, controls: controls, selects: selects};
}
"""

CHOOSE_OPTION = """
(args) => {
  const el = document.getElementById(args.id)
    || document.querySelector('[name="' + args.id + '"]');
  if (!el) throw new Error('nedtrekkslisten ' + args.id + ' finnes ikke');
  el.value = args.value;
  el.dispatchEvent(new Event('input', {bubbles: true}));
  el.dispatchEvent(new Event('change', {bubbles: true}));
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
        if self._is_signed_in(page):
            return

        self._presenter.info(instructions)
        page.goto(self._config.studentweb.base_url, wait_until="domcontentloaded")
        try:
            page.wait_for_function(
                IS_SIGNED_IN,
                arg=self._config.auth.signed_in_selector,
                timeout=self._config.auth.login_timeout_seconds * 1000,
            )
        except PlaywrightTimeout as error:
            raise NotAuthenticated("innloggingen tok for lang tid") from error

    def open(self) -> SearchFilters:
        page = self._ensure_page()
        self._dismiss_idle_dialog(page)
        if not self._is_on_courses_page(page):
            page.goto(self._config.studentweb.courses_url, wait_until="domcontentloaded")
        if not self._is_signed_in(page):
            raise NotAuthenticated("Studentweb sendte oss til innloggingssiden")

        return SearchFilters(
            release=page.evaluate(READ_RELEASE, self._config.selectors.release_pattern)
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
        if not page.evaluate(HAS_NEXT_PAGE, selectors.paginator_next_class):
            raise PageUnavailable("det finnes ingen neste side")

        with page.expect_response(self._is_postback, timeout=30000):
            page.evaluate(CLICK_NEXT_PAGE, selectors.paginator_next_class)
        return self._read_result(page, page_index=1)

    def open_confirm_dialog(self, button_id: str) -> DialogState:
        page = self._ensure_page()
        self._click_and_wait(page, button_id)
        return self._read_dialog(page)

    def choose(self, select_id: str, value: str) -> DialogState:
        page = self._ensure_page()
        try:
            page.evaluate(CHOOSE_OPTION, {"id": select_id, "value": value})
        except PlaywrightError as error:
            raise ConfirmDialogUnrecognised(f"kunne ikke velge i {select_id}: {error}") from error
        page.wait_for_timeout(200)
        return self._read_dialog(page)

    def advance_dialog(self, control_id: str) -> DialogState:
        page = self._ensure_page()
        self._click_and_wait(page, control_id)
        try:
            return self._read_dialog(page)
        except ConfirmDialogUnrecognised:
            return DialogState(html=page.inner_text("body"))

    def read_outcome(self) -> str:
        return self._ensure_page().inner_text("body")

    def _read_dialog(self, page: Page) -> DialogState:
        marker = self._config.selectors.confirm_form_marker
        try:
            page.wait_for_function(DIALOG_IS_READY, arg=marker, timeout=15000)
        except PlaywrightTimeout as error:
            seen = page.evaluate(DESCRIBE_DIALOG_CANDIDATES, marker)
            raise ConfirmDialogUnrecognised(
                f"bekreftelsesdialogen ble aldri synlig. Noder med {marker!r}: {seen}"
            ) from error

        raw = page.evaluate(READ_DIALOG_STATE, marker)
        if not raw:
            raise ConfirmDialogUnrecognised("bekreftelsesdialogen dukket aldri opp")

        self._logger.debug("dialogsteg: %s", raw)
        return DialogState(
            html=raw["html"],
            controls=tuple(
                DialogControl(id=item["id"], label=item["label"]) for item in raw["controls"]
            ),
            selects=tuple(
                DialogSelect(
                    id=item["id"],
                    label=item["label"],
                    options=tuple(
                        DialogOption(
                            value=option["value"],
                            label=option["label"],
                            disabled=bool(option.get("disabled")),
                        )
                        for option in item["options"]
                    ),
                    selected=item["selected"],
                )
                for item in raw["selects"]
            ),
        )

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

    def _dismiss_idle_dialog(self, page: Page) -> None:
        selectors = self._config.selectors
        try:
            outcome = page.evaluate(
                DISMISS_IDLE_DIALOG,
                {
                    "markers": list(selectors.idle_dialog_markers),
                    "labels": list(selectors.idle_dismiss_labels),
                },
            )
        except PlaywrightError:
            return

        if outcome is None:
            return
        if outcome == "seen":
            self._logger.warning("fant en utloggingsvarsel-dialog uten knapp å trykke på")
            return
        self._logger.info("lukket utloggingsvarselet via %s", outcome)
        page.wait_for_timeout(300)

    def _is_signed_in(self, page: Page) -> bool:
        try:
            return bool(page.evaluate(IS_SIGNED_IN, self._config.auth.signed_in_selector))
        except PlaywrightError:
            return False

    def _is_on_courses_page(self, page: Page) -> bool:
        return self._config.studentweb.courses_path in page.url and self._is_signed_in(page)

    def _postback_url(self) -> str:
        return self._config.studentweb.courses_path

    def _is_postback(self, response) -> bool:
        return response.request.method == "POST" and self._postback_url() in response.url

    def _click_and_wait(self, page: Page, element_id: str) -> None:
        try:
            with page.expect_response(self._is_postback, timeout=30000):
                page.evaluate(CLICK_BY_ID, element_id)
        except PlaywrightTimeout as error:
            raise PageUnavailable(f"Studentweb svarte ikke på klikk mot {element_id}") from error
        except PlaywrightError as error:
            raise PageUnavailable(f"kunne ikke klikke {element_id}: {error}") from error
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
