"""Binary sensor platform for Vacuula robots (Docked, Charging)."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import VacuulaConfigEntry
from .const import ROBOT_TYPE_GEN3
from .coordinator import VacuulaCoordinator
from .entity import VacuulaEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VacuulaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Vacuula binary sensor entities."""
    coordinator: VacuulaCoordinator = entry.runtime_data

    @callback
    def _async_add_new_robots(serials: list[str]) -> None:
        entities: list[BinarySensorEntity] = []
        for serial in serials:
            entities.extend(
                [
                    VacuulaDockedBinarySensor(coordinator, serial),
                    VacuulaChargingBinarySensor(coordinator, serial),
                ]
            )
        async_add_entities(entities)

    entry.async_on_unload(
        coordinator.register_new_robot_callback(_async_add_new_robots)
    )


class VacuulaDockedBinarySensor(VacuulaEntity, BinarySensorEntity):
    """Binary sensor indicating whether the robot is on its dock."""

    _attr_name = "Docked"
    _attr_device_class = BinarySensorDeviceClass.PLUG

    def __init__(self, coordinator: VacuulaCoordinator, serial: str) -> None:
        """Initialize the docked binary sensor."""
        super().__init__(coordinator, serial, "docked")

    @property
    def is_on(self) -> bool | None:
        """Return True if the robot is docked."""
        robot = self._robot
        if not robot or not robot.state:
            return None
        if robot.robot_type == ROBOT_TYPE_GEN3:
            return bool(robot.state.get("details", {}).get("isDocked"))
        return bool(self._gen4_body.get("details", {}).get("is_docked"))


class VacuulaChargingBinarySensor(VacuulaEntity, BinarySensorEntity):
    """Binary sensor indicating whether the robot battery is charging."""

    _attr_name = "Charging"
    _attr_device_class = BinarySensorDeviceClass.BATTERY_CHARGING

    def __init__(self, coordinator: VacuulaCoordinator, serial: str) -> None:
        """Initialize the charging binary sensor."""
        super().__init__(coordinator, serial, "charging")

    @property
    def is_on(self) -> bool | None:
        """Return True if the robot is charging."""
        robot = self._robot
        if not robot or not robot.state:
            return None
        if robot.robot_type == ROBOT_TYPE_GEN3:
            return bool(robot.state.get("details", {}).get("isCharging"))
        return bool(self._gen4_body.get("details", {}).get("is_charging"))
