"""Number: manual feed portion in grams (linear 10-120, step 10, slider)."""

from __future__ import annotations

import logging

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import MeowStarConfigEntry
from .const import (
    DEFAULT_FEED_PORTION,
    DEVICE_TYPE_FEEDER,
    DOMAIN,
    FEED_PORTION_MAX,
    FEED_PORTION_MIN,
    FEED_PORTION_STEP,
)
from .coordinator import MeowStarCoordinator, MeowStarDeviceData
from .device import build_device_info

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MeowStarConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: MeowStarCoordinator = entry.runtime_data
    entities: list[NumberEntity] = []
    for data in coordinator.data.values():
        if data.family == DEVICE_TYPE_FEEDER:
            entities.append(_FeedPortionNumber(hass, coordinator, data))
    async_add_entities(entities)


class _FeedPortionNumber(NumberEntity, RestoreEntity):
    """Manual feed portion (grams), linear 10-120, restored across restarts."""

    _attr_icon = "mdi:scale-balance"
    _attr_mode = NumberMode.SLIDER
    _attr_native_min_value = FEED_PORTION_MIN
    _attr_native_max_value = FEED_PORTION_MAX
    _attr_native_step = FEED_PORTION_STEP
    _attr_native_unit_of_measurement = "g"
    _attr_suggested_display_precision = 0

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: MeowStarCoordinator,
        data: MeowStarDeviceData,
    ) -> None:
        self._hass = hass
        self.coordinator = coordinator
        self.data_ref = data
        self._attr_name = "手动喂食克数"
        self._attr_unique_id = f"{data.iot_id}_feed_portion"
        self._attr_native_value = float(DEFAULT_FEED_PORTION)
        self._attr_device_info = build_device_info(data)

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # 订阅 coordinator：每次轮询成功后刷新本实体状态
        self.async_on_remove(
            self.coordinator.async_add_listener(self._handle_coordinator_update)
        )
        last_state = await self.async_get_last_state()
        if last_state is not None:
            try:
                value = float(last_state.state)
            except (TypeError, ValueError):
                value = None
            if value is not None:
                snapped = round(value / FEED_PORTION_STEP) * FEED_PORTION_STEP
                self._attr_native_value = float(
                    min(max(snapped, FEED_PORTION_MIN), FEED_PORTION_MAX)
                )
        self._store()

    def _handle_coordinator_update(self) -> None:
        self.data_ref = self.coordinator.data.get(self.data_ref.iot_id, self.data_ref)
        self.async_write_ha_state()

    def _store(self) -> None:
        """Share the chosen grams with the feed button."""
        store = self._hass.data.get(DOMAIN, {}).get(
            self.coordinator.config_entry.entry_id
        )
        if store is not None and self._attr_native_value is not None:
            store["feed_portion"] = int(round(self._attr_native_value))

    async def async_set_native_value(self, value: float) -> None:
        self._attr_native_value = float(value)
        self._store()
        self.async_write_ha_state()