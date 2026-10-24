"""Switch entities for Vacuula robot vacuums (Gen3 schedule toggle)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
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
    """Set up Vacuula switch entities with dynamic discovery."""
    coordinator: VacuulaCoordinator = entry.runtime_data

    @callback
    def _async_add_new_robots(serials: list[str]) -> None:
        entities: list[SwitchEntity] = []
        for serial in serials:
            robot = coordinator.data.get(serial)
            if robot and robot.robot_type == ROBOT_TYPE_GEN3:
                entities.append(VacuulaScheduleSwitch(coordinator, serial))
        if entities:
            async_add_entities(entities)

    entry.async_on_unload(
        coordinator.register_new_robot_callback(_async_add_new_robots)
    )


class VacuulaScheduleSwitch(VacuulaEntity, SwitchEntity):
    """Switch to enable or disable the robot's internal cleaning schedule (Gen3)."""

    _attr_name = "Schedule"
    _attr_icon = "mdi:calendar-clock"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: VacuulaCoordinator, serial: str) -> None:
        """Initialize the schedule switch."""
        super().__init__(coordinator, serial, "schedule")

    @property
    def is_on(self) -> bool | None:
        """Return True if the robot's internal schedule is enabled."""
        if not self.robot or not self.robot.state:
            return None
        return bool(self.robot.state.get("details", {}).get("isScheduleEnabled", False))

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable the robot's internal schedule."""
        resp = await self.coordinator.client.async_set_schedule_enabled(
            self._serial, True
        )
        await self.coordinator.async_apply_command_response(self._serial, resp)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable the robot's internal schedule."""
        resp = await self.coordinator.client.async_set_schedule_enabled(
            self._serial, False
        )
        await self.coordinator.async_apply_command_response(self._serial, resp)
