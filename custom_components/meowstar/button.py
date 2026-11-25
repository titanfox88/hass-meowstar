"""Buttons: manual clean / level litter / sterilize / feed."""

from __future__ import annotations

import logging
from typing import Callable

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import MeowStarConfigEntry
from .api import MeowStarApiError
from .const import (
    CMD_ADD_CAT_LITTER,
    CMD_CLEAN_HAND,
    CMD_CLEAR_FOOD,
    CMD_FEED_FOOD,
    CMD_STERILIZATION,
    DEFAULT_FEED_PORTION,
    DEVICE_TYPE_FEEDER,
    DEVICE_TYPE_LITTER,
    DOMAIN,
)
from .coordinator import MeowStarCoordinator, MeowStarDeviceData
from .device import build_device_info

_LOGGER = logging.getLogger(__name__)


def _current_feed_portion(hass: HomeAssistant, entry_id: str) -> int:
    """Read the grams chosen on the feed-portion select."""
    store = hass.data.get(DOMAIN, {}).get(entry_id)
    if store is None:
        return DEFAULT_FEED_PORTION
    return int(store.get("feed_portion", DEFAULT_FEED_PORTION))


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MeowStarConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: MeowStarCoordinator = entry.runtime_data
    entities: list[ButtonEntity] = []
    for data in coordinator.data.values():
        if data.family == DEVICE_TYPE_LITTER:
            entities.extend(
                [
                    _CommandButton(coordinator, data, "clean_now", "一键清理", "mdi:radiobox-marked", CMD_CLEAN_HAND),
                    _CommandButton(coordinator, data, "level_litter", "一键抚平", "mdi:texture-box", CMD_ADD_CAT_LITTER),
                    _CommandButton(coordinator, data, "sterilize", "深度杀菌", "mdi:shield-bacteria", CMD_STERILIZATION),
                ]
            )
        elif data.family == DEVICE_TYPE_FEEDER:
            entities.extend(
                [
                    _CommandButton(
                        coordinator, data, "feed_manual", "手动喂食", "mdi:food-drumstick",
                        CMD_FEED_FOOD,
                        dynamic_value=lambda d=data: _current_feed_portion(hass, entry.entry_id),
                    ),
                    _CommandButton(
                        coordinator, data, "clear_food", "碗内余粮清零", "mdi:restore",
                        CMD_CLEAR_FOOD, value=1,
                    ),
                ]
            )
    async_add_entities(entities)


class _CommandButton(ButtonEntity):
    def __init__(
        self,
        coordinator: MeowStarCoordinator,
        data: MeowStarDeviceData,
        key: str,
        name: str,
        icon: str,
        cmd: str,
        value: int = 0,
        dynamic_value: Callable[[], int] | None = None,
    ) -> None:
        self.coordinator = coordinator
        self.data_ref = data
        self._cmd = cmd
        self._value = value
        self._dynamic_value = dynamic_value
        self._attr_name = name
        self._attr_icon = icon
        self._attr_unique_id = f"{data.iot_id}_{key}"
        self._attr_device_info = build_device_info(data)

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and self.data_ref.online

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            self.coordinator.async_add_listener(self._handle_coordinator_update)
        )

    def _handle_coordinator_update(self) -> None:
        self.data_ref = self.coordinator.data.get(self.data_ref.iot_id, self.data_ref)
        self.async_write_ha_state()

    async def async_press(self) -> None:
        value = self._dynamic_value() if self._dynamic_value is not None else self._value
        try:
            await self.coordinator.client.set_command(
                self.data_ref.iot_id, self._cmd, value
            )
        except MeowStarApiError as err:
            _LOGGER.error("Command %s on %s failed: %s", self._cmd, self.data_ref.nickname, err)
            raise
        await self.coordinator.async_request_refresh()
