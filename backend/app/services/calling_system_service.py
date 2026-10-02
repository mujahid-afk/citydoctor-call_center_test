"""HTTP client for the EXISTING internal calling system, reached over VPN.

This is the only module that knows how to talk to that system. The final API
shape is not known yet, so:

* endpoint paths come from env (CALLING_SYSTEM_*_PATH, ``{call_id}`` placeholder);
* request bodies are built in ``build_outbound_body`` (one place to change);
* responses are parsed tolerantly (``call_id`` / ``id`` / ``uniqueid`` / ...).

Replace the bodies of these methods once the real internal API is confirmed.
"""

from __future__ import annotations

import asyncio
import logging
import socket
import time
from typing import Any
from urllib.parse import urlparse

import httpx

from ..config import Settings, get_settings

logger = logging.getLogger(__name__)


class CallingSystemError(Exception):
    """Raised when the internal calling system is unreachable or returns an error."""


class CallingSystemService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    # ------------------------------------------------------------------ plumbing
    @property
    def configured(self) -> bool:
        return bool(self.settings.calling_system_base_url)

    def _url(self, path_template: str, call_id: str | None = None) -> str:
        path = path_template.replace("{call_id}", call_id or "")
        if not path.startswith("/"):
            path = "/" + path
        return f"{self.settings.calling_system_base_url}{path}"

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.settings.calling_system_api_key:
            headers["Authorization"] = f"Bearer {self.settings.calling_system_api_key}"
            headers["X-API-Key"] = self.settings.calling_system_api_key
        return headers

    def auth_headers_for(self, url: str) -> dict[str, str]:
        """Auth headers when ``url`` points at the calling system (used for recording proxying)."""
        base = urlparse(self.settings.calling_system_base_url)
        target = urlparse(url)
        if base.netloc and base.netloc == target.netloc:
            return self._headers()
        return {}

    async def _request(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        if not self.configured:
            raise CallingSystemError("CALLING_SYSTEM_BASE_URL is not configured.")
        try:
            async with httpx.AsyncClient(
                timeout=self.settings.calling_system_timeout,
                verify=self.settings.calling_system_verify_tls,
            ) as client:
                response = await client.request(method, url, headers=self._headers(), **kwargs)
        except httpx.HTTPError as exc:
            raise CallingSystemError(
                f"Could not reach the calling system at {url} (is the VPN up?): {exc}"
            ) from exc
        try:
            data = response.json()
        except ValueError:
            data = {"raw": response.text[:2000]}
        if not isinstance(data, dict):
            data = {"data": data}
        if response.status_code >= 400:
            detail = data.get("detail") or data.get("message") or data.get("error") or response.text[:300]
            raise CallingSystemError(f"Calling system error {response.status_code}: {detail}")
        return data

    # ------------------------------------------------------------------ API
    @staticmethod
    def build_outbound_body(
        *,
        customer_phone: str,
        brand: str,
        agent_id: str | None,
        purpose: str,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Request body for POST {base}{CALLING_SYSTEM_OUTBOUND_PATH}. Adjust to the real API."""
        return {
            "customer_phone": customer_phone,
            "brand": brand,
            "agent_id": agent_id,
            "purpose": purpose,
            "context": context,
        }

    async def start_outbound_call(
        self,
        *,
        customer_phone: str,
        brand: str,
        agent_id: str | None,
        purpose: str,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        body = self.build_outbound_body(
            customer_phone=customer_phone, brand=brand, agent_id=agent_id, purpose=purpose, context=context
        )
        return await self._request("POST", self._url(self.settings.calling_system_outbound_path), json=body)

    async def get_call_status(self, call_id: str) -> dict[str, Any]:
        return await self._request("GET", self._url(self.settings.calling_system_status_path, call_id))

    async def get_call_details(self, call_id: str) -> dict[str, Any]:
        return await self._request("GET", self._url(self.settings.calling_system_details_path, call_id))

    async def fetch_bytes(self, url: str) -> tuple[bytes, str]:
        """Download a file (e.g. a recording on the VPN). Returns (content, content_type)."""
        try:
            async with httpx.AsyncClient(
                timeout=60, verify=self.settings.calling_system_verify_tls, follow_redirects=True
            ) as client:
                response = await client.get(url, headers=self.auth_headers_for(url))
        except httpx.HTTPError as exc:
            raise CallingSystemError(f"Could not download {url}: {exc}") from exc
        if response.status_code >= 400:
            raise CallingSystemError(f"Recording download failed with HTTP {response.status_code}")
        return response.content, response.headers.get("content-type", "audio/mpeg")

    # ------------------------------------------------------------------ diagnostics
    async def check_connectivity(self) -> dict[str, Any]:
        """Best-effort VPN reachability check for the API and the FreePBX host."""
        result: dict[str, Any] = {
            "base_url": self.settings.calling_system_base_url or None,
            "api": None,
            "freepbx_host": self.settings.vpn_internal_freepbx_host or None,
            "freepbx": None,
        }
        if self.configured:
            started = time.perf_counter()
            try:
                data = await self._request("GET", self._url(self.settings.calling_system_health_path))
                result["api"] = {"reachable": True, "latency_ms": _ms(started), "response": data}
            except CallingSystemError as exc:
                result["api"] = {"reachable": False, "error": str(exc)}
        if self.settings.vpn_internal_freepbx_host:
            result["freepbx"] = await _tcp_check(self.settings.vpn_internal_freepbx_host)
        return result


def _ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


async def _tcp_check(host_value: str) -> dict[str, Any]:
    """TCP connect to host[:port] (default 443, then 80)."""
    host, _, port_text = host_value.partition(":")
    ports = [int(port_text)] if port_text.isdigit() else [443, 80]
    for port in ports:
        started = time.perf_counter()
        try:
            _, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=3)
            writer.close()
            return {"reachable": True, "port": port, "latency_ms": _ms(started)}
        except (OSError, asyncio.TimeoutError, socket.gaierror):
            continue
    return {"reachable": False, "ports_tried": ports}
