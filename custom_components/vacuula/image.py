"""Image platform for Vacuula robot floor maps and last cleaning run maps."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from homeassistant.components.image import ImageEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import VacuulaConfigEntry
from .coordinator import VacuulaCoordinator
from .entity import VacuulaEntity
from .map_renderer import compute_cropped_zones, render_map_png


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VacuulaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Vacuula map image entities with dynamic robot discovery."""
    coordinator: VacuulaCoordinator = entry.runtime_data

    @callback
    def _async_add_new_robots(serials: list[str]) -> None:
        entities: list[ImageEntity] = []
        for serial in serials:
            entities.extend(
                [
                    VacuulaFloorMapImage(coordinator, serial),
                    VacuulaLastRunMapImage(coordinator, serial),
                ]
            )
        async_add_entities(entities)

    entry.async_on_unload(
        coordinator.register_new_robot_callback(_async_add_new_robots)
    )


class VacuulaFloorMapImage(VacuulaEntity, ImageEntity):
    """Image entity rendering the robot's active floor plan, room zones, and No-Go lines."""

    _attr_name = "Floor map"
    _attr_icon = "mdi:floor-plan"
    _attr_content_type = "image/png"

    def __init__(self, coordinator: VacuulaCoordinator, serial: str) -> None:
        """Initialize the floor map image entity."""
        VacuulaEntity.__init__(self, coordinator, serial, "floor_map")
        ImageEntity.__init__(self, coordinator.hass)
        self._cached_key: tuple[str | None, int] | None = None
        self._cached_png: bytes | None = None
        self._attr_image_last_updated = datetime.now(UTC)

    @property
    def available(self) -> bool:
        """Remain available while server is reachable and floor map is loaded."""
        return bool(
            CoordinatorEntity.available.fget(self)
            and self._robot is not None
            and self._robot.floormap is not None
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return metadata about the active floor plan and interactive cropped zones."""
        robot = self._robot
        if not robot:
            return {}
        return {
            "serial": self._serial,
            "map_id": robot.active_map_id,
            "map_name": robot.active_map_name,
            "zones": compute_cropped_zones(robot.floormap, robot.boundaries),
        }

    @callback
    def _handle_coordinator_update(self) -> None:
        """Invalidate cache and bump timestamp when map or boundaries change."""
        robot = self._robot
        if robot:
            new_key = (robot.active_map_id, len(robot.boundaries))
            if new_key != self._cached_key:
                self._attr_image_last_updated = datetime.now(UTC)
        super()._handle_coordinator_update()

    async def async_image(self) -> bytes | None:
        """Return rendered PNG bytes of the active floor plan."""
        robot = self._robot
        if not robot or not robot.floormap:
            return None
        key = (robot.active_map_id, len(robot.boundaries))
        if key == self._cached_key and self._cached_png is not None:
            return self._cached_png

        png = await self.hass.async_add_executor_job(
            render_map_png, robot.floormap, robot.boundaries, None
        )
        self._cached_key = key
        self._cached_png = png
        return png


class VacuulaLastRunMapImage(VacuulaEntity, ImageEntity):
    """Image entity rendering the latest cleaning run path overlaid on the floor plan."""

    _attr_name = "Last run map"
    _attr_icon = "mdi:map-check-outline"
    _attr_content_type = "image/png"

    def __init__(self, coordinator: VacuulaCoordinator, serial: str) -> None:
        """Initialize the last run map image entity."""
        VacuulaEntity.__init__(self, coordinator, serial, "last_run_map")
        ImageEntity.__init__(self, coordinator.hass)
        self._cached_key: tuple[str | None, str | None, int] | None = None
        self._cached_png: bytes | None = None
        self._attr_image_last_updated = datetime.now(UTC)

    @property
    def available(self) -> bool:
        """Remain available while server is reachable and run or floor map is loaded."""
        return bool(
            CoordinatorEntity.available.fget(self)
            and self._robot is not None
            and (
                self._robot.last_runmap is not None or self._robot.floormap is not None
            )
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return metadata about the latest cleaning run."""
        robot = self._robot
        if not robot or not robot.last_run:
            return {}
        return {
            "serial": self._serial,
            "run_id": robot.last_run_id,
            "cleaned_area_m2": robot.last_run.get("cleaned_area"),
            "start_at": robot.last_run.get("start_at"),
            "end_at": robot.last_run.get("end_at"),
            "status": robot.last_run.get("status"),
            "zones": compute_cropped_zones(robot.floormap, robot.boundaries),
        }

    @callback
    def _handle_coordinator_update(self) -> None:
        """Invalidate cache and bump timestamp when last run changes."""
        robot = self._robot
        if robot:
            new_key = (
                robot.active_map_id,
                robot.last_run_id,
                len(robot.boundaries),
            )
            if new_key != self._cached_key:
                self._attr_image_last_updated = datetime.now(UTC)
        super()._handle_coordinator_update()

    async def async_image(self) -> bytes | None:
        """Return rendered PNG bytes of the latest cleaning run overlaid on the floor map."""
        robot = self._robot
        if not robot or (not robot.last_runmap and not robot.floormap):
            return None
        key = (robot.active_map_id, robot.last_run_id, len(robot.boundaries))
        if key == self._cached_key and self._cached_png is not None:
            return self._cached_png

        png = await self.hass.async_add_executor_job(
            render_map_png, robot.floormap, robot.boundaries, robot.last_runmap
        )
        self._cached_key = key
        self._cached_png = png
        return png
