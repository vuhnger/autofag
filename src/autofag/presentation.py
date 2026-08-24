from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol


class Presenter(Protocol):
    def info(self, message: str) -> None: ...

    def warn(self, message: str) -> None: ...

    def table(self, title: str, headers: Sequence[str], rows: Sequence[Sequence[str]]) -> None: ...


class RichPresenter:
    def __init__(self) -> None:
        from rich.console import Console

        self._console = Console()

    def info(self, message: str) -> None:
        self._console.print(message)

    def warn(self, message: str) -> None:
        self._console.print(f"[yellow]{message}[/yellow]")

    def table(self, title: str, headers: Sequence[str], rows: Sequence[Sequence[str]]) -> None:
        from rich.table import Table

        table = Table(title=title, header_style="bold")
        for header in headers:
            table.add_column(header)
        for row in rows:
            table.add_row(*[str(cell) for cell in row])
        self._console.print(table)


class RecordingPresenter:
    def __init__(self) -> None:
        self.messages: list[str] = []
        self.tables: list[tuple[str, list[list[str]]]] = []

    def info(self, message: str) -> None:
        self.messages.append(message)

    def warn(self, message: str) -> None:
        self.messages.append(message)

    def table(self, title: str, headers: Sequence[str], rows: Sequence[Sequence[str]]) -> None:
        self.tables.append((title, [[str(cell) for cell in row] for row in rows]))
