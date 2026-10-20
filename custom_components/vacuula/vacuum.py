"""Vacuum platform for Vacuula (Gen3 & Gen4 Neato robots)."""
from __future__ import annotations

from typing import Any

from homeassistant.components.vacuum import (
    StateVacuumEntity,
    VacuumActivity,
    VacuumEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import VacuulaConfigEntry
from .const import (
    DOMAIN,
    FAN_SPEED_ECO,
    FAN_SPEED_TURBO,
    FAN_SPEEDS,
    GEN3_MODE_ECO,
    ROBOT_TYPE_GEN3,
)
from .coordinator import VacuulaCoordinator, VacuulaRobotData

SUPPORTED_FEATURES = (
    VacuumEntityFeature.STATE
    | VacuumEntityFeature.START
    | VacuumEntityFeature.PAUSE
    | VacuumEntityFeature.STOP
    | VacuumEntityFeature.RETURN_HOME
    | VacuumEntityFeature.LOCATE
    | VacuumEntityFeature.FAN_SPEED
    | VacuumEntityFeature.BATTERY
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VacuulaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Vacuula vacuum entities from a config entry."""
    coordinator: VacuulaCoordinator = entry.runtime_data
    async_add_entities(
        VacuulaVacuumEntity(coordinator, serial) for serial in coordinator.data
    )


class VacuulaVacuumEntity(CoordinatorEntity[VacuulaCoordinator], StateVacuumEntity):
    """Representation of a Neato robot vacuum managed by Vacuula."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_supported_features = SUPPORTED_FEATURES
    _attr_fan_speed_list = FAN_SPEEDS

    def __init__(self, coordinator: VacuulaCoordinator, serial: str) -> None:
        """Initialize the vacuum entity."""
        super().__init__(coordinator)
        self._serial = serial
        self._attr_unique_id = f"{serial}_vacuum"

    @property
    def _robot(self) -> VacuulaRobotData | None:
        """Return current robot data from coordinator."""
        return self.coordinator.data.get(self._serial)

    @property
    def available(self) -> bool:
        """Return True if the robot is currently connected to Vacuula."""
        return bool(super().available and self._robot and self._robot.connected)

    @property
    def device_info(self) -> DeviceInfo:
        """Return device registry info for this robot."""
        robot = self._robot
        state = robot.state if robot else {}
        meta = state.get("meta", {})
        return DeviceInfo(
            identifiers={(DOMAIN, self._serial)},
            name=robot.name if robot else self._serial,
            manufacturer="Neato Robotics",
            model=meta.get("modelName") or (robot.robot_type if robot else "Neato"),
            sw_version=meta.get("firmware"),
            serial_number=self._serial,
        )

    @property
    def activity(self) -> VacuumActivity | None:
        """Return current vacuum activity."""
        robot = self._robot
        if not robot or not robot.state:
            return None

        if robot.robot_type == ROBOT_TYPE_GEN3:
            state_code = robot.state.get("state")
            action_code = robot.state.get("action")
            details = robot.state.get("details", {})
            if state_code == 1:
                return (
                    VacuumActivity.DOCKED
                    if details.get("isDocked")
                    else VacuumActivity.IDLE
                )
            if state_code == 2:
                return (
                    VacuumActivity.RETURNING
                    if action_code == 6
                    else VacuumActivity.CLEANING
                )
            if state_code == 3:
                return VacuumActivity.PAUSED
            if state_code == 4 or robot.state.get("error"):
                return VacuumActivity.ERROR
            return VacuumActivity.IDLE

        # Gen4 state mapping
        body = robot.state.get("body", robot.state)
        gen4_state = str(body.get("state", "")).lower()
        if "clean" in gen4_state or "busy" in gen4_state:
            return VacuumActivity.CLEANING
        if "pause" in gen4_state:
            return VacuumActivity.PAUSED
        if "return" in gen4_state:
            return VacuumActivity.RETURNING
        if "error" in gen4_state:
            return VacuumActivity.ERROR
        if body.get("docked") or "dock" in gen4_state or "idle" in gen4_state:
            return VacuumActivity.DOCKED
        return VacuumActivity.IDLE

    @property
    def battery_level(self) -> int | None:
        """Return the battery level of the vacuum cleaner."""
        robot = self._robot
        if not robot or not robot.state:
            return None
        if robot.robot_type == ROBOT_TYPE_GEN3:
            charge = robot.state.get("details", {}).get("charge")
            return int(charge) if charge is not None else None
        body = robot.state.get("body", robot.state)
        charge = body.get("battery_level") or body.get("charge")
        return int(charge) if charge is not None else None

    @property
    def fan_speed(self) -> str | None:
        """Return the current fan speed (eco or turbo)."""
        robot = self._robot
        if not robot or not robot.state:
            return FAN_SPEED_TURBO
        if robot.robot_type == ROBOT_TYPE_GEN3:
            mode = robot.state.get("cleaning", {}).get("mode")
            return FAN_SPEED_ECO if mode == GEN3_MODE_ECO else FAN_SPEED_TURBO
        return FAN_SPEED_TURBO

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return generation-specific state attributes."""
        robot = self._robot
        if not robot or not robot.state:
            return {}
        if robot.robot_type == ROBOT_TYPE_GEN3:
            details = robot.state.get("details", {})
            return {
                "is_charging": details.get("isCharging"),
                "is_docked": details.get("isDocked"),
                "is_schedule_enabled": details.get("isScheduleEnabled"),
                "error": robot.state.get("error"),
                "alert": robot.state.get("alert"),
            }
        return {}

    async def async_start(self) -> None:
        """Start or resume cleaning."""
        robot = self._robot
        if not robot:
            return
        if self.activity == VacuumActivity.PAUSED:
            await self.coordinator.client.async_resume_cleaning(
                self._serial, robot.robot_type
            )
        else:
            await self.coordinator.client.async_start_cleaning(
                self._serial, robot.robot_type, self.fan_speed or FAN_SPEED_TURBO
            )
        await self.coordinator.async_request_refresh()

    async def async_pause(self) -> None:
        """Pause the cleaning task."""
        if robot := self._robot:
            await self.coordinator.client.async_pause_cleaning(
                self._serial, robot.robot_type
            )
            await self.coordinator.async_request_refresh()

    async def async_stop(self, **kwargs: Any) -> None:
        """Stop the vacuum cleaner."""
        if robot := self._robot:
            await self.coordinator.client.async_stop_cleaning(
                self._serial, robot.robot_type
            )
            await self.coordinator.async_request_refresh()

    async def async_return_to_base(self, **kwargs: Any) -> None:
        """Set the vacuum cleaner to return to the dock."""
        if robot := self._robot:
            await self.coordinator.client.async_return_to_base(
                self._serial, robot.robot_type
            )
            await self.coordinator.async_request_refresh()

    async def async_locate(self, **kwargs: Any) -> None:
        """Locate the vacuum cleaner."""
        if robot := self._robot:
            await self.coordinator.client.async_locate(
                self._serial, robot.robot_type
            )

    async def async_set_fan_speed(self, fan_speed: str, **kwargs: Any) -> None:
        """Set fan speed (applied on next cleaning start)."""
        if fan_speed in FAN_SPEEDS:
            self._attr_fan_speed = fan_speed
            self.async_write_ha_state()
