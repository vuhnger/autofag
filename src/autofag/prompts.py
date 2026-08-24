from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol


class PromptAborted(RuntimeError):
    pass


class Prompter(Protocol):
    def text(self, message: str, default: str = "") -> str: ...

    def secret(self, message: str) -> str: ...

    def select(self, message: str, choices: Sequence[tuple[str, str]]) -> str: ...

    def checkbox(self, message: str, choices: Sequence[tuple[str, str]]) -> list[str]: ...

    def confirm(self, message: str, default: bool = True) -> bool: ...


class QuestionaryPrompter:
    def text(self, message: str, default: str = "") -> str:
        import questionary

        answer = questionary.text(message, default=default).ask()
        return _require(answer).strip()

    def secret(self, message: str) -> str:
        import questionary

        return _require(questionary.password(message).ask()).strip()

    def select(self, message: str, choices: Sequence[tuple[str, str]]) -> str:
        import questionary

        options = [questionary.Choice(title=label, value=value) for value, label in choices]
        return _require(questionary.select(message, choices=options).ask())

    def checkbox(self, message: str, choices: Sequence[tuple[str, str]]) -> list[str]:
        import questionary

        options = [questionary.Choice(title=label, value=value) for value, label in choices]
        answer = questionary.checkbox(message, choices=options).ask()
        if answer is None:
            raise PromptAborted("avbrutt")
        return list(answer)

    def confirm(self, message: str, default: bool = True) -> bool:
        import questionary

        answer = questionary.confirm(message, default=default).ask()
        if answer is None:
            raise PromptAborted("avbrutt")
        return bool(answer)


class ScriptedPrompter:
    def __init__(self, answers: Sequence[object]) -> None:
        self._answers = list(answers)
        self.asked: list[str] = []

    def _next(self, message: str) -> object:
        self.asked.append(message)
        if not self._answers:
            raise PromptAborted(f"no scripted answer left for {message!r}")
        return self._answers.pop(0)

    def text(self, message: str, default: str = "") -> str:
        return str(self._next(message))

    def secret(self, message: str) -> str:
        return str(self._next(message))

    def select(self, message: str, choices: Sequence[tuple[str, str]]) -> str:
        return str(self._next(message))

    def checkbox(self, message: str, choices: Sequence[tuple[str, str]]) -> list[str]:
        answer = self._next(message)
        return list(answer) if isinstance(answer, (list, tuple)) else [str(answer)]

    def confirm(self, message: str, default: bool = True) -> bool:
        return bool(self._next(message))


def _require(answer: str | None) -> str:
    if answer is None:
        raise PromptAborted("avbrutt")
    return answer
