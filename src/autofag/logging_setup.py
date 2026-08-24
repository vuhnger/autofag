from __future__ import annotations

import logging
from logging import Filter, LogRecord

from autofag.storage.secrets import SecretStore

REDACTED = "[redigert]"


class SecretRedactionFilter(Filter):
    def __init__(self, secrets: SecretStore, extra: frozenset[str] = frozenset()) -> None:
        super().__init__()
        self._secrets = secrets
        self._extra = set(extra)

    def add(self, value: str) -> None:
        if value:
            self._extra.add(value)

    def filter(self, record: LogRecord) -> bool:
        record.msg = self._scrub(str(record.msg))
        if record.args:
            record.args = tuple(self._scrub(str(arg)) for arg in _as_tuple(record.args))
        return True

    def _scrub(self, text: str) -> str:
        for value in self._secrets.known_values() | self._extra:
            if value and value in text:
                text = text.replace(value, REDACTED)
        return text


def configure_logging(secrets: SecretStore, verbose: bool = False) -> logging.Logger:
    logger = logging.getLogger("autofag")
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)

    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)

    logger.filters.clear()
    logger.addFilter(SecretRedactionFilter(secrets))
    return logger


def _as_tuple(args: object) -> tuple:
    return args if isinstance(args, tuple) else (args,)
