"""The MeowStar (喵星公民) integration: smart litter box & feeder."""

from __future__ import annotations

import logging

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .api import MeowStarClient
from .const import CONF_MOBILE, DEFAULT_FEED_PORTION, DEFAULT_SCAN_INTERVAL, DOMAIN
from .coordinator import MeowStarCoordinator

PLATFORMS = ("sensor", "binary_sensor", "button", "number")

_LOGGER = logging.getLogger(__name__)

type MeowStarConfigEntry = ConfigEntry  # noqa: F821 (typing helper)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up from a config entry."""
    mobile = entry.data[CONF_MOBILE]
    password = entry.data[CONF_PASSWORD]

    session = aiohttp.ClientSession()
    client = MeowStarClient(session, mobile, password)
    try:
        await client.login()
    except Exception as err:  # noqa: BLE001
        await session.close()
        raise ConfigEntryNotReady(f"Cannot log in to MeowStar: {err}") from err

    scan_interval = entry.options.get("scan_interval", DEFAULT_SCAN_INTERVAL)
    coordinator = MeowStarCoordinator(hass, client, scan_interval)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "client": client,
        "session": session,
        "coordinator": coordinator,
        "feed_portion": DEFAULT_FEED_PORTION,
    }
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload and close the HTTP session."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        store = hass.data[DOMAIN].pop(entry.entry_id)
        await store["session"].close()
    return unload_ok


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Future schema migrations go here."""
    return True
