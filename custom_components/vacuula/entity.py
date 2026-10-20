"""Base entity for Vacuula robots."""
from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, ROBOT_TYPE_GEN3
from .coordinator import VacuulaCoordinator, VacuulaRobotData


class VacuulaEntity(CoordinatorEntity[VacuulaCoordinator]):
    """Common base class for all Vacuula robot entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: VacuulaCoordinator, serial: str, key: str) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._serial = serial
        self._attr_unique_id = f"{serial}_{key}"

    @property
    def _robot(self) -> VacuulaRobotData | None:
        """Return current robot data from coordinator."""
        return self.coordinator.data.get(self._serial) if self.coordinator.data else None

    @property
    def robot(self) -> VacuulaRobotData | None:
        """Return current robot data from coordinator."""
        return self._robot

    @property
    def _gen4_body(self) -> dict[str, Any]:
        """Return the inner body dictionary for a Gen4 robot state."""
        robot = self._robot
        if not robot or not robot.state:
            return {}
        body = robot.state.get("body")
        return body if isinstance(body, dict) else robot.state

    @property
    def available(self) -> bool:
        """Return True if the robot is currently connected to Vacuula."""
        return bool(super().available and self._robot and self._robot.connected)

    @property
    def device_info(self) -> DeviceInfo:
        """Return device registry info for this robot."""
        robot = self._robot
        state = robot.state if robot else {}
        meta = state.get("meta", {}) if isinstance(state, dict) else {}
        default_model = (
            "Neato Botvac Connected (Gen3)"
            if (robot and robot.robot_type == ROBOT_TYPE_GEN3)
            else "Neato Botvac (Gen4)"
        )
        return DeviceInfo(
            identifiers={(DOMAIN, self._serial)},
            name=robot.name if robot else self._serial,
            manufacturer="Neato Robotics",
            model=meta.get("modelName") or default_model,
            sw_version=meta.get("firmware"),
            serial_number=self._serial,
        )
