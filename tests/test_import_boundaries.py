from __future__ import annotations

import ast
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "src" / "autofag"

RESTRICTED_MODULES = {
    "httpx": {"notify/http.py"},
    "playwright": {"auth/browser.py"},
    "keyring": {"storage/secrets.py"},
    "subprocess": {"notify/channels.py"},
    "smtplib": {"notify/channels.py"},
    "questionary": {"prompts.py"},
    "rich": {"presentation.py"},
}


def _imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    return roots


@pytest.mark.parametrize("restricted,allowed", sorted(RESTRICTED_MODULES.items()))
def test_restricted_module_is_only_imported_where_it_belongs(restricted, allowed):
    offenders = []
    for path in sorted(PACKAGE_ROOT.rglob("*.py")):
        relative = path.relative_to(PACKAGE_ROOT).as_posix()
        if relative in allowed:
            continue
        if restricted in _imported_roots(path):
            offenders.append(relative)

    assert offenders == [], (
        f"{restricted!r} may only be imported from {sorted(allowed)}, "
        f"but is also imported in {offenders}"
    )


def test_every_studentweb_action_goes_through_the_paced_page():
    paced = (PACKAGE_ROOT / "transport" / "pace.py").read_text(encoding="utf-8")
    app = (PACKAGE_ROOT / "app.py").read_text(encoding="utf-8")
    assert "_budget_store.consume" in paced
    assert "PacedStudentwebPage(" in app


def test_the_notification_client_can_never_reach_studentweb():
    outbound = (PACKAGE_ROOT / "notify" / "http.py").read_text(encoding="utf-8")
    assert "_reject_studentweb" in outbound
