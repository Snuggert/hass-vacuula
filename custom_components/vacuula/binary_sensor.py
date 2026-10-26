"""Binary sensor platform for Vacuula robots (Connected, Docked, Charging, Dust Bin Full, Dock Seen)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import VacuulaConfigEntry
from .const import ROBOT_TYPE_GEN3
from .coordinator import VacuulaCoordinator, is_installer_outdated
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
        if robot.robot_type == ROBOT_TYPE_GEN3:
            return bool((robot.state.get("details") or {}).get("isDocked"))
        details = self._gen4_body.get("details") or {}
        return bool(details.get("is_docked") or details.get("isDocked"))


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
            return bool((robot.state.get("details") or {}).get("isCharging"))
        details = self._gen4_body.get("details") or {}
        return bool(details.get("is_charging") or details.get("isCharging"))


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
        if not robot or not robot.state:
            return None
        return bool((robot.state.get("details") or {}).get("dockHasBeenSeen"))


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
        if not robot or not robot.state:
            return None

        if robot.robot_type == ROBOT_TYPE_GEN3:
            alert = str(robot.state.get("alert") or "").lower()
            error = str(robot.state.get("error") or "").lower()
            return "dustbin" in alert or "dustbin" in error

        errors = self._gen4_body.get("errors") or []
        if isinstance(errors, list):
            for err in errors:
                if isinstance(err, dict):
                    code = str(err.get("code") or "").lower()
                    if "dustbin" in code or "bin_full" in code:
                        return True
        return False

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
