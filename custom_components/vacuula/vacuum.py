"""Vacuum platform for Vacuula (Gen3 & Gen4 Neato robots)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.vacuum import (
    StateVacuumEntity,
    VacuumEntityFeature,
)

try:
    from homeassistant.components.vacuum import VacuumActivity
except ImportError:  # pragma: no cover
    from enum import Enum

    class VacuumActivity(str, Enum):  # type: ignore[no-redef]
        """Fallback enum for Home Assistant versions prior to 2023.9."""

        CLEANING = "cleaning"
        DOCKED = "docked"
        IDLE = "idle"
        PAUSED = "paused"
        RETURNING = "returning"
        ERROR = "error"


from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import VacuulaConfigEntry
from .const import (
    ALL_ZONES_OPTION,
    FAN_SPEED_TURBO,
    FAN_SPEEDS_GEN3,
    FAN_SPEEDS_GEN4,
    GEN3_ACTION_DOCKING,
    GEN3_ACTION_NAMES,
    GEN3_ACTION_SUSPENDED_CLEANING,
    GEN3_ACTION_SUSPENDED_EXPLORATION,
    GEN3_STATE_BUSY,
    GEN3_STATE_ERROR,
    GEN3_STATE_IDLE,
    GEN3_STATE_PAUSED,
    ROBOT_TYPE_GEN3,
)
from .coordinator import VacuulaCoordinator, is_installer_outdated
from .entity import VacuulaEntity

SUPPORTED_FEATURES = (
    VacuumEntityFeature.STATE
    | VacuumEntityFeature.START
    | VacuumEntityFeature.PAUSE
    | VacuumEntityFeature.STOP
    | VacuumEntityFeature.RETURN_HOME
    | VacuumEntityFeature.LOCATE
    | VacuumEntityFeature.FAN_SPEED
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VacuulaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Vacuula vacuum entities with dynamic robot discovery."""
    coordinator: VacuulaCoordinator = entry.runtime_data

    @callback
    def _async_add_new_robots(serials: list[str]) -> None:
        async_add_entities(VacuulaVacuumEntity(coordinator, s) for s in serials)

    entry.async_on_unload(
        coordinator.register_new_robot_callback(_async_add_new_robots)
    )


class VacuulaVacuumEntity(VacuulaEntity, StateVacuumEntity):
    """Representation of a Neato robot vacuum managed by Vacuula."""

    _attr_name = None
    _attr_supported_features = SUPPORTED_FEATURES

    def __init__(self, coordinator: VacuulaCoordinator, serial: str) -> None:
        """Initialize the vacuum entity."""
        super().__init__(coordinator, serial, "vacuum")

    @property
    def fan_speed_list(self) -> list[str]:
        """Return the list of available fan speeds for this robot generation."""
        robot = self._robot
        if robot and robot.robot_type == ROBOT_TYPE_GEN3:
            return FAN_SPEEDS_GEN3
        return FAN_SPEEDS_GEN4

    @property
    def activity(self) -> VacuumActivity | None:
        """Return current vacuum activity."""
        robot = self._robot
        if not robot or not robot.state:
            return None

        if robot.robot_type == ROBOT_TYPE_GEN3:
            state_code = robot.state.get("state")
            action_code = robot.state.get("action", 0)
            details = robot.state.get("details") or {}

            if state_code == GEN3_STATE_ERROR or robot.state.get("error"):
                return VacuumActivity.ERROR
            if state_code == GEN3_STATE_PAUSED:
                return VacuumActivity.PAUSED
            if state_code == GEN3_STATE_BUSY:
                if action_code == GEN3_ACTION_DOCKING:
                    return VacuumActivity.RETURNING
                if action_code in (
                    GEN3_ACTION_SUSPENDED_CLEANING,
                    GEN3_ACTION_SUSPENDED_EXPLORATION,
                ):
                    return (
                        VacuumActivity.DOCKED
                        if details.get("isDocked")
                        else VacuumActivity.PAUSED
                    )
                return VacuumActivity.CLEANING
            if state_code == GEN3_STATE_IDLE:
                return (
                    VacuumActivity.DOCKED
                    if details.get("isDocked")
                    else VacuumActivity.IDLE
                )
            return VacuumActivity.IDLE

        # Gen4 FullRobotState mapping
        body = self._gen4_body
        state_str = str(body.get("state", "")).lower()
        action_str = str(body.get("action", "")).lower()
        details = body.get("details") or {}
        errors = body.get("errors")

        if state_str == "error" or (isinstance(errors, list) and len(errors) > 0):
            return VacuumActivity.ERROR
        if state_str == "paused":
            return VacuumActivity.PAUSED
        if state_str == "busy":
            if action_str == "docking":
                return VacuumActivity.RETURNING
            return VacuumActivity.CLEANING
        if details.get("is_docked") or details.get("isDocked"):
            return VacuumActivity.DOCKED
        return VacuumActivity.IDLE

    @property
    def fan_speed(self) -> str | None:
        """Return the currently selected fan speed."""
        robot = self._robot
        return robot.preferred_fan_speed if robot else FAN_SPEED_TURBO

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return generation-specific and map/zone state attributes."""
        robot = self._robot
        if not robot or not robot.state:
            return {}
        zone_names = [str(z.get("name")) for z in robot.zones if z.get("name")]
        base_attrs: dict[str, Any] = {
            "navigation_mode": robot.preferred_navigation_mode,
            "active_map_id": robot.active_map_id,
            "active_map_name": robot.active_map_name,
            "available_zones": zone_names,
            "selected_zone": robot.selected_zone,
        }
        if robot.robot_type == ROBOT_TYPE_GEN3:
            action_code = int(robot.state.get("action", 0))
            base_attrs.update(
                {
                    "action": GEN3_ACTION_NAMES.get(action_code, str(action_code)),
                    "error": robot.state.get("error"),
                    "alert": robot.state.get("alert"),
                }
            )
            if robot.installed_with:
                base_attrs["installed_with"] = robot.installed_with
                min_ver = self.coordinator.server_info.get("min_installer_version")
                base_attrs["outdated_installer"] = is_installer_outdated(
                    robot.installed_with, min_ver
                )
            return base_attrs

        body = self._gen4_body
        base_attrs.update(
            {
                "action": body.get("action"),
                "errors": body.get("errors"),
            }
        )
        return base_attrs

    async def async_start(self) -> None:
        """Start or resume cleaning (full map/house or selected room zone)."""
        robot = self._robot
        if not robot:
            return
        if self.activity == VacuumActivity.PAUSED:
            resp = await self.coordinator.client.async_resume_cleaning(
                self._serial, robot.robot_type
            )
        elif (
            robot.selected_zone
            and robot.selected_zone != ALL_ZONES_OPTION
            and robot.active_map_id
        ):
            zone_ids = robot.resolve_zone_ids([robot.selected_zone])
            resp = await self.coordinator.client.async_start_zone_cleaning(
                self._serial,
                robot.robot_type,
                robot.active_map_id,
                zone_ids,
                fan_speed=robot.preferred_fan_speed,
                navigation_mode=robot.preferred_navigation_mode,
            )
        else:
            resp = await self.coordinator.client.async_start_cleaning(
                self._serial,
                robot.robot_type,
                fan_speed=robot.preferred_fan_speed,
                navigation_mode=robot.preferred_navigation_mode,
                category=robot.preferred_category,
                map_id=robot.active_map_id,
            )
        await self.coordinator.async_apply_command_response(self._serial, resp)

    async def async_pause(self) -> None:
        """Pause the cleaning task."""
        if robot := self._robot:
            resp = await self.coordinator.client.async_pause_cleaning(
                self._serial, robot.robot_type
            )
            await self.coordinator.async_apply_command_response(self._serial, resp)

    async def async_stop(self, **kwargs: Any) -> None:
        """Stop the vacuum cleaner."""
        if robot := self._robot:
            resp = await self.coordinator.client.async_stop_cleaning(
                self._serial, robot.robot_type
            )
            await self.coordinator.async_apply_command_response(self._serial, resp)

    async def async_return_to_base(self, **kwargs: Any) -> None:
        """Set the vacuum cleaner to return to the dock."""
        if robot := self._robot:
            resp = await self.coordinator.client.async_return_to_base(
                self._serial, robot.robot_type
            )
            await self.coordinator.async_apply_command_response(self._serial, resp)

    async def async_locate(self, **kwargs: Any) -> None:
        """Locate the vacuum cleaner."""
        if robot := self._robot:
            await self.coordinator.client.async_locate(self._serial, robot.robot_type)

    async def async_set_fan_speed(self, fan_speed: str, **kwargs: Any) -> None:
        """Set preferred fan speed for the next cleaning run."""
        robot = self._robot
        if robot and fan_speed in self.fan_speed_list:
            robot.preferred_fan_speed = fan_speed
            self.coordinator.async_update_listeners()
