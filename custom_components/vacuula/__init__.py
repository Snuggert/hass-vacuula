"""The Vacuula integration."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import voluptuous as vol
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ENTITY_ID, CONF_URL
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import VacuulaApiClient
from .const import (
    DEFAULT_URL,
    DOMAIN,
    PLATFORMS,
    SERVICE_CLEAN_SPOT,
    SERVICE_CLEAN_ZONE,
    SERVICE_CLEAN_ZONES,
    SERVICE_DISMISS_ALERT,
    SERVICE_REFRESH_MAPS,
    SERVICE_SEND_RAW_COMMAND,
)
from .coordinator import VacuulaCoordinator, VacuulaRobotData

_LOGGER = logging.getLogger(__name__)

FRONTEND_URL = "/vacuula_frontend/vacuula-map-card.js"
FRONTEND_VERSION = "0.8.0"

type VacuulaConfigEntry = ConfigEntry[VacuulaCoordinator]


async def _async_register_lovelace_resource(hass: HomeAssistant, url: str) -> None:
    """Automatically register or update the card in Lovelace storage resources."""
    lovelace_data: Any = hass.data.get("lovelace")
    if lovelace_data is None:
        return
    resources = (
        getattr(lovelace_data, "resources", None)
        if hasattr(lovelace_data, "resources")
        else lovelace_data.get("resources")
        if isinstance(lovelace_data, dict)
        else None
    )
    if resources is None or not hasattr(resources, "async_items"):
        return
    if hasattr(resources, "loaded") and not resources.loaded:
        await resources.async_load()

    for entry in resources.async_items():
        entry_url = str(entry.get("url", ""))
        if entry_url.startswith(FRONTEND_URL):
            if entry_url != url and hasattr(resources, "async_update_item"):
                await resources.async_update_item(entry["id"], {"url": url})
            return

    if hasattr(resources, "async_create_item"):
        await resources.async_create_item({"res_type": "module", "url": url})
        _LOGGER.info("Registered Vacuula Lovelace resource: %s", url)


async def _async_register_frontend(hass: HomeAssistant) -> None:
    """Register static path and auto-inject the bundled Vacuula Lovelace map card."""
    flag_key = f"{DOMAIN}_frontend_registered"
    card_path = Path(__file__).parent / "frontend" / "vacuula-map-card.js"
    if not card_path.is_file():
        return
    versioned_url = f"{FRONTEND_URL}?v={FRONTEND_VERSION}"
    try:
        if not hass.data.get(flag_key):
            if hasattr(hass.http, "async_register_static_paths"):
                await hass.http.async_register_static_paths(
                    [
                        StaticPathConfig(
                            FRONTEND_URL, str(card_path), cache_headers=False
                        )
                    ]
                )
            hass.data[flag_key] = True
        await _async_register_lovelace_resource(hass, versioned_url)
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("Could not register Vacuula Lovelace card: %s", err)


def _async_get_loaded_entries(hass: HomeAssistant) -> list[VacuulaConfigEntry]:
    """Return loaded config entries for Vacuula."""
    if hasattr(hass.config_entries, "async_loaded_entries"):
        return hass.config_entries.async_loaded_entries(DOMAIN)
    return [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if getattr(entry, "runtime_data", None) is not None
    ]


def _serial_from_entity_id(
    hass: HomeAssistant, entity_id: str | list[str] | None
) -> str | None:
    """Resolve a robot serial from a Home Assistant entity_id if provided."""
    if not entity_id:
        return None
    target_eid = entity_id[0] if isinstance(entity_id, list) else str(entity_id)
    state = hass.states.get(target_eid)
    if state and state.attributes.get("serial"):
        return str(state.attributes["serial"])
    ent_reg = er.async_get(hass)
    reg_entry = ent_reg.async_get(target_eid)
    if reg_entry and reg_entry.unique_id:
        uid = reg_entry.unique_id
        for entry in _async_get_loaded_entries(hass):
            coord: VacuulaCoordinator = entry.runtime_data
            if coord.data:
                for rob_serial in coord.data:
                    if uid == rob_serial or uid.startswith(f"{rob_serial}_"):
                        return rob_serial
    return None


def _resolve_target_robot(
    hass: HomeAssistant,
    serial: str | None = None,
    entity_id: str | list[str] | None = None,
) -> tuple[VacuulaCoordinator, VacuulaRobotData]:
    """Find the coordinator and robot matching serial/entity_id, or the sole robot if omitted."""
    resolved_serial = serial or _serial_from_entity_id(hass, entity_id)
    entries: list[VacuulaConfigEntry] = _async_get_loaded_entries(hass)
    all_robots: list[tuple[VacuulaCoordinator, VacuulaRobotData]] = []
    for entry in entries:
        coord: VacuulaCoordinator = entry.runtime_data
        if not coord.data:
            continue
        if resolved_serial and resolved_serial in coord.data:
            return coord, coord.data[resolved_serial]
        for robot in coord.data.values():
            all_robots.append((coord, robot))

    if resolved_serial:
        raise HomeAssistantError(f"Robot '{resolved_serial}' not found in Vacuula")
    if len(all_robots) == 1:
        return all_robots[0]
    if not all_robots:
        raise HomeAssistantError("No robots found in Vacuula")
    raise HomeAssistantError(
        "Multiple robots are configured; please specify 'entity_id' or 'serial' in the action call"
    )


def _async_register_services(hass: HomeAssistant) -> None:
    """Register domain-level actions for Vacuula (idempotent)."""
    if hass.services.has_service(DOMAIN, SERVICE_CLEAN_ZONES):
        return

    async def _handle_clean_zones(call: ServiceCall) -> None:
        serial = call.data.get("serial")
        entity_id = call.data.get(ATTR_ENTITY_ID)
        raw_zones = call.data["zones"]
        if isinstance(raw_zones, str):
            zone_list = [z.strip() for z in raw_zones.split(",") if z.strip()]
        elif isinstance(raw_zones, list):
            zone_list = [str(z).strip() for z in raw_zones if str(z).strip()]
        else:
            zone_list = [str(raw_zones).strip()]

        coord, robot = _resolve_target_robot(hass, serial, entity_id)
        map_id = call.data.get("map_id") or robot.active_map_id
        if not map_id:
            raise HomeAssistantError(
                f"No active floor map available for robot {robot.name} ({robot.serial})"
            )

        zone_ids = robot.resolve_zone_ids(zone_list)
        fan_speed = call.data.get("fan_speed") or robot.preferred_fan_speed
        nav_mode = call.data.get("navigation_mode") or robot.preferred_navigation_mode

        resp = await coord.client.async_start_zone_cleaning(
            robot.serial,
            robot.robot_type,
            map_id,
            zone_ids,
            fan_speed=fan_speed,
            navigation_mode=nav_mode,
        )
        await coord.async_apply_command_response(robot.serial, resp)

    async def _handle_clean_spot(call: ServiceCall) -> None:
        serial = call.data.get("serial")
        entity_id = call.data.get(ATTR_ENTITY_ID)
        coord, robot = _resolve_target_robot(hass, serial, entity_id)
        width = int(call.data.get("width", 200))
        height = int(call.data.get("height", 200))
        fan_speed = call.data.get("fan_speed") or robot.preferred_fan_speed
        nav_mode = call.data.get("navigation_mode") or robot.preferred_navigation_mode

        resp = await coord.client.async_start_spot_cleaning(
            robot.serial,
            robot.robot_type,
            width=width,
            height=height,
            fan_speed=fan_speed,
            navigation_mode=nav_mode,
        )
        await coord.async_apply_command_response(robot.serial, resp)

    async def _handle_refresh_maps(call: ServiceCall) -> None:
        serial = call.data.get("serial")
        entity_id = call.data.get(ATTR_ENTITY_ID)
        if serial or entity_id:
            coord, robot = _resolve_target_robot(hass, serial, entity_id)
            await coord.async_refresh_maps_and_runs(robot.serial)
            return
        tasks = [
            entry.runtime_data.async_refresh_maps_and_runs(rob_serial)
            for entry in _async_get_loaded_entries(hass)
            if entry.runtime_data and entry.runtime_data.data
            for rob_serial in list(entry.runtime_data.data)
        ]
        if tasks:
            await asyncio.gather(*tasks)

    async def _handle_clean_zone(call: ServiceCall) -> None:
        serial = call.data.get("serial")
        entity_id = call.data.get(ATTR_ENTITY_ID)
        zone_name = str(call.data["zone_name"]).strip()
        map_name_filter = call.data.get("map_name")
        if map_name_filter is not None:
            map_name_filter = str(map_name_filter).strip().lower()

        coord, robot = _resolve_target_robot(hass, serial, entity_id)

        target_zone = None
        for zone in robot.zones:
            if not isinstance(zone, dict):
                continue
            name = str(zone.get("name", "")).strip()
            if name.lower() == zone_name.lower():
                z_map_name = zone.get("map_name") or robot.active_map_name
                if map_name_filter is None or (
                    z_map_name and str(z_map_name).strip().lower() == map_name_filter
                ):
                    target_zone = zone
                    break

        if not target_zone:
            raise HomeAssistantError(
                f"Zone '{call.data['zone_name']}' not found for robot {robot.serial}"
            )

        map_id = (
            target_zone.get("map_id") or call.data.get("map_id") or robot.active_map_id
        )
        if not map_id:
            raise HomeAssistantError(
                f"No active floor map available for robot {robot.name} ({robot.serial})"
            )

        fan_speed = (
            call.data.get("fan_speed")
            or call.data.get("mode")
            or robot.preferred_fan_speed
        )
        nav_mode = call.data.get("navigation_mode") or robot.preferred_navigation_mode

        resp = await coord.client.async_start_zone_cleaning(
            robot.serial,
            robot.robot_type,
            map_id,
            [str(target_zone["id"])],
            fan_speed=fan_speed,
            navigation_mode=nav_mode,
        )
        await coord.async_apply_command_response(robot.serial, resp)

    async def _handle_dismiss_alert(call: ServiceCall) -> None:
        serial = call.data.get("serial")
        entity_id = call.data.get(ATTR_ENTITY_ID)
        coord, robot = _resolve_target_robot(hass, serial, entity_id)
        resp = await coord.client.async_dismiss_alert(robot.serial)
        if resp:
            await coord.async_apply_command_response(robot.serial, resp)

    async def _handle_send_raw_command(call: ServiceCall) -> None:
        serial = call.data.get("serial")
        entity_id = call.data.get(ATTR_ENTITY_ID)
        command = str(call.data["command"])
        params = call.data.get("params")
        coord, robot = _resolve_target_robot(hass, serial, entity_id)
        resp = await coord.client.async_send_raw_command(robot.serial, command, params)
        if resp:
            await coord.async_apply_command_response(robot.serial, resp)

    hass.services.async_register(
        DOMAIN,
        SERVICE_CLEAN_ZONE,
        _handle_clean_zone,
        schema=vol.Schema(
            {
                vol.Optional(ATTR_ENTITY_ID): cv.comp_entity_ids,
                vol.Optional("serial"): cv.string,
                vol.Required("zone_name"): cv.string,
                vol.Optional("map_name"): cv.string,
                vol.Optional("fan_speed"): cv.string,
                vol.Optional("mode"): cv.string,
                vol.Optional("navigation_mode"): cv.string,
            }
        ),
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_CLEAN_ZONES,
        _handle_clean_zones,
        schema=vol.Schema(
            {
                vol.Optional(ATTR_ENTITY_ID): cv.comp_entity_ids,
                vol.Optional("serial"): cv.string,
                vol.Required("zones"): vol.Any(cv.string, [cv.string]),
                vol.Optional("map_id"): cv.string,
                vol.Optional("fan_speed"): cv.string,
                vol.Optional("navigation_mode"): cv.string,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CLEAN_SPOT,
        _handle_clean_spot,
        schema=vol.Schema(
            {
                vol.Optional(ATTR_ENTITY_ID): cv.comp_entity_ids,
                vol.Optional("serial"): cv.string,
                vol.Optional("width", default=200): vol.All(
                    vol.Coerce(int), vol.Range(min=50, max=500)
                ),
                vol.Optional("height", default=200): vol.All(
                    vol.Coerce(int), vol.Range(min=50, max=500)
                ),
                vol.Optional("fan_speed"): cv.string,
                vol.Optional("navigation_mode"): cv.string,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_REFRESH_MAPS,
        _handle_refresh_maps,
        schema=vol.Schema(
            {
                vol.Optional(ATTR_ENTITY_ID): cv.comp_entity_ids,
                vol.Optional("serial"): cv.string,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_DISMISS_ALERT,
        _handle_dismiss_alert,
        schema=vol.Schema(
            {
                vol.Optional(ATTR_ENTITY_ID): cv.comp_entity_ids,
                vol.Optional("serial"): cv.string,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_RAW_COMMAND,
        _handle_send_raw_command,
        schema=vol.Schema(
            {
                vol.Optional(ATTR_ENTITY_ID): cv.comp_entity_ids,
                vol.Optional("serial"): cv.string,
                vol.Required("command"): cv.string,
                vol.Optional("params"): vol.Any(dict, None),
            }
        ),
    )


async def async_setup_entry(hass: HomeAssistant, entry: VacuulaConfigEntry) -> bool:
    """Set up Vacuula from a config entry."""
    await _async_register_frontend(hass)

    session = async_get_clientsession(hass)
    server_url = entry.data.get(CONF_URL, DEFAULT_URL)
    client = VacuulaApiClient(server_url, session)
    coordinator = VacuulaCoordinator(hass, entry, client)

    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    _async_register_services(hass)

    # Register Hub device in Device Registry
    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, f"server_{entry.entry_id}")},
        name=entry.title,
        manufacturer="Vacuula",
        model="Vacuula Server",
        sw_version=coordinator.server_info.get("version")
        if coordinator.server_info
        else None,
        entry_type=dr.DeviceEntryType.SERVICE,
        configuration_url=coordinator.client.base_url,
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await coordinator.async_start_sse()
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_reload_entry(hass: HomeAssistant, entry: VacuulaConfigEntry) -> None:
    """Reload config entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: VacuulaConfigEntry) -> bool:
    """Unload a config entry."""
    coordinator = getattr(entry, "runtime_data", None)
    if coordinator is not None and hasattr(coordinator, "async_stop_sse"):
        await coordinator.async_stop_sse()
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok and not _async_get_loaded_entries(hass):
        for service in (
            SERVICE_CLEAN_ZONES,
            SERVICE_CLEAN_SPOT,
            SERVICE_REFRESH_MAPS,
        ):
            hass.services.async_remove(DOMAIN, service)
    return unload_ok
