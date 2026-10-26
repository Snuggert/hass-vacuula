"""Binary sensor platform for Vacuula robots (Connected, Docked, Charging, Dust Bin Full, Dock Seen)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import VacuulaConfigEntry
from .const import DOMAIN, ROBOT_TYPE_GEN3
from .coordinator import VacuulaCoordinator, is_installer_outdated
from .entity import VacuulaEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VacuulaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Vacuula binary sensor entities."""
    coordinator: VacuulaCoordinator = entry.runtime_data

    # Add server binary sensor
    async_add_entities([VacuulaServerStatusBinarySensor(coordinator, entry)])

    @callback
    def _async_add_new_robots(serials: list[str]) -> None:
        entities: list[BinarySensorEntity] = []
        for serial in serials:
            entities.extend(
                [
                    VacuulaConnectedBinarySensor(coordinator, serial),
                    VacuulaDockedBinarySensor(coordinator, serial),
                    VacuulaChargingBinarySensor(coordinator, serial),
                    VacuulaBinFullBinarySensor(coordinator, serial),
                ]
            )
            robot = coordinator.data.get(serial)
            if robot and robot.robot_type == ROBOT_TYPE_GEN3:
                entities.append(VacuulaDockSeenBinarySensor(coordinator, serial))
                entities.append(
                    VacuulaOutdatedInstallerBinarySensor(coordinator, serial)
                )
        async_add_entities(entities)

    entry.async_on_unload(
        coordinator.register_new_robot_callback(_async_add_new_robots)
    )


class VacuulaConnectedBinarySensor(VacuulaEntity, BinarySensorEntity):
    """Diagnostic binary sensor indicating whether the robot is connected to Vacuula."""

    _attr_name = "Connected"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: VacuulaCoordinator, serial: str) -> None:
        """Initialize the connected binary sensor."""
        super().__init__(coordinator, serial, "connected")

    @property
    def available(self) -> bool:
        """Available whenever the Vacuula server itself is reachable."""
        return bool(self.coordinator.last_update_success and self._robot is not None)

    @property
    def is_on(self) -> bool:
        """Return True if the robot is currently connected to Vacuula."""
        return bool(self._robot and self._robot.connected)


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
        return robot.is_docked


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
        return robot.is_charging


class VacuulaDockSeenBinarySensor(VacuulaEntity, BinarySensorEntity):
    """Binary sensor indicating whether a Gen3 robot has seen its charging base."""

    _attr_name = "Dock seen"
    _attr_icon = "mdi:home-map-marker"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: VacuulaCoordinator, serial: str) -> None:
        """Initialize the dock seen binary sensor."""
        super().__init__(coordinator, serial, "dock_seen")

    @property
    def is_on(self) -> bool | None:
        """Return True if the robot has seen its dock."""
        robot = self._robot
        return robot.dock_has_been_seen if robot else None


class VacuulaBinFullBinarySensor(VacuulaEntity, BinarySensorEntity):
    """Binary sensor indicating whether the robot dust bin is full or missing."""

    _attr_name = "Dust bin full"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_icon = "mdi:delete-empty"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: VacuulaCoordinator, serial: str) -> None:
        """Initialize the bin full binary sensor."""
        super().__init__(coordinator, serial, "bin_full")

    @property
    def is_on(self) -> bool | None:
        """Return True if the dust bin is full or missing."""
        robot = self._robot
        return robot.is_bin_full if robot else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return detailed bin status and alert description."""
        robot = self._robot
        if not robot or not robot.state:
            return {}
        alert = (
            robot.state.get("alert") if robot.robot_type == ROBOT_TYPE_GEN3 else None
        )
        return {
            "alert": alert,
            "description": "Empty the robot's dust bin and filter"
            if self.is_on
            else "Normal",
        }


class VacuulaOutdatedInstallerBinarySensor(VacuulaEntity, BinarySensorEntity):
    """Diagnostic binary sensor indicating whether the robot installer needs an update."""

    _attr_translation_key = "installer_outdated"
    _attr_name = "Installer outdated"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: VacuulaCoordinator, serial: str) -> None:
        """Initialize the outdated installer binary sensor."""
        super().__init__(coordinator, serial, "installer_outdated")

    @property
    def available(self) -> bool:
        """Available whenever the Vacuula server itself is reachable."""
        return bool(self.coordinator.last_update_success and self._robot is not None)

    @property
    def is_on(self) -> bool:
        """Return True if the robot was installed with an outdated installer."""
        robot = self._robot
        if not robot or not robot.installed_with:
            return False
        min_ver = self.coordinator.server_info.get("min_installer_version")
        return is_installer_outdated(robot.installed_with, min_ver)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return installer version metadata."""
        robot = self._robot
        attrs: dict[str, Any] = {}
        if robot and robot.installed_with:
            attrs["installed_with"] = robot.installed_with
        min_ver = self.coordinator.server_info.get("min_installer_version")
        if min_ver:
            attrs["minimum_installer_version"] = min_ver
        return attrs


class VacuulaServerStatusBinarySensor(
    CoordinatorEntity[VacuulaCoordinator], BinarySensorEntity
):
    """Diagnostic binary sensor indicating whether the Vacuula server is reachable."""

    _attr_has_entity_name = True
    _attr_translation_key = "server_status"
    _attr_name = "Server status"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: VacuulaCoordinator,
        entry: VacuulaConfigEntry,
    ) -> None:
        """Initialize the server status binary sensor."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"server_{entry.entry_id}_server_status"

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
    def is_on(self) -> bool:
        """Return True if the coordinator last refresh was successful."""
        return bool(self.coordinator.last_update_success)
