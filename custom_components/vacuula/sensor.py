"""Sensor platform for Vacuula robots (Battery, Action, Alert, Last Clean Area/Duration, Total Cleans)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfArea, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import VacuulaConfigEntry
from .const import DOMAIN
from .coordinator import VacuulaCoordinator
from .entity import VacuulaEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VacuulaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Vacuula sensor entities."""
    coordinator: VacuulaCoordinator = entry.runtime_data

    # Add server sensors
    async_add_entities(
        [
            VacuulaServerVersionSensor(coordinator, entry),
            VacuulaConnectedRobotsSensor(coordinator, entry),
        ]
    )

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
        return robot.battery_level if robot else None


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
        return robot.current_action_name


class VacuulaAlertSensor(VacuulaEntity, SensorEntity):
    """Current robot alert or error code sensor."""

    _attr_translation_key = "alert"
    _attr_name = "Alert"
    _attr_icon = "mdi:alert-circle-outline"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: VacuulaCoordinator, serial: str) -> None:
        """Initialize the alert sensor."""
        super().__init__(coordinator, serial, "alert")

    @property
    def native_value(self) -> str:
        """Return active error/alert code or 'none'."""
        robot = self._robot
        return robot.alert_or_error if robot else "none"


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
    def available(self) -> bool:
        """Remain available while server is reachable even if robot is asleep."""
        return bool(self.coordinator.last_update_success and self._robot is not None)

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
    def available(self) -> bool:
        """Remain available while server is reachable even if robot is asleep."""
        return bool(self.coordinator.last_update_success and self._robot is not None)

    @property
    def native_value(self) -> float | None:
        """Return duration of the last cleaning run in minutes."""
        robot = self._robot
        return robot.last_clean_duration_min if robot else None


class VacuulaTotalCleansSensor(VacuulaEntity, SensorEntity):
    """Sensor reporting total historical cleaning runs stored in Vacuula."""

    _attr_name = "Total cleans"
    _attr_icon = "mdi:counter"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: VacuulaCoordinator, serial: str) -> None:
        """Initialize the total cleans sensor."""
        super().__init__(coordinator, serial, "total_cleans")

    @property
    def available(self) -> bool:
        """Remain available while server is reachable even if robot is asleep."""
        return bool(self.coordinator.last_update_success and self._robot is not None)

    @property
    def native_value(self) -> int:
        """Return total number of recorded cleaning runs."""
        robot = self._robot
        return robot.total_runs if robot else 0


class VacuulaServerVersionSensor(CoordinatorEntity[VacuulaCoordinator], SensorEntity):
    """Diagnostic sensor reporting the Vacuula server version."""

    _attr_has_entity_name = True
    _attr_translation_key = "server_version"
    _attr_name = "Server version"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: VacuulaCoordinator,
        entry: VacuulaConfigEntry,
    ) -> None:
        """Initialize the server version sensor."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"server_{entry.entry_id}_server_version"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device registry info for server hub."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"server_{self._entry.entry_id}")},
            name=self._entry.title,
            manufacturer="Vacuula",
            model="Vacuula Server",
            sw_version=self.coordinator.server_info.get("version")
            if self.coordinator.server_info
            else None,
        )

    @property
    def native_value(self) -> str | None:
        """Return server version."""
        return (
            self.coordinator.server_info.get("version")
            if self.coordinator.server_info
            else None
        )


class VacuulaConnectedRobotsSensor(CoordinatorEntity[VacuulaCoordinator], SensorEntity):
    """Sensor reporting the number of connected robots on the Vacuula server."""

    _attr_has_entity_name = True
    _attr_translation_key = "connected_robots"
    _attr_name = "Connected robots"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: VacuulaCoordinator,
        entry: VacuulaConfigEntry,
    ) -> None:
        """Initialize the connected robots sensor."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"server_{entry.entry_id}_connected_robots"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device registry info for server hub."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"server_{self._entry.entry_id}")},
            name=self._entry.title,
            manufacturer="Vacuula",
            model="Vacuula Server",
            sw_version=self.coordinator.server_info.get("version")
            if self.coordinator.server_info
            else None,
        )

    @property
    def native_value(self) -> int:
        """Return number of robots with connected=True."""
        if not self.coordinator.data:
            return 0
        return sum(1 for robot in self.coordinator.data.values() if robot.connected)
