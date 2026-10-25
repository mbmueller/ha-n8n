"""n8n Public API client."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urljoin

import aiohttp
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .models import Workflow

_LOGGER = logging.getLogger(__name__)

_REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)


class N8nApiError(Exception):
    """Base error for n8n API failures."""


class N8nAuthError(N8nApiError):
    """Raised when the API key is rejected (HTTP 401/403)."""


class N8nNotFoundError(N8nApiError):
    """Raised when a resource is missing (HTTP 404)."""


def _tag_names(raw_tags: Any) -> list[str]:
    """Extract tag names from n8n tag objects or strings."""
    if not raw_tags:
        return []
    names: list[str] = []
    for tag in raw_tags:
        if isinstance(tag, str):
            names.append(tag)
        elif isinstance(tag, dict) and tag.get("name"):
            names.append(str(tag["name"]))
    return names


def _extract_webhook_path(nodes: Any) -> str | None:
    """Return the first Webhook node production path, if any."""
    if not isinstance(nodes, list):
        return None
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_type = str(node.get("type", "")).lower()
        if "webhook" not in node_type:
            continue
        params = node.get("parameters") or {}
        path = params.get("path")
        if path:
            return str(path).lstrip("/")
    return None


def workflow_from_api(payload: dict[str, Any]) -> Workflow:
    """Map an n8n workflow JSON object to a Workflow dataclass."""
    return Workflow(
        workflow_id=str(payload["id"]),
        name=str(payload.get("name") or payload["id"]),
        active=bool(payload.get("active", False)),
        tags=_tag_names(payload.get("tags")),
        updated_at=payload.get("updatedAt"),
        webhook_path=_extract_webhook_path(payload.get("nodes")),
    )


class N8nApiClient:
    """Async client for the n8n Public API (``X-N8N-API-KEY``)."""

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

    @classmethod
    def from_hass(
        cls,
        hass: Any,
        base_url: str,
        api_key: str,
        *,
        verify_ssl: bool = True,
    ) -> N8nApiClient:
        """Build a client using Home Assistant's shared aiohttp session."""
        return cls(
            async_get_clientsession(hass, verify_ssl=verify_ssl),
            base_url,
            api_key,
            verify_ssl=verify_ssl,
        )

    @property
    def base_url(self) -> str:
        """Return the configured n8n base URL (no trailing slash)."""
        return self._base_url

    @property
    def api_root(self) -> str:
        """Return the Public API root (``…/api/v1``)."""
        return f"{self._base_url}/api/v1"

    def _headers(self) -> dict[str, str]:
        return {
            "X-N8N-API-KEY": self._api_key,
            "Accept": "application/json",
        }

    async def _request(
        self,
        method: str,
        url: str,
        *,
        json: dict[str, Any] | None = None,
        auth: bool = True,
    ) -> Any:
        """Perform an HTTP request and map common error statuses."""
        headers = self._headers() if auth else {"Accept": "application/json"}
        if json is not None:
            headers = {**headers, "Content-Type": "application/json"}

        try:
            async with self._session.request(
                method,
                url,
                headers=headers,
                json=json,
                timeout=_REQUEST_TIMEOUT,
            ) as response:
                if response.status in (401, 403):
                    raise N8nAuthError("Invalid n8n API key")
                if response.status == 404:
                    text = await response.text()
                    raise N8nNotFoundError(text or "Not found")
                if response.status >= 400:
                    text = await response.text()
                    raise N8nApiError(
                        f"n8n API error {response.status}: {text[:200]}"
                    )
                if response.status == 204:
                    return None
                content_type = response.headers.get("Content-Type", "")
                if "application/json" in content_type:
                    return await response.json(content_type=None)
                text = await response.text()
                return text or None
        except (N8nApiError, N8nAuthError, N8nNotFoundError):
            raise
        except TimeoutError as err:
            raise N8nApiError("Timeout talking to n8n") from err
        except aiohttp.ClientError as err:
            raise N8nApiError(f"Connection error: {err}") from err

    async def async_validate(self) -> dict[str, Any]:
        """Validate connectivity and auth via a lightweight workflows list."""
        data = await self._request(
            "GET", f"{self.api_root}/workflows?limit=1"
        )
        if not isinstance(data, dict):
            return {"ok": True}
        return {"ok": True, "count": len(data.get("data") or [])}

    async def async_get_workflows(self) -> list[Workflow]:
        """List all workflows (paginated)."""
        workflows: list[Workflow] = []
        cursor: str | None = None

        while True:
            url = f"{self.api_root}/workflows?limit=100"
            if cursor:
                url = f"{url}&cursor={cursor}"
            payload = await self._request("GET", url)
            if not isinstance(payload, dict):
                break
            for item in payload.get("data") or []:
                if isinstance(item, dict) and item.get("id") is not None:
                    workflows.append(workflow_from_api(item))
            cursor = payload.get("nextCursor")
            if not cursor:
                break

        return workflows

    async def async_get_workflow(self, workflow_id: str) -> Workflow:
        """Fetch a single workflow (includes nodes when permitted)."""
        payload = await self._request(
            "GET", f"{self.api_root}/workflows/{workflow_id}"
        )
        if not isinstance(payload, dict):
            raise N8nApiError("Unexpected workflow response")
        return workflow_from_api(payload)

    async def async_activate_workflow(self, workflow_id: str) -> Workflow:
        """Activate (publish) a workflow."""
        payload = await self._request(
            "POST", f"{self.api_root}/workflows/{workflow_id}/activate"
        )
        if isinstance(payload, dict) and payload.get("id") is not None:
            return workflow_from_api(payload)
        return await self.async_get_workflow(workflow_id)

    async def async_deactivate_workflow(self, workflow_id: str) -> Workflow:
        """Deactivate (unpublish) a workflow."""
        payload = await self._request(
            "POST", f"{self.api_root}/workflows/{workflow_id}/deactivate"
        )
        if isinstance(payload, dict) and payload.get("id") is not None:
            return workflow_from_api(payload)
        return await self.async_get_workflow(workflow_id)

    async def async_execute_workflow(
        self,
        workflow_id: str,
        data: dict[str, Any] | None = None,
    ) -> Any:
        """Trigger a workflow via Public API execute (when supported)."""
        return await self._request(
            "POST",
            f"{self.api_root}/workflows/{workflow_id}/execute",
            json=data or {},
        )

    async def async_trigger_webhook(
        self,
        webhook_path: str,
        data: dict[str, Any] | None = None,
    ) -> Any:
        """POST to an n8n production webhook path (no API key)."""
        path = webhook_path.lstrip("/")
        if path.startswith("webhook/") or path.startswith("webhook-test/"):
            url = urljoin(f"{self._base_url}/", path)
        else:
            url = f"{self._base_url}/webhook/{path}"
        return await self._request("POST", url, json=data or {}, auth=False)

    async def async_trigger_workflow(
        self,
        workflow_id: str,
        *,
        webhook_path: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Trigger via webhook when known, else API execute, else discover webhook."""
        path = webhook_path
        if not path:
            try:
                detail = await self.async_get_workflow(workflow_id)
                path = detail.webhook_path
            except N8nApiError as err:
                _LOGGER.debug(
                    "Could not load workflow %s for webhook discovery: %s",
                    workflow_id,
                    err,
                )

        if path:
            result = await self.async_trigger_webhook(path, data)
            return {"mode": "webhook", "webhook_path": path, "result": result}

        try:
            result = await self.async_execute_workflow(workflow_id, data)
            return {"mode": "api_execute", "result": result}
        except (N8nNotFoundError, N8nApiError) as err:
            raise N8nApiError(
                "Could not trigger workflow: no webhook path found and API "
                f"execute failed ({err}). Add a Webhook trigger in n8n."
            ) from err
