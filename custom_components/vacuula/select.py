"""Select entities for Vacuula robot vacuums (Navigation mode)."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import VacuulaConfigEntry
from .const import (
    FAN_SPEED_TURBO,
    GEN3_NAV_MODES,
    GEN4_NAV_MODES,
    NAV_MODE_DEEP,
    ROBOT_TYPE_GEN3,
)
from .coordinator import VacuulaCoordinator
from .entity import VacuulaEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VacuulaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Vacuula select entities with dynamic discovery."""
    coordinator: VacuulaCoordinator = entry.runtime_data

    @callback
    def _async_add_new_robots(serials: list[str]) -> None:
        async_add_entities(
            VacuulaNavigationModeSelect(coordinator, serial) for serial in serials
        )

    entry.async_on_unload(coordinator.register_new_robot_callback(_async_add_new_robots))


class VacuulaNavigationModeSelect(VacuulaEntity, SelectEntity):
    """Select entity for choosing the robot's navigation mode."""

    _attr_name = "Navigation mode"
    _attr_icon = "mdi:map-marker-path"

    def __init__(self, coordinator: VacuulaCoordinator, serial: str) -> None:
        """Initialize the navigation mode select entity."""
        super().__init__(coordinator, serial, "navigation_mode")

    @property
    def options(self) -> list[str]:
        """Return available navigation modes based on robot generation."""
        if self.robot and self.robot.robot_type == ROBOT_TYPE_GEN3:
            return GEN3_NAV_MODES
        return GEN4_NAV_MODES

    @property
    def current_option(self) -> str | None:
        """Return currently selected navigation mode."""
        if not self.robot:
            return None
        return self.robot.preferred_navigation_mode

    async def async_select_option(self, option: str) -> None:
        """Update the preferred navigation mode for subsequent clean runs."""
        if not self.robot:
            return
        self.robot.preferred_navigation_mode = option
        # Gen3 Deep navigation mode requires Turbo fan speed
        if self.robot.robot_type == ROBOT_TYPE_GEN3 and option == NAV_MODE_DEEP:
            self.robot.preferred_fan_speed = FAN_SPEED_TURBO
        self.coordinator.async_update_listeners()
