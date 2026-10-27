"""Base entity for Vacuula robots."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, ROBOT_TYPE_GEN3
from .coordinator import VacuulaCoordinator, VacuulaRobotData

if TYPE_CHECKING:
    from . import VacuulaConfigEntry


class VacuulaServerEntity(CoordinatorEntity[VacuulaCoordinator]):
    """Common base class for Vacuula server hub diagnostic entities."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: VacuulaCoordinator,
        entry: VacuulaConfigEntry,
        key: str,
    ) -> None:
        """Initialize the server entity."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"server_{entry.entry_id}_{key}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device registry info for server hub."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"server_{self._entry.entry_id}")},
            name=self._entry.title,
            manufacturer="Vacuula",
            model="Vacuula Server",
            sw_version=self.coordinator.server_info.get("version")
            if self.coordinator.server_info
            else None,
        )


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
        return (
            self.coordinator.data.get(self._serial) if self.coordinator.data else None
        )

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
        config_entry = getattr(self.coordinator, "config_entry", None)
        dev_info = DeviceInfo(
            identifiers={(DOMAIN, self._serial)},
            name=robot.name if robot else self._serial,
            manufacturer="Neato Robotics",
            model=meta.get("modelName") or default_model,
            sw_version=meta.get("firmware"),
            serial_number=self._serial,
        )
        if config_entry and self.hass:
            try:
                dev_reg = dr.async_get(self.hass)
                server_device = dev_reg.async_get_device_by_identifier(
                    (DOMAIN, f"server_{config_entry.entry_id}"),
                    config_entry.entry_id,
                )
                if server_device:
                    dev_info["via_device_id"] = server_device.id
            except RuntimeError:
                # Device registry not set up (e.g. standalone sandbox / mock environment)
                pass
        return dev_info
