"""Vacuum platform for Vacuula (Gen3 & Gen4 Neato robots)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.vacuum import (
    StateVacuumEntity,
    VacuumActivity,
    VacuumEntityFeature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import VacuulaConfigEntry
from .const import (
    ALL_ZONES_OPTION,
    FAN_SPEED_TURBO,
    FAN_SPEEDS_GEN3,
    FAN_SPEEDS_GEN4,
    GEN3_ACTION_NAMES,
    ROBOT_TYPE_GEN3,
)
from .coordinator import VacuulaCoordinator, is_installer_outdated
from .entity import VacuulaEntity

PARALLEL_UPDATES = 0

SUPPORTED_FEATURES = (
    VacuumEntityFeature.STATE
    | VacuumEntityFeature.START
    | VacuumEntityFeature.PAUSE
    | VacuumEntityFeature.STOP
    | VacuumEntityFeature.RETURN_HOME
    | VacuumEntityFeature.LOCATE
    | VacuumEntityFeature.FAN_SPEED
)

_ACTIVITY_MAP: dict[str, VacuumActivity] = {
    "error": VacuumActivity.ERROR,
    "paused": VacuumActivity.PAUSED,
    "returning": VacuumActivity.RETURNING,
    "cleaning": VacuumActivity.CLEANING,
    "docked": VacuumActivity.DOCKED,
    "idle": VacuumActivity.IDLE,
}


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
        return _ACTIVITY_MAP.get(robot.activity_state, VacuumActivity.IDLE)

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
