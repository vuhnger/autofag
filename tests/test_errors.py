from __future__ import annotations

import typer

from autofag.errors import guarded, write_crash_log


def test_an_unexpected_error_becomes_an_exit_not_a_traceback():
    @guarded
    def boom() -> None:
        raise ValueError("uventet")

    try:
        boom()
    except typer.Exit as exit_signal:
        assert exit_signal.exit_code == 1
    else:
        raise AssertionError("expected the guard to convert the error into an Exit")


def test_ctrl_c_exits_quietly():
    @guarded
    def interrupted() -> None:
        raise KeyboardInterrupt

    try:
        interrupted()
    except typer.Exit as exit_signal:
        assert exit_signal.exit_code == 130
    else:
        raise AssertionError("expected the guard to convert the interrupt into an Exit")


def test_a_deliberate_exit_passes_straight_through():
    @guarded
    def deliberate() -> None:
        raise typer.Exit(code=2)

    try:
        deliberate()
    except typer.Exit as exit_signal:
        assert exit_signal.exit_code == 2


def test_even_a_base_exception_is_caught():
    @guarded
    def recursion() -> None:
        raise RecursionError("for dypt")

    try:
        recursion()
    except typer.Exit:
        return
    raise AssertionError("expected the guard to catch it")


def test_the_crash_log_records_the_traceback(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))

    try:
        raise ValueError("skrivbar feil")
    except ValueError as error:
        path = write_crash_log(error)

    assert path.exists()
    assert "skrivbar feil" in path.read_text(encoding="utf-8")
