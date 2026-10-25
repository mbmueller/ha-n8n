"""n8n Public API client (stub)."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)


class N8nApiError(Exception):
    """Base error for n8n API failures."""


class N8nAuthError(N8nApiError):
    """Raised when the API key is rejected (HTTP 401)."""


class N8nApiClient:
    """Minimal async client for the n8n Public API.

    Phase 0 stub — methods raise ``NotImplementedError`` until Phase 1.
    Auth header convention: ``X-N8N-API-KEY``.
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        base_url: str,
        api_key: str,
        *,
        verify_ssl: bool = True,
    ) -> None:
        self._session = session
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._verify_ssl = verify_ssl

    @property
    def api_root(self) -> str:
        """Return the Public API root (``…/api/v1``)."""
        return f"{self._base_url}/api/v1"

    def _headers(self) -> dict[str, str]:
        return {"X-N8N-API-KEY": self._api_key}

    async def async_validate(self) -> dict[str, Any]:
        """Validate connectivity / auth (Phase 1)."""
        raise NotImplementedError("N8nApiClient.async_validate — Phase 1")

    async def async_get_workflows(self) -> list[dict[str, Any]]:
        """List workflows (Phase 1)."""
        raise NotImplementedError("N8nApiClient.async_get_workflows — Phase 1")
