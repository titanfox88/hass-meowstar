"""Binary sensors: online status and cat-in-box occupancy."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import MeowStarConfigEntry
from .const import DEVICE_TYPE_LITTER
from .coordinator import MeowStarCoordinator, MeowStarDeviceData
from .device import build_device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MeowStarConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: MeowStarCoordinator = entry.runtime_data
    entities: list[BinarySensorEntity] = []
    for data in coordinator.data.values():
        entities.append(_OnlineSensor(coordinator, data))
        if data.family == DEVICE_TYPE_LITTER:
            entities.append(_CatInBoxSensor(coordinator, data))
    async_add_entities(entities)


class _BaseBinarySensor(BinarySensorEntity):
    def __init__(
        self, coordinator: MeowStarCoordinator, data: MeowStarDeviceData, key: str, name: str
    ) -> None:
        self.coordinator = coordinator
        self.data_ref = data
        self._attr_name = name
        self._attr_unique_id = f"{data.iot_id}_{key}"
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

    def _handle_coordinator_update(self) -> None:
        self.data_ref = self.coordinator.data.get(self.data_ref.iot_id, self.data_ref)
        self.async_write_ha_state()


class _OnlineSensor(_BaseBinarySensor):
    """Device online status (status == 1)."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: MeowStarCoordinator, data: MeowStarDeviceData) -> None:
        super().__init__(coordinator, data, "online", f"{data.nickname} 在线")

    @property
    def is_on(self) -> bool:
        return self.data_ref.online


class _CatInBoxSensor(_BaseBinarySensor):
    """Whether a cat is currently inside the litter box (State_Cat == 1)."""

    _attr_device_class = BinarySensorDeviceClass.OCCUPANCY

    def __init__(self, coordinator: MeowStarCoordinator, data: MeowStarDeviceData) -> None:
        super().__init__(coordinator, data, "cat_in_box", "猫咪在猫砂盆内")

    @property
    def is_on(self) -> bool | None:
        prop = (self.data_ref.property or {}).get("prop") or {}
        state = prop.get("State_Cat")
        if state is None:
            return None
        return state == 1
