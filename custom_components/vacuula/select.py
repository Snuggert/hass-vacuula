"""Select entities for Vacuula robot vacuums (Navigation mode, Cleaning category, Target zone)."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import VacuulaConfigEntry
from .const import (
    ALL_ZONES_OPTION,
    CLEAN_CATEGORY_HOUSE,
    CLEAN_CATEGORY_MAP,
    FAN_SPEED_TURBO,
    GEN3_CATEGORY_HOUSE,
    GEN3_CATEGORY_MAP,
    GEN3_CLEAN_CATEGORIES,
    GEN3_NAV_MODES,
    GEN4_NAV_MODES,
    NAV_MODE_DEEP,
    ROBOT_TYPE_GEN3,
)
from .coordinator import VacuulaCoordinator
from .entity import VacuulaEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VacuulaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Vacuula select entities with dynamic discovery."""
    coordinator: VacuulaCoordinator = entry.runtime_data

    @callback
    def _async_add_new_robots(serials: list[str]) -> None:
        entities: list[SelectEntity] = []
        for serial in serials:
            entities.append(VacuulaNavigationModeSelect(coordinator, serial))
            entities.append(VacuulaTargetZoneSelect(coordinator, serial))
            entities.append(VacuulaSelectedMapSelect(coordinator, serial))
            robot = coordinator.data.get(serial)
            if robot and robot.robot_type == ROBOT_TYPE_GEN3:
                entities.append(VacuulaCleaningCategorySelect(coordinator, serial))
        async_add_entities(entities)

    entry.async_on_unload(
        coordinator.register_new_robot_callback(_async_add_new_robots)
    )


class VacuulaNavigationModeSelect(VacuulaEntity, SelectEntity):
    """Select entity for choosing the robot's navigation mode."""

    _attr_name = "Navigation mode"
    _attr_icon = "mdi:map-marker-path"
    _attr_entity_category = EntityCategory.CONFIG

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


class VacuulaCleaningCategorySelect(VacuulaEntity, SelectEntity):
    """Select entity for Gen3 cleaning category ('map' with No-Go lines vs 'house')."""

    _attr_name = "Cleaning mode"
    _attr_icon = "mdi:floor-plan"
    _attr_options = GEN3_CLEAN_CATEGORIES
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: VacuulaCoordinator, serial: str) -> None:
        """Initialize the cleaning category select entity."""
        super().__init__(coordinator, serial, "cleaning_category")

    @property
    def current_option(self) -> str | None:
        """Return 'map' or 'house'."""
        if not self.robot:
            return None
        return (
            CLEAN_CATEGORY_HOUSE
            if self.robot.preferred_category == GEN3_CATEGORY_HOUSE
            else CLEAN_CATEGORY_MAP
        )

    async def async_select_option(self, option: str) -> None:
        """Update the preferred cleaning category."""
        if not self.robot:
            return
        self.robot.preferred_category = (
            GEN3_CATEGORY_HOUSE if option == CLEAN_CATEGORY_HOUSE else GEN3_CATEGORY_MAP
        )
        self.coordinator.async_update_listeners()


class VacuulaTargetZoneSelect(VacuulaEntity, SelectEntity):
    """Select entity for choosing a target room zone (or 'all' for full map)."""

    _attr_name = "Target zone"
    _attr_icon = "mdi:vector-polygon"

    def __init__(self, coordinator: VacuulaCoordinator, serial: str) -> None:
        """Initialize the target zone select entity."""
        super().__init__(coordinator, serial, "target_zone")

    @property
    def options(self) -> list[str]:
        """Return 'all' plus all discovered room zone names on the active floorplan."""
        if not self.robot:
            return [ALL_ZONES_OPTION]
        zone_names = [str(z["name"]) for z in self.robot.zones if z.get("name")]
        seen: set[str] = {ALL_ZONES_OPTION}
        opts = [ALL_ZONES_OPTION]
        for name in zone_names:
            if name not in seen:
                seen.add(name)
                opts.append(name)
        return opts

    @property
    def current_option(self) -> str:
        """Return currently selected target zone (or 'all')."""
        if not self.robot:
            return ALL_ZONES_OPTION
        if self.robot.selected_zone in self.options:
            return self.robot.selected_zone
        return ALL_ZONES_OPTION

    async def async_select_option(self, option: str) -> None:
        """Select target zone for the next vacuum.start action."""
        if not self.robot:
            return
        self.robot.selected_zone = option
        self.coordinator.async_update_listeners()


class VacuulaSelectedMapSelect(VacuulaEntity, SelectEntity):
    """Select entity for choosing the robot's active floor map."""

    _attr_name = "Selected map"
    _attr_icon = "mdi:map"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: VacuulaCoordinator, serial: str) -> None:
        """Initialize the selected map select entity."""
        super().__init__(coordinator, serial, "selected_map")

    @property
    def options(self) -> list[str]:
        """Return available floor map names."""
        if not self.robot or not self.robot.maps:
            if self.robot and self.robot.active_map_name:
                return [self.robot.active_map_name]
            return []
        names: list[str] = []
        seen: set[str] = set()
        for m in self.robot.maps:
            name = str(m.get("name") or m.get("id") or "").strip()
            if name and name not in seen:
                seen.add(name)
                names.append(name)
        return names

    @property
    def current_option(self) -> str | None:
        """Return currently active map name."""
        if not self.robot:
            return None
        if self.robot.active_map_name and self.robot.active_map_name in self.options:
            return self.robot.active_map_name
        return self.options[0] if self.options else None

    async def async_select_option(self, option: str) -> None:
        """Switch the active map to the chosen floor map."""
        if not self.robot:
            return
        target_map = next(
            (
                m
                for m in self.robot.maps
                if str(m.get("name") or m.get("id") or "").strip() == option
            ),
            None,
        )
        if target_map and target_map.get("id"):
            await self.coordinator.async_set_active_map(
                self._serial, str(target_map["id"])
            )
