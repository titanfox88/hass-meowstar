"""Async API client for the MeowStar (喵星公民) cloud.

Reverse-engineered from the official H5 app backend
(https://xiaolong618.com/api_h5/api/v1.*). Authentication is a plain
bearer-style ``token`` request header without signatures or encryption.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import aiohttp

from .const import (
    API_URL_DEVICE_MY,
    API_URL_GET_PROPERTY,
    API_URL_LOGIN,
    API_URL_MQTT,
    API_URL_SET_COMMAND,
    API_URL_TODAY_WORK_LOG,
    API_URL_W_LOG,
    API_URL_W_MQTT,
    API_URL_WSQ_STATIC,
)

_LOGGER = logging.getLogger(__name__)


class MeowStarAuthError(Exception):
    """Raised when login fails or the token is invalid."""


class MeowStarApiError(Exception):
    """Raised for API errors other than auth problems."""


class MeowStarClient:
    """Thin async wrapper around the MeowStar cloud API."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        mobile: str,
        password: str,
    ) -> None:
        self._session = session
        self._mobile = mobile
        self._password = password
        self._token: str | None = None

    @property
    def token(self) -> str | None:
        return self._token

    # ------------------------------------------------------------------
    # Low level helpers
    # ------------------------------------------------------------------

    async def _request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        retry_auth: bool = True,
    ) -> Any:
        headers = {"Host": "xiaolong618.com"}
        if self._token:
            headers["token"] = self._token
        _t0 = time.monotonic()
        _LOGGER.debug("--> %s %s params=%s", method, url.replace("https://xiaolong618.com", ""), params or {})
        async with self._session.request(
            method, url, params=params, json=json, headers=headers, timeout=aiohttp.ClientTimeout(total=30)
        ) as resp:
            data = await resp.json(content_type=None)
            code = data.get("code") if isinstance(data, dict) else None
            _LOGGER.debug("<-- %s %s code=%s in %.2fs", method, url.replace("https://xiaolong618.com", ""), code, time.monotonic() - _t0)
            if code == 401:
                if retry_auth:
                    _LOGGER.debug("Token expired, re-logging in")
                    await self.login()
                    return await self._request(
                        method, url, params=params, json=json, retry_auth=False
                    )
                raise MeowStarAuthError(f"Auth failed after re-login: {data}")
            if code != 200:
                raise MeowStarApiError(f"API error {code}: {data.get('msg') or data}")
            return data.get("data")

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    async def login(self) -> str:
        """Log in and store the token. Raises MeowStarAuthError on failure."""
        payload = {
            "mobile": self._mobile,
            "pwd": self._password,
            "type": "pwd",
            "deviceBrand": "",
            "deviceModel": "",
        }
        async with self._session.post(
            API_URL_LOGIN,
            json=payload,
            headers={"Host": "xiaolong618.com"},
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            data = await resp.json(content_type=None)
        if data.get("code") != 200 or not data.get("data"):
            raise MeowStarAuthError(f"Login failed: {data.get('msg') or data}")
        token = data["data"].get("token")
        if not token:
            raise MeowStarAuthError("Login response missing token")
        self._token = token
        _LOGGER.debug("Logged in as %s", self._mobile)
        return token

    async def ensure_token(self) -> None:
        """Login if we do not have a token yet."""
        if not self._token:
            await self.login()

    # ------------------------------------------------------------------
    # Devices
    # ------------------------------------------------------------------

    async def get_devices(self) -> list[dict[str, Any]]:
        """Return the raw device list."""
        return await self._request("GET", API_URL_DEVICE_MY) or []

    async def get_property(self, iot_id: str) -> dict[str, Any]:
        """Full property snapshot for M-series litter boxes."""
        return await self._request("GET", API_URL_GET_PROPERTY, params={"id": iot_id})

    async def get_mqtt(self, iot_id: str) -> dict[str, Any]:
        """Realtime snapshot for M-series litter boxes (catList = per-cat weights)."""
        return await self._request("GET", API_URL_MQTT, params={"id": iot_id})

    async def get_today_work_log(self, iot_id: str, limit: int = 5) -> list[dict[str, Any]]:
        """Today's work log (toilet events + clean/sterilize actions)."""
        return (
            await self._request(
                "GET",
                API_URL_TODAY_WORK_LOG,
                params={"iot_id": iot_id, "limit": limit, "lastId": ""},
            )
            or []
        )

    async def get_wsq_static(self, iot_id: str) -> dict[str, Any]:
        """Static/statistics snapshot for W-series feeders."""
        return await self._request("GET", API_URL_WSQ_STATIC, params={"iotId": iot_id})

    async def get_w_mqtt(self, iot_id: str) -> dict[str, Any]:
        """Realtime snapshot for W-series feeders (long-poll endpoint, one shot)."""
        return await self._request("GET", API_URL_W_MQTT, params={"id": iot_id})

    async def get_w_log(self, iot_id: str, page: int = 1, page_size: int = 10) -> dict[str, Any] | None:
        """Paged work log for W-series feeders."""
        return await self._request(
            "GET",
            API_URL_W_LOG,
            params={
                "lastLogId": "",
                "lastLogTimeStr": "",
                "page": page,
                "pageSize": page_size,
                "selectType": 3,
                "id": iot_id,
            },
        )

    # ------------------------------------------------------------------
    # Control
    # ------------------------------------------------------------------

    async def set_command(self, iot_id: str, cmd: str, value: int = 0) -> Any:
        """Send a device command.

        Known commands: Clean_Hand (clean now), Add_CatLitter (level litter),
        Sterilization (deep sterilize), FeedFood (manual feed, value = grams).
        """
        payload = {"id": iot_id, "title": "state", "v": value, "cmd": cmd}
        return await self._request("POST", API_URL_SET_COMMAND, json=payload)
