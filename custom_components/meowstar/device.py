"""Shared helpers for MeowStar entities."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN, MANUFACTURER
from .coordinator import MeowStarDeviceData


def build_device_info(data: MeowStarDeviceData) -> DeviceInfo:
    """DeviceInfo for one physical MeowStar device."""
    device = data.device
    prop = data.property or {}
    hw = None
    mcu = device.get("versionMcu")
    if data.family == "feeder":
        mqtt = data.w_mqtt or {}
        basic = mqtt.get("basicData") or {}
        hw = basic.get("Version_Hardware")
        mcu = mcu or basic.get("Version_Hardware")
    else:
        hw = (data.property or {}).get("prop", {}).get("Version_Hardware") if isinstance(prop, dict) else None
        propd = prop.get("prop") if isinstance(prop, dict) else None
        if isinstance(propd, dict):
            hw = propd.get("Version_Hardware")
    return DeviceInfo(
        identifiers={(DOMAIN, data.iot_id)},
        name=data.nickname,
        manufacturer=MANUFACTURER,
        model=f"{device.get('deviceName') or ''} ({device.get('deviceType') or ''})".strip(),
        sw_version=hw or mcu,
        serial_number=device.get("sn"),
    )
