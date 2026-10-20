"""Sensor platform for Vacuula robots (Battery, Action, Alert, Last Clean Area/Duration, Total Cleans)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfArea, UnitOfTime
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
                    VacuulaLastCleanAreaSensor(coordinator, serial),
                    VacuulaLastCleanDurationSensor(coordinator, serial),
                    VacuulaTotalCleansSensor(coordinator, serial),
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


class VacuulaLastCleanAreaSensor(VacuulaEntity, SensorEntity):
    """Sensor reporting the cleaned area of the most recent cleaning run."""

    _attr_name = "Last clean area"
    _attr_icon = "mdi:texture-box"
    _attr_device_class = SensorDeviceClass.AREA
    _attr_native_unit_of_measurement = UnitOfArea.SQUARE_METERS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator: VacuulaCoordinator, serial: str) -> None:
        """Initialize the last clean area sensor."""
        super().__init__(coordinator, serial, "last_clean_area")

    @property
    def native_value(self) -> float | None:
        """Return cleaned area in square meters."""
        robot = self._robot
        if not robot or not robot.last_run:
            return None
        area = robot.last_run.get("cleaned_area")
        return round(float(area), 2) if area is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return metadata from the last cleaning run."""
        robot = self._robot
        if not robot or not robot.last_run:
            return {}
        run = robot.last_run
        return {
            "run_id": robot.last_run_id,
            "status": run.get("status"),
            "launched_from": run.get("launched_from"),
            "start_at": run.get("start_at"),
            "end_at": run.get("end_at"),
            "charge_at_start": run.get("run_charge_at_start"),
            "charge_at_end": run.get("run_charge_at_end"),
        }


class VacuulaLastCleanDurationSensor(VacuulaEntity, SensorEntity):
    """Sensor reporting the duration of the most recent cleaning run in minutes."""

    _attr_name = "Last clean duration"
    _attr_icon = "mdi:timer-outline"
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator: VacuulaCoordinator, serial: str) -> None:
        """Initialize the last clean duration sensor."""
        super().__init__(coordinator, serial, "last_clean_duration")

    @property
    def native_value(self) -> float | None:
        """Return duration of the last cleaning run in minutes."""
        robot = self._robot
        if not robot or not robot.last_run:
            return None
        start_str = robot.last_run.get("start_at")
        end_str = robot.last_run.get("end_at")
        if not isinstance(start_str, str) or not isinstance(end_str, str):
            return None
        try:
            start_dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
            end_dt = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
            seconds = max(0.0, (end_dt - start_dt).total_seconds())
            return round(seconds / 60.0, 1)
        except ValueError:
            return None


class VacuulaTotalCleansSensor(VacuulaEntity, SensorEntity):
    """Sensor reporting total historical cleaning runs stored in Vacuula."""

    _attr_name = "Total cleans"
    _attr_icon = "mdi:counter"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(self, coordinator: VacuulaCoordinator, serial: str) -> None:
        """Initialize the total cleans sensor."""
        super().__init__(coordinator, serial, "total_cleans")

    @property
    def native_value(self) -> int:
        """Return total number of recorded cleaning runs."""
        robot = self._robot
        return robot.total_runs if robot else 0
