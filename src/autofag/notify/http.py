from __future__ import annotations

from collections.abc import Mapping

import httpx
from httpx._client import USE_CLIENT_DEFAULT

from autofag.config import StudentwebConfig


class OutboundHttpError(RuntimeError):
    pass


class ForbiddenTarget(OutboundHttpError):
    pass


class OutboundHttpClient:
    def __init__(self, studentweb: StudentwebConfig, timeout: float) -> None:
        self._forbidden_prefix = studentweb.base_url
        self._client = httpx.Client(timeout=timeout, follow_redirects=False)

    def post(
        self,
        url: str,
        *,
        content: bytes | None = None,
        data: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        auth: tuple[str, str] | None = None,
    ) -> int:
        self._reject_studentweb(url)
        try:
            response = self._client.post(
                url,
                content=content,
                data=dict(data) if data else None,
                headers=dict(headers) if headers else None,
                auth=auth if auth is not None else USE_CLIENT_DEFAULT,
            )
        except httpx.HTTPError as error:
            raise OutboundHttpError(f"POST {url} failed: {error}") from error

        if response.status_code >= 400:
            raise OutboundHttpError(f"POST {url} returned {response.status_code}")
        return response.status_code

    def _reject_studentweb(self, url: str) -> None:
        if url.startswith(self._forbidden_prefix):
            raise ForbiddenTarget("notification client must never talk to Studentweb")

    def close(self) -> None:
        self._client.close()
