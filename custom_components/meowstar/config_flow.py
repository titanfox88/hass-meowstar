"""Config flow for the MeowStar (喵星公民) integration."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD
from homeassistant.core import HomeAssistant, callback

from .api import MeowStarApiError, MeowStarAuthError, MeowStarClient
from .const import CONF_MOBILE, DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_MOBILE): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


async def _validate_login(hass: HomeAssistant, mobile: str, password: str):
    """Try to log in; returns the client on success."""
    async with aiohttp.ClientSession() as session:
        client = MeowStarClient(session, mobile, password)
        await client.login()
        return client


class MeowStarConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the MeowStar config flow."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                client = await _validate_login(
                    self.hass, user_input[CONF_MOBILE], user_input[CONF_PASSWORD]
                )
            except MeowStarAuthError:
                errors["base"] = "invalid_auth"
            except (aiohttp.ClientError, TimeoutError, MeowStarApiError):
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error during login")
                errors["base"] = "unknown"
            else:
                # guard against duplicate accounts
                await self.async_set_unique_id(user_input[CONF_MOBILE])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"喵星公民 {user_input[CONF_MOBILE][:3]}****{user_input[CONF_MOBILE][-4:]}",
                    data=user_input,
                    options={"scan_interval": DEFAULT_SCAN_INTERVAL},
                )

        return self.async_show_form(step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> MeowStarOptionsFlow:
        return MeowStarOptionsFlow(config_entry)


class MeowStarOptionsFlow(config_entries.OptionsFlow):
    """Options flow: only the scan interval."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self.config_entry.options.get("scan_interval", DEFAULT_SCAN_INTERVAL)
        schema = vol.Schema(
            {
                vol.Required(
                    "scan_interval", description={"suggested_value": current}
                ): int,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
