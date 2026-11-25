"""Sensors for MeowStar devices: litter boxes and feeders."""

from __future__ import annotations

import json
import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import MeowStarConfigEntry
from .const import DEVICE_TYPE_FEEDER, DEVICE_TYPE_LITTER
from .coordinator import MeowStarCoordinator, MeowStarDeviceData
from .device import build_device_info

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MeowStarConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: MeowStarCoordinator = entry.runtime_data
    entities: list[SensorEntity] = []
    for data in coordinator.data.values():
        if data.family == DEVICE_TYPE_LITTER:
            entities.extend(_litter_sensors(coordinator, data))
        elif data.family == DEVICE_TYPE_FEEDER:
            entities.extend(_feeder_sensors(coordinator, data))
    async_add_entities(entities)

    # 猫体重实体是动态的：工作日志里出现新猫时追加（跨天后第一天上厕所才会出现）
    known_cats: set[tuple[str, str]] = set()

    def _sync_cat_sensors() -> None:
        new_entities: list[SensorEntity] = []
        for data in coordinator.data.values():
            if data.family != DEVICE_TYPE_LITTER:
                continue
            for cat in _cats_from_device(data):
                key = (data.iot_id, cat["nickname"])
                if key not in known_cats:
                    known_cats.add(key)
                    new_entities.append(_CatWeightSensor(coordinator, data, cat))
        if new_entities:
            async_add_entities(new_entities)

    _sync_cat_sensors()
    entry.async_on_unload(coordinator.async_add_listener(_sync_cat_sensors))


def _litter_sensors(
    coordinator: MeowStarCoordinator, data: MeowStarDeviceData
) -> list[SensorEntity]:
    sensors: list[SensorEntity] = [
        _LitterPropSensor(coordinator, data, "litter_remaining", "猫砂剩余量", "%", "prop", "Weight_Litter_Percent", "measurement"),
        _LitterPropSensor(coordinator, data, "bin_usage", "集便仓使用量", "%", "prop", "Height", "measurement"),
        _LitterPropSensor(coordinator, data, "litter_weight", "猫砂重量", "kg", "clean_weight", "WeightLitter", "measurement"),
        _LitterPropSensor(coordinator, data, "chamber_temperature", "舱内温度", "°C", "prop", "Temperature", "measurement", device_class="temperature"),
        _LitterCountSensor(coordinator, data, "clean_today", "今日清理次数", ("clean", "today")),
        _LitterCountSensor(coordinator, data, "clean_yesterday", "昨日清理次数", ("clean", "yesterday")),
        _LitterCountSensor(coordinator, data, "clean_total", "累计清理次数", ("clean", "total")),
        _LitterCountSensor(coordinator, data, "toilet_today", "今日如厕次数", ("toilet", "today_times")),
        _LitterCountSensor(coordinator, data, "toilet_yesterday", "昨日如厕次数", ("toilet", "yesterday_times")),
        _LitterCountSensor(coordinator, data, "toilet_avg_duration", "今日平均如厕时长", ("toilet", "today_avg"), "s"),
        _LitterLastEventSensor(coordinator, data),
    ]
    # 猫体重实体由 _sync_cat_sensors 动态管理（见 async_setup_entry）
    return sensors


def _feeder_sensors(
    coordinator: MeowStarCoordinator, data: MeowStarDeviceData
) -> list[SensorEntity]:
    return [
        _FeederSensor(coordinator, data, "bowl_food", "碗内余粮", "g", ("basicData", "Weight_Food"), "measurement"),
        _FeederSensor(coordinator, data, "fed_today", "今日出粮", "g", ("daystat", "feedTotalDay", "totalWeight"), "measurement"),
        _FeederSensor(coordinator, data, "eaten_today", "今日进食", "g", ("daystat", "eatTotalDay", "totalWeight"), "measurement"),
        _FeederSensor(coordinator, data, "eaten_today_count", "今日进食次数", None, ("daystat", "eatTotalDay", "totalCnt")),
        _FeederSensor(coordinator, data, "eaten_yesterday", "昨日进食", "g", ("daystat", "eatTotalYesterday", "totalWeight"), "measurement"),
        _FeederStaticSensor(coordinator, data, "fed_total", "累计喂食", "g", "sumOutRealWeight", "measurement"),
        _FeederStaticSensor(coordinator, data, "expenses_total", "累计花销", "元", "sumExpenses", "total_money", precision=2),
        _FeederStaticSensor(coordinator, data, "expenses_today", "今日花销", "元", "nowDaySumExpenses", "total_money", precision=2),
        _FeederSensor(coordinator, data, "barn_temperature", "粮仓温度", "°C", ("hotBoardInfo", "Temp"), "measurement", device_class="temperature"),
        _FeederSensor(coordinator, data, "barn_humidity", "粮仓湿度", "%", ("hotBoardInfo", "Humi"), "measurement", device_class="humidity"),
    ]


def _cats_from_device(data: MeowStarDeviceData) -> list[dict[str, Any]]:
    """Cats with realtime weight from device_mqtt catList, plus per-cat stats
    from today's work log (count / latest time / duration / excreta)."""
    cat_list = (data.mqtt or {}).get("catList") or {}
    cats: dict[str, dict[str, Any]] = {}
    for _slot, cat in cat_list.items():
        if not isinstance(cat, dict):
            continue
        nick = (cat.get("name") or "").strip()
        weight = cat.get("Weight")
        if not nick or nick in ("未知", "unknown") or not weight:
            continue
        cats[nick] = {
            "nickname": nick,
            # 云端 catList.Weight 单位为 0.01kg（如 369 -> 3.69kg）
            "weight": weight / 100 if weight > 10 else weight,
            "count": None,
            "time": None,
            "duration": None,
            "excreta": None,
        }
    seen_cats: set[str] = set()  # work log is newest-first: keep each cat first hit (its latest visit) only
    for group in data.work_log or []:
        nick = group.get("nickname")
        if not nick or nick in ("未知", "unknown") or nick not in cats:
            continue
        if nick in seen_cats:
            continue
        seen_cats.add(nick)
        info = group.get("taskRecordInfo") or {}
        cat = cats[nick]
        cat["count"] = group.get("currentCount", cat.get("count"))
        cat["time"] = f"{group.get('day','')} {group.get('time','')}".strip()
        cat["duration"] = info.get("duration", cat.get("duration"))
        cat["excreta"] = info.get("cat_excreta", cat.get("excreta"))
    return list(cats.values())


class _BaseSensor(SensorEntity):
    """Common plumbing for MeowStar sensors."""

    _attr_has_entity_name = False

    def __init__(
        self,
        coordinator: MeowStarCoordinator,
        data: MeowStarDeviceData,
        key: str,
        name: str,
    ) -> None:
        self.coordinator = coordinator
        self.data_ref = data
        self._key = key
        self._attr_name = name
        self._attr_unique_id = f"{data.iot_id}_{key}"
        self._attr_device_info = build_device_info(data)

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and self.data_ref.online

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # 订阅 coordinator：每次轮询成功后刷新本实体状态
        self.async_on_remove(
            self.coordinator.async_add_listener(self._handle_coordinator_update)
        )

    def _handle_coordinator_update(self) -> None:
        self.data_ref = self.coordinator.data.get(self.data_ref.iot_id, self.data_ref)
        self.async_write_ha_state()


def _dig(source: Any, *keys: str) -> Any:
    cur = source
    for key in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


class _LitterPropSensor(_BaseSensor):
    """Scalar value out of the M-series property snapshot."""

    def __init__(
        self,
        coordinator: MeowStarCoordinator,
        data: MeowStarDeviceData,
        key: str,
        name: str,
        unit: str | None,
        root: str,
        prop_key: str,
        state_class: str | None,
        device_class: str | None = None,
    ) -> None:
        super().__init__(coordinator, data, key, name)
        self._root = root
        self._prop_key = prop_key
        self._attr_native_unit_of_measurement = unit
        self._attr_state_class = state_class
        self._attr_device_class = device_class

    @property
    def native_value(self) -> Any:
        prop = self.data_ref.property or {}
        if self._root == "clean_weight":
            clean = prop.get("Clean")
            if isinstance(clean, str):
                try:
                    clean = json.loads(clean)
                except ValueError:
                    return None
            return _dig(clean, self._prop_key)
        propd = prop.get("prop") or {}
        return _dig(propd, self._prop_key)


class _LitterCountSensor(_BaseSensor):
    """Counters in get_property (clean.*, toilet.*)."""

    def __init__(
        self,
        coordinator: MeowStarCoordinator,
        data: MeowStarDeviceData,
        key: str,
        name: str,
        path: tuple[str, str],
        unit: str | None = None,
    ) -> None:
        super().__init__(coordinator, data, key, name)
        self._path = path
        self._attr_native_unit_of_measurement = unit

    @property
    def native_value(self) -> Any:
        return _dig(self.data_ref.property, *self._path)


class _LitterLastEventSensor(_BaseSensor):
    """Latest toilet event with rich attributes."""

    def __init__(self, coordinator: MeowStarCoordinator, data: MeowStarDeviceData) -> None:
        super().__init__(coordinator, data, "last_toilet_event", "最近如厕")

    @property
    def native_value(self) -> Any:
        for group in self.data_ref.work_log or []:
            if group.get("nickname") and group.get("nickname") not in ("未知", "unknown"):
                return f"{group.get('nickname')} {group.get('time','')}"
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        for group in self.data_ref.work_log or []:
            if group.get("nickname") and group.get("nickname") not in ("未知", "unknown"):
                info = group.get("taskRecordInfo") or {}
                return {
                    "猫咪": group.get("nickname"),
                    "时间": f"{group.get('day','')} {group.get('time','')}".strip(),
                    "停留时长(秒)": info.get("duration"),
                    "体重(kg)": (info.get("cat_weight") or 0) / 100 if info.get("cat_weight") else None,
                    "排泄物重量(g)": info.get("cat_excreta"),
                    "当日次数": group.get("currentCount"),
                    "备注": info.get("remark"),
                }
        return {}


class _CatWeightSensor(_BaseSensor):
    """Latest weight of one cat."""

    def __init__(
        self, coordinator: MeowStarCoordinator, data: MeowStarDeviceData, cat: dict[str, Any]
    ) -> None:
        nick = cat["nickname"]
        super().__init__(coordinator, data, f"weight_{nick}", f"{nick} 体重")
        self._nick = nick
        self._attr_native_unit_of_measurement = "kg"
        self._attr_state_class = "measurement"
        self._attr_icon = "mdi:cat"

    @property
    def native_value(self) -> Any:
        for cat in _cats_from_device(self.data_ref):
            if cat["nickname"] == self._nick:
                return round(cat["weight"], 2)
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        for cat in _cats_from_device(self.data_ref):
            if cat["nickname"] == self._nick:
                return {
                    "最近如厕时间": cat.get("time"),
                    "停留时长(秒)": cat.get("duration"),
                    "当日如厕次数": cat.get("count"),
                    "排泄物重量(g)": cat.get("excreta"),
                }
        return {}


class _FeederSensor(_BaseSensor):
    """Value out of the W-series realtime (device_w_mqtt) snapshot."""

    def __init__(
        self,
        coordinator: MeowStarCoordinator,
        data: MeowStarDeviceData,
        key: str,
        name: str,
        unit: str | None,
        path: tuple[str, ...],
        state_class: str | None = None,
        device_class: str | None = None,
    ) -> None:
        super().__init__(coordinator, data, key, name)
        self._path = path
        self._attr_native_unit_of_measurement = unit
        self._attr_state_class = state_class
        self._attr_device_class = device_class

    @property
    def native_value(self) -> Any:
        return _dig(self.data_ref.w_mqtt, *self._path)


class _FeederStaticSensor(_BaseSensor):
    """Value out of getDeviceWsqStaticData."""

    def __init__(
        self,
        coordinator: MeowStarCoordinator,
        data: MeowStarDeviceData,
        key: str,
        name: str,
        unit: str | None,
        field: str,
        state_class: str | None = None,
        precision: int | None = None,
    ) -> None:
        super().__init__(coordinator, data, key, name)
        self._field = field
        self._attr_native_unit_of_measurement = unit
        self._attr_state_class = state_class
        self._precision = precision

    @property
    def native_value(self) -> Any:
        val = _dig(self.data_ref.wsq_static, self._field)
        if val is not None and self._precision is not None:
            val = round(float(val), self._precision)
        return val
