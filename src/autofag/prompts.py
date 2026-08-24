from __future__ import annotations

from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Protocol, TypeVar

T = TypeVar("T")


class PromptAborted(RuntimeError):
    pass


class Prompter(Protocol):
    def text(self, message: str, default: str = "") -> str: ...

    def secret(self, message: str) -> str: ...

    def select(self, message: str, choices: Sequence[tuple[str, str]]) -> str: ...

    def checkbox(self, message: str, choices: Sequence[tuple[str, str]]) -> list[str]: ...

    def confirm(self, message: str, default: bool = True) -> bool: ...


class QuestionaryPrompter:
    def __init__(self) -> None:
        self._worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="autofag-prompt")

    def text(self, message: str, default: str = "") -> str:
        import questionary

        answer = self._off_loop(lambda: questionary.text(message, default=default).ask())
        return _require(answer).strip()

    def secret(self, message: str) -> str:
        import questionary

        return _require(self._off_loop(lambda: questionary.password(message).ask())).strip()

    def select(self, message: str, choices: Sequence[tuple[str, str]]) -> str:
        import questionary

        options = [questionary.Choice(title=label, value=value) for value, label in choices]
        return _require(self._off_loop(lambda: questionary.select(message, choices=options).ask()))

    def checkbox(self, message: str, choices: Sequence[tuple[str, str]]) -> list[str]:
        import questionary

        options = [questionary.Choice(title=label, value=value) for value, label in choices]
        answer = self._off_loop(lambda: questionary.checkbox(message, choices=options).ask())
        if answer is None:
            raise PromptAborted("avbrutt")
        return list(answer)

    def confirm(self, message: str, default: bool = True) -> bool:
        import questionary

        answer = self._off_loop(lambda: questionary.confirm(message, default=default).ask())
        if answer is None:
            raise PromptAborted("avbrutt")
        return bool(answer)

    def close(self) -> None:
        self._worker.shutdown(wait=False)

    def _off_loop(self, question: Callable[[], T]) -> T:
        return self._worker.submit(question).result()


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
