from __future__ import annotations

from typing import Protocol

import keyring
from keyring.errors import KeyringError


class SecretStoreError(RuntimeError):
    pass


class SecretStore(Protocol):
    def get(self, name: str) -> str | None: ...

    def set(self, name: str, value: str) -> None: ...

    def delete(self, name: str) -> None: ...

    def known_values(self) -> frozenset[str]: ...


class KeyringSecretStore:
    def __init__(self, service_name: str) -> None:
        self._service_name = service_name
        self._seen: set[str] = set()

    def get(self, name: str) -> str | None:
        try:
            value = keyring.get_password(self._service_name, name)
        except KeyringError as error:
            raise SecretStoreError(f"could not read secret {name!r}: {error}") from error
        if value:
            self._seen.add(value)
        return value

    def set(self, name: str, value: str) -> None:
        try:
            keyring.set_password(self._service_name, name, value)
        except KeyringError as error:
            raise SecretStoreError(f"could not store secret {name!r}: {error}") from error
        self._seen.add(value)

    def delete(self, name: str) -> None:
        try:
            keyring.delete_password(self._service_name, name)
        except KeyringError:
            return

    def known_values(self) -> frozenset[str]:
        return frozenset(self._seen)


class InMemorySecretStore:
    def __init__(self, initial: dict[str, str] | None = None) -> None:
        self._values: dict[str, str] = dict(initial or {})

    def get(self, name: str) -> str | None:
        return self._values.get(name)

    def set(self, name: str, value: str) -> None:
        self._values[name] = value

    def delete(self, name: str) -> None:
        self._values.pop(name, None)

    def known_values(self) -> frozenset[str]:
        return frozenset(self._values.values())


SECRET_NTFY_TOPIC = "ntfy_topic"
SECRET_NTFY_TOKEN = "ntfy_token"
SECRET_SMTP_PASSWORD = "smtp_password"
SECRET_TWILIO_ACCOUNT_SID = "twilio_account_sid"
SECRET_TWILIO_AUTH_TOKEN = "twilio_auth_token"
