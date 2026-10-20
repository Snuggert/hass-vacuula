"""Button platform for Vacuula robots (Locate, Dismiss Alert)."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
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
    """Set up Vacuula button entities."""
    coordinator: VacuulaCoordinator = entry.runtime_data

    @callback
    def _async_add_new_robots(serials: list[str]) -> None:
        entities: list[ButtonEntity] = []
        for serial in serials:
            entities.append(VacuulaLocateButton(coordinator, serial))
            robot = coordinator.data.get(serial)
            if robot and robot.robot_type == ROBOT_TYPE_GEN3:
                entities.append(VacuulaDismissAlertButton(coordinator, serial))
        async_add_entities(entities)

    entry.async_on_unload(
        coordinator.register_new_robot_callback(_async_add_new_robots)
    )


class VacuulaLocateButton(VacuulaEntity, ButtonEntity):
    """Button to trigger the robot's 'Find Me' sound."""

    _attr_name = "Locate"
    _attr_icon = "mdi:volume-high"

    def __init__(self, coordinator: VacuulaCoordinator, serial: str) -> None:
        """Initialize the locate button."""
        super().__init__(coordinator, serial, "locate")

    async def async_press(self) -> None:
        """Play locate sound on the robot."""
        if robot := self._robot:
            await self.coordinator.client.async_locate(
                self._serial, robot.robot_type
            )


class VacuulaDismissAlertButton(VacuulaEntity, ButtonEntity):
    """Button to dismiss the current alert on a Gen3 robot."""

    _attr_name = "Dismiss alert"
    _attr_icon = "mdi:bell-cancel-outline"

    def __init__(self, coordinator: VacuulaCoordinator, serial: str) -> None:
        """Initialize the dismiss alert button."""
        super().__init__(coordinator, serial, "dismiss_alert")

    async def async_press(self) -> None:
        """Dismiss current alert and update robot state."""
        if robot := self._robot:
            resp = await self.coordinator.client.async_dismiss_alert(
                self._serial, robot.robot_type
            )
            await self.coordinator.async_apply_command_response(self._serial, resp)
