"""DataUpdateCoordinator for the MeowStar (喵星公民) integration."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import MeowStarApiError, MeowStarAuthError, MeowStarClient
from .const import (
    DEFAULT_SCAN_INTERVAL,
    DEVICE_TYPE_FEEDER,
    DEVICE_TYPE_LITTER,
    LITTER_DEVICE_TYPES,
    MIN_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


def classify_device(device: dict[str, Any]) -> str | None:
    """Return DEVICE_TYPE_LITTER / DEVICE_TYPE_FEEDER / None."""
    dtype = (device.get("deviceType") or "").upper()
    name = (device.get("deviceName") or "").upper()
    if dtype.startswith("M") or dtype in LITTER_DEVICE_TYPES or name.startswith("M"):
        return DEVICE_TYPE_LITTER
    if dtype.startswith("W") or dtype in FEEDER_LIKE or name.startswith("WS"):
        return DEVICE_TYPE_FEEDER
    return None


FEEDER_LIKE = {"W4", "W2", "W"}


class MeowStarDeviceData:
    """Merged snapshot for one device."""

    def __init__(self, device: dict[str, Any]) -> None:
        self.device = device
        self.family = classify_device(device)
        self.iot_id: str = device.get("iotId") or ""
        self.property: dict[str, Any] | None = None
        self.work_log: list[dict[str, Any]] | None = None
        self.mqtt: dict[str, Any] | None = None
        self.wsq_static: dict[str, Any] | None = None
        self.w_mqtt: dict[str, Any] | None = None
        self.w_log: list[dict[str, Any]] | None = None

    # convenience -------------------------------------------------------
    @property
    def online(self) -> bool:
        return self.device.get("status") == 1

    @property
    def nickname(self) -> str:
        return self.device.get("nickname") or self.device.get("deviceName") or self.iot_id


class MeowStarCoordinator(DataUpdateCoordinator[dict[str, MeowStarDeviceData]]):
    """Poll all devices once per interval and merge their snapshots."""

    FETCH_TIMEOUT = 120  # 总超时：无论哪个环节挂起，都保证返回并重试

    def __init__(
        self,
        hass: HomeAssistant,
        client: MeowStarClient,
        scan_interval: int,
    ) -> None:
        interval = max(MIN_SCAN_INTERVAL, scan_interval or DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            name="meowstar",
            update_interval=timedelta(seconds=interval),
        )
        self.client = client

    async def _async_update_data(self) -> dict[str, MeowStarDeviceData]:
        try:
            return await asyncio.wait_for(self._fetch_all(), timeout=self.FETCH_TIMEOUT)
        except asyncio.TimeoutError as err:
            raise UpdateFailed("Fetching timed out after 120s (stuck request?)") from err

    async def _fetch_all(self) -> dict[str, MeowStarDeviceData]:
        try:
            await self.client.ensure_token()
            devices = await self.client.get_devices()
        except MeowStarAuthError as err:
            raise UpdateFailed(f"Authentication failed: {err}") from err
        except MeowStarApiError as err:
            raise UpdateFailed(f"API error: {err}") from err

        result: dict[str, MeowStarDeviceData] = {}
        for device in devices:
            data = MeowStarDeviceData(device)
            if not data.iot_id:
                continue
            try:
                if data.family == DEVICE_TYPE_LITTER:
                    data.property = await self.client.get_property(data.iot_id)
                    data.work_log = await self.client.get_today_work_log(data.iot_id)
                    data.mqtt = await self.client.get_mqtt(data.iot_id)
                elif data.family == DEVICE_TYPE_FEEDER:
                    data.wsq_static = await self.client.get_wsq_static(data.iot_id)
                    data.w_mqtt = await self.client.get_w_mqtt(data.iot_id)
                    wlog = await self.client.get_w_log(data.iot_id, page_size=10)
                    data.w_log = (wlog or {}).get("data") if isinstance(wlog, dict) else None
            except MeowStarApiError as err:
                _LOGGER.warning("Failed to update %s: %s", data.nickname, err)
            except MeowStarAuthError as err:
                raise UpdateFailed(f"Authentication failed: {err}") from err
            result[data.iot_id] = data
        return result
