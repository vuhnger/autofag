from __future__ import annotations


class TransportError(RuntimeError):
    pass


class ForbiddenTarget(TransportError):
    pass


class BudgetExhausted(TransportError):
    pass


class RequestFailed(TransportError):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
