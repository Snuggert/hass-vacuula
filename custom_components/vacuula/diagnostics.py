"""Diagnostics support for the Vacuula integration.

Sensitive fields (robot serials, MAC addresses, secrets and the server URL)
are redacted with ``async_redact_data`` before being returned.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_URL
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry

from . import VacuulaConfigEntry
from .const import DOMAIN
from .coordinator import VacuulaCoordinator, VacuulaRobotData

TO_REDACT = {
    CONF_URL,
    "host",
    "serial",
    "serial_number",
    "serialNumber",
    "mac",
    "mac_address",
    "macAddress",
    "secret",
    "secret_key",
    "token",
    "password",
    "nucleo_url",
    "unique_id",
}


def _serialize_robot(robot: VacuulaRobotData) -> dict[str, Any]:
    """Serialize a VacuulaRobotData instance for diagnostics output."""
    return {
        "serial": robot.serial,
        "name": robot.name,
        "robot_type": robot.robot_type,
        "connected": robot.connected,
        "installed_with": robot.installed_with,
        "preferred_fan_speed": robot.preferred_fan_speed,
        "preferred_navigation_mode": robot.preferred_navigation_mode,
        "preferred_category": robot.preferred_category,
        "selected_zone": robot.selected_zone,
        "active_map_id": robot.active_map_id,
        "active_map_name": robot.active_map_name,
        "maps": robot.maps,
        "zones": [
            {
                "id": z.get("id"),
                "name": z.get("name"),
                "color": z.get("color"),
                "enabled": z.get("enabled"),
            }
            for z in robot.zones
        ],
        "boundaries_count": len(robot.boundaries),
        "total_runs": robot.total_runs,
        "last_run_id": robot.last_run_id,
        "last_run": robot.last_run,
        "state": robot.state,
    }


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: VacuulaConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a Vacuula config entry."""
    coordinator: VacuulaCoordinator = entry.runtime_data
    try:
        server_info = await coordinator.client.async_get_server_info()
    except Exception as err:  # noqa: BLE001
        server_info = {"error": str(err)}

    # Robot dict keys are serials, so index them instead of exposing the serial.
    robots = {
        f"robot_{idx}": _serialize_robot(robot)
        for idx, robot in enumerate((coordinator.data or {}).values(), start=1)
    }
    return async_redact_data(
        {
            "entry": {
                "url": entry.data.get(CONF_URL),
                "title": entry.title,
            },
            "server_info": server_info,
            "robots": robots,
        },
        TO_REDACT,
    )


async def async_get_device_diagnostics(
    hass: HomeAssistant, entry: VacuulaConfigEntry, device: DeviceEntry
) -> dict[str, Any]:
    """Return diagnostics for a specific Neato robot device."""
    coordinator: VacuulaCoordinator = entry.runtime_data
    serial = next(
        (id_val for domain, id_val in device.identifiers if domain == DOMAIN),
        None,
    )
    if not serial or not coordinator.data or serial not in coordinator.data:
        return {"error": "Robot not found in coordinator data"}
    return async_redact_data(_serialize_robot(coordinator.data[serial]), TO_REDACT)
