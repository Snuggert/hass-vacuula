"""Sensor platform for Vacuula robots (Battery, Action, Alert/Error)."""
from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import VacuulaConfigEntry
from .const import GEN3_ACTION_NAMES, ROBOT_TYPE_GEN3
from .coordinator import VacuulaCoordinator
from .entity import VacuulaEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VacuulaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Vacuula sensor entities."""
    coordinator: VacuulaCoordinator = entry.runtime_data

    @callback
    def _async_add_new_robots(serials: list[str]) -> None:
        entities: list[SensorEntity] = []
        for serial in serials:
            entities.extend(
                [
                    VacuulaBatterySensor(coordinator, serial),
                    VacuulaActionSensor(coordinator, serial),
                    VacuulaAlertSensor(coordinator, serial),
                ]
            )
        async_add_entities(entities)

    entry.async_on_unload(
        coordinator.register_new_robot_callback(_async_add_new_robots)
    )


class VacuulaBatterySensor(VacuulaEntity, SensorEntity):
    """Battery level sensor for a Neato robot."""

    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: VacuulaCoordinator, serial: str) -> None:
        """Initialize the battery sensor."""
        super().__init__(coordinator, serial, "battery")

    @property
    def native_value(self) -> int | None:
        """Return battery percentage."""
        robot = self._robot
        if not robot or not robot.state:
            return None
        if robot.robot_type == ROBOT_TYPE_GEN3:
            charge = robot.state.get("details", {}).get("charge")
            return int(charge) if charge is not None else None
        details = self._gen4_body.get("details", {})
        charge = details.get("charge")
        return int(charge) if charge is not None else None


class VacuulaActionSensor(VacuulaEntity, SensorEntity):
    """Current robot action sensor."""

    _attr_translation_key = "action"
    _attr_name = "Action"
    _attr_icon = "mdi:robot-vacuum"

    def __init__(self, coordinator: VacuulaCoordinator, serial: str) -> None:
        """Initialize the action sensor."""
        super().__init__(coordinator, serial, "action")

    @property
    def native_value(self) -> str | None:
        """Return human-readable action string."""
        robot = self._robot
        if not robot or not robot.state:
            return None
        if robot.robot_type == ROBOT_TYPE_GEN3:
            action_code = int(robot.state.get("action", 0))
            return GEN3_ACTION_NAMES.get(action_code, f"unknown_{action_code}")
        return str(self._gen4_body.get("action", "idle")).lower()


class VacuulaAlertSensor(VacuulaEntity, SensorEntity):
    """Current robot alert or error code sensor."""

    _attr_translation_key = "alert"
    _attr_name = "Alert"
    _attr_icon = "mdi:alert-circle-outline"

    def __init__(self, coordinator: VacuulaCoordinator, serial: str) -> None:
        """Initialize the alert sensor."""
        super().__init__(coordinator, serial, "alert")

    @property
    def native_value(self) -> str:
        """Return active error/alert code or 'none'."""
        robot = self._robot
        if not robot or not robot.state:
            return "none"
        if robot.robot_type == ROBOT_TYPE_GEN3:
            return str(
                robot.state.get("error") or robot.state.get("alert") or "none"
            )
        errors = self._gen4_body.get("errors")
        if isinstance(errors, list) and errors:
            first = errors[0]
            if isinstance(first, dict) and first.get("code"):
                return str(first["code"])
        return "none"
