"""Full-Stack Developer Sandbox: In-Process Integration Runtime, Entity Registry & Lovelace UI.

Spins up the actual `custom_components/vacuula` integration (`VacuulaCoordinator` + all 7
Home Assistant entity platforms: `vacuum`, `image`, `sensor`, `binary_sensor`, `select`,
`switch`, `button`), connects it via REST + SSE to the live `VacuulaServerManager`, and
serves a complete Lovelace frontend (`<vacuula-map-card>` + `<vacuula-map-card-editor>`)
alongside an interactive Home Assistant Entity & Device Inspector in the browser.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import re
import time
from collections.abc import Callable
from typing import Any

# Pre-import homeassistant before voluptuous so probatio's install_as_voluptuous()
# never emits a RuntimeWarning.
with contextlib.suppress(ImportError):
    import homeassistant  # noqa: F401

import aiohttp
from aiohttp import web

from custom_components.vacuula.core import (
    FAN_SPEEDS_GEN3,
    FAN_SPEEDS_GEN4,
    GEN3_NAV_MODES,
    GEN4_NAV_MODES,
    ROBOT_TYPE_GEN3,
    VacuulaApiClient,
    VacuulaController,
    VacuulaRobotData,
    render_map_png,
)

from .server_manager import REPO_ROOT, VacuulaServerManager

logger = logging.getLogger(__name__)

CARD_JS_PATH = (
    REPO_ROOT / "custom_components" / "vacuula" / "frontend" / "vacuula-map-card.js"
)


def _slugify(text: str) -> str:
    """Convert a string into a Home Assistant entity slug."""
    slug = re.sub(r"[^a-z0-9]+", "_", text.strip().lower()).strip("_")
    return slug or "neato_botvac"


class _LightweightEventBus:
    """Lightweight event bus shim for Home Assistant helpers (e.g. httpx_client)."""

    def __init__(self) -> None:
        """Initialize the event bus."""
        self._listeners: list[tuple[str, Callable[..., Any]]] = []

    def async_listen_once(
        self, event_type: str, listener: Callable[..., Any]
    ) -> Callable[[], None]:
        """Listen once for an event type."""
        entry = (event_type, listener)
        self._listeners.append(entry)

        def _remove() -> None:
            if entry in self._listeners:
                self._listeners.remove(entry)

        return _remove

    def async_listen(
        self, event_type: str, listener: Callable[..., Any]
    ) -> Callable[[], None]:
        """Listen for an event type."""
        return self.async_listen_once(event_type, listener)

    async def async_fire_all(self) -> None:
        """Invoke all registered listeners on shutdown."""
        while self._listeners:
            _, cb = self._listeners.pop()
            with contextlib.suppress(Exception):
                res = cb(None)
                if asyncio.iscoroutine(res):
                    await res


class _LightweightMockHass:
    """Lightweight in-process Home Assistant runtime shim for hosting real integration entities."""

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        """Initialize the mock Home Assistant runtime."""
        self.loop = loop
        self.data: dict[str, Any] = {}
        self.bus = _LightweightEventBus()
        self._tasks: set[asyncio.Task[Any]] = set()

    def async_create_background_task(self, target: Any, name: str) -> asyncio.Task[Any]:
        """Create and track a background asyncio task."""
        task = self.loop.create_task(target, name=name)
        self._tasks.add(task)
        return task

    async def async_add_executor_job(
        self, target: Callable[..., Any], *args: Any
    ) -> Any:
        """Run a blocking callable in the default thread pool executor."""
        return await self.loop.run_in_executor(None, target, *args)

    async def async_shutdown(self) -> None:
        """Cancel all background tasks and close registered bus listeners."""
        tasks = list(self._tasks)
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()
        await self.bus.async_fire_all()


class _LightweightMockConfigEntry:
    """Lightweight ConfigEntry shim for setting up custom_components/vacuula platforms."""

    def __init__(self, url: str) -> None:
        """Initialize the mock config entry."""
        self.entry_id = "sandbox_vacuula_entry"
        self.domain = "vacuula"
        self.title = "Vacuula Dev Server"
        self.data = {"url": url}
        self.options: dict[str, Any] = {}
        self.pref_disable_polling = True
        self.runtime_data: Any = None
        self._unload_callbacks: list[Callable[[], None]] = []

    def async_on_unload(self, func: Callable[[], Any]) -> None:
        """Register an unload callback."""
        self._unload_callbacks.append(func)

    async def async_unload(self) -> None:
        """Invoke all registered unload callbacks."""
        while self._unload_callbacks:
            cb = self._unload_callbacks.pop()
            with contextlib.suppress(Exception):
                res = cb()
                if asyncio.iscoroutine(res):
                    await res


class VacuulaDevSandbox:
    """Full-stack sandbox hosting the real `custom_components/vacuula` integration and Lovelace UI."""

    def __init__(
        self,
        vacuula_url: str,
        server_manager: VacuulaServerManager | None = None,
        host: str = "127.0.0.1",
        port: int = 8124,
    ) -> None:
        """Initialize the standalone developer sandbox."""
        self.vacuula_url = vacuula_url.rstrip("/")
        self.server_manager = server_manager
        self.host = host
        self.port = port
        self._session: aiohttp.ClientSession | None = None
        self.client: VacuulaApiClient | None = None
        self.controller: VacuulaController | None = None

        # Real Home Assistant integration runtime objects
        self._mock_hass: _LightweightMockHass | None = None
        self._mock_entry: _LightweightMockConfigEntry | None = None
        self.coordinator: Any = None
        self.entities: dict[str, Any] = {}
        self._entity_domains: dict[str, str] = {}

        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None
        self._map_cache_buster: int = int(time.time() * 1000)
        self._sse_Queues: set[asyncio.Queue[str]] = set()

    @property
    def sandbox_url(self) -> str:
        """Return the HTTP URL for the sandbox UI."""
        return f"http://{self.host}:{self.port}"

    async def _setup_real_integration_entities(self) -> bool:
        """Boot the actual custom_components/vacuula coordinator and all 7 entity platforms."""
        try:
            from custom_components.vacuula import (
                binary_sensor as ha_binary_sensor,
            )
            from custom_components.vacuula import (
                button as ha_button,
            )
            from custom_components.vacuula import (
                image as ha_image,
            )
            from custom_components.vacuula import (
                select as ha_select,
            )
            from custom_components.vacuula import (
                sensor as ha_sensor,
            )
            from custom_components.vacuula import (
                switch as ha_switch,
            )
            from custom_components.vacuula import (
                vacuum as ha_vacuum,
            )
            from custom_components.vacuula.coordinator import VacuulaCoordinator
        except ImportError:
            logger.info(
                "Home Assistant package not installed; using pure-Python VacuulaController fallback"
            )
            return False

        assert self.client is not None
        loop = asyncio.get_running_loop()
        self._mock_hass = _LightweightMockHass(loop)
        self._mock_entry = _LightweightMockConfigEntry(self.vacuula_url)

        self.coordinator = VacuulaCoordinator(
            self._mock_hass,  # type: ignore[arg-type]
            self._mock_entry,  # type: ignore[arg-type]
            self.client,
        )
        self._mock_entry.runtime_data = self.coordinator

        # Perform initial poll (fetches server_info, robots, state, maps, boundaries, runs)
        self.coordinator.data = await self.coordinator._async_update_data()  # noqa: SLF001
        self.coordinator.last_update_success = True

        # Helper to register entities created by each platform's async_setup_entry
        def _make_adder(platform_domain: str) -> Callable[[Any], None]:
            def _add_entities(
                new_entities: Any, _update_before_add: bool = False
            ) -> None:
                for ent in new_entities:
                    ent.hass = self._mock_hass
                    eid = self._compute_entity_id(platform_domain, ent)
                    ent.entity_id = eid
                    self.entities[eid] = ent
                    self._entity_domains[eid] = platform_domain

            return _add_entities

        # Forward setup to all 7 real integration platforms!
        for domain_name, platform_mod in (
            ("vacuum", ha_vacuum),
            ("image", ha_image),
            ("sensor", ha_sensor),
            ("binary_sensor", ha_binary_sensor),
            ("select", ha_select),
            ("switch", ha_switch),
            ("button", ha_button),
        ):
            await platform_mod.async_setup_entry(
                self._mock_hass,  # type: ignore[arg-type]
                self._mock_entry,  # type: ignore[arg-type]
                _make_adder(domain_name),  # type: ignore[arg-type]
            )

        # Subscribe to coordinator updates so SSE events push immediately to browser clients
        self.coordinator.async_add_listener(self._on_coordinator_update)

        # Start live SSE listeners against the Vacuula dev server
        await self.coordinator.async_start_sse()
        logger.info(
            "Loaded %d live entities from custom_components/vacuula across 7 platforms",
            len(self.entities),
        )
        return True

    def _compute_entity_id(self, platform_domain: str, ent: Any) -> str:
        """Compute the standard Home Assistant entity_id for an integration entity."""
        robot = getattr(ent, "_robot", None)
        robot_slug = _slugify(robot.name if robot else getattr(ent, "_serial", "robot"))
        uid = str(getattr(ent, "unique_id", "") or "")
        serial = str(getattr(ent, "_serial", "") or "")
        key = uid[len(serial) + 1 :] if uid.startswith(f"{serial}_") else uid

        if platform_domain == "vacuum" or key == "vacuum":
            return f"vacuum.{robot_slug}"
        # Map bin_full key to dust_bin_full for friendly Lovelace matching
        if platform_domain == "binary_sensor" and key == "bin_full":
            return f"binary_sensor.{robot_slug}_dust_bin_full"
        return f"{platform_domain}.{robot_slug}_{_slugify(key)}"

    def _on_coordinator_update(self) -> None:
        """Broadcast updated entity states to all connected browser SSE clients."""
        payload = json.dumps(
            {
                "states": self.build_hass_states(),
                "entities": self.build_entity_inspector_list(),
                "devices": self.build_device_list(),
                "server_info": self._get_server_info(),
            }
        )
        for q in list(self._sse_Queues):
            with contextlib.suppress(asyncio.QueueFull):
                q.put_nowait(payload)

    def _get_server_info(self) -> dict[str, Any]:
        """Return server metadata from coordinator or controller."""
        if self.coordinator is not None:
            return dict(self.coordinator.server_info)
        if self.controller is not None:
            return dict(self.controller.server_info)
        return {}

    def _get_robots_dict(self) -> dict[str, VacuulaRobotData]:
        """Return current robots mapping from coordinator or controller."""
        if self.coordinator is not None and self.coordinator.data:
            return dict(self.coordinator.data)
        if self.controller is not None:
            return dict(self.controller.robots)
        return {}

    async def async_start(self) -> None:
        """Start the aiohttp client, integration runtime, and sandbox web server."""
        self._session = aiohttp.ClientSession()
        self.client = VacuulaApiClient(self.vacuula_url, self._session)

        used_real_ha = await self._setup_real_integration_entities()
        if not used_real_ha:
            self.controller = VacuulaController(self.client)
            await self.controller.async_refresh_all()

        app = web.Application()
        app.router.add_get("/", self._handle_index)
        app.router.add_get("/favicon.ico", self._handle_favicon)
        app.router.add_get(
            "/vacuula_frontend/vacuula-map-card.js", self._handle_card_js
        )
        app.router.add_get("/api/sandbox/states", self._handle_get_states)
        app.router.add_get("/api/sandbox/events", self._handle_sse_events)
        app.router.add_post("/api/sandbox/call_service", self._handle_call_service)
        app.router.add_post("/api/sandbox/mock_robot", self._handle_mock_robot)
        app.router.add_get("/api/sandbox/map/{serial}/{kind}.png", self._handle_map_png)

        self._runner = web.AppRunner(app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self.host, self.port)
        await self._site.start()
        if self._site._server and self._site._server.sockets:  # noqa: SLF001
            self.port = self._site._server.sockets[0].getsockname()[1]  # noqa: SLF001
        logger.info("Vacuula Developer Sandbox running at %s", self.sandbox_url)

    async def async_stop(self) -> None:
        """Stop the integration runtime, SSE tasks, web server, and HTTP session."""
        if self.coordinator is not None and hasattr(self.coordinator, "async_stop_sse"):
            with contextlib.suppress(Exception):
                await self.coordinator.async_stop_sse()
        if self._mock_entry is not None:
            await self._mock_entry.async_unload()
        if self._mock_hass is not None:
            await self._mock_hass.async_shutdown()
        if self._runner:
            await self._runner.cleanup()
            self._runner = None
        if self._session:
            await self._session.close()
            self._session = None

    def _serialize_real_entity(self, eid: str, ent: Any) -> dict[str, Any]:
        """Serialize a live Home Assistant Entity instance into a state object."""
        domain = self._entity_domains.get(eid, eid.split(".")[0])
        robot = getattr(ent, "_robot", None)
        serial = getattr(ent, "_serial", "")
        robot_name = robot.name if robot else serial
        ent_name = getattr(ent, "name", None) or getattr(ent, "_attr_name", None)
        friendly_name = f"{robot_name} {ent_name}".strip() if ent_name else robot_name

        available = bool(getattr(ent, "available", True))
        raw_attrs = dict(getattr(ent, "extra_state_attributes", None) or {})
        raw_attrs["friendly_name"] = friendly_name
        if serial and "serial" not in raw_attrs:
            raw_attrs["serial"] = serial

        state_val = "unavailable"
        if available:
            if domain == "vacuum":
                act = getattr(ent, "activity", None)
                state_val = str(act.value if hasattr(act, "value") else (act or "idle"))
                raw_attrs["fan_speed"] = getattr(ent, "fan_speed", None)
                raw_attrs["fan_speed_list"] = getattr(ent, "fan_speed_list", [])
                raw_attrs["supported_features"] = int(
                    getattr(ent, "supported_features", 14204)
                )
            elif domain == "sensor":
                nv = getattr(ent, "native_value", None)
                state_val = "unknown" if nv is None else str(nv)
                unit = getattr(ent, "native_unit_of_measurement", None)
                if unit:
                    raw_attrs["unit_of_measurement"] = str(unit)
                dc = getattr(ent, "device_class", None)
                if dc:
                    raw_attrs["device_class"] = str(
                        dc.value if hasattr(dc, "value") else dc
                    )
            elif domain == "binary_sensor":
                is_on = getattr(ent, "is_on", None)
                state_val = "unknown" if is_on is None else ("on" if is_on else "off")
                dc = getattr(ent, "device_class", None)
                if dc:
                    raw_attrs["device_class"] = str(
                        dc.value if hasattr(dc, "value") else dc
                    )
            elif domain == "select":
                opt = getattr(ent, "current_option", None)
                state_val = "unknown" if opt is None else str(opt)
                raw_attrs["options"] = list(getattr(ent, "options", []))
            elif domain == "switch":
                is_on = getattr(ent, "is_on", None)
                state_val = "unknown" if is_on is None else ("on" if is_on else "off")
            elif domain == "button":
                state_val = "2026-10-26T09:00:00Z"
            elif domain == "image":
                dt = getattr(ent, "image_last_updated", None)
                state_val = dt.isoformat() if dt else "2026-10-26T09:00:00Z"
                kind = "run" if "last_run" in eid else "floor"
                raw_attrs["entity_picture"] = (
                    f"/api/sandbox/map/{serial}/{kind}.png?t={self._map_cache_buster}"
                )

        icon = getattr(ent, "icon", None) or getattr(ent, "_attr_icon", None)
        if icon:
            raw_attrs["icon"] = icon

        return {
            "entity_id": eid,
            "domain": domain,
            "class_name": ent.__class__.__name__,
            "entity_class": ent.__class__.__name__,
            "unique_id": getattr(ent, "unique_id", eid),
            "serial": serial,
            "state": state_val,
            "available": available,
            "attributes": raw_attrs,
        }

    def build_device_list(self) -> list[dict[str, Any]]:
        """Return device registry metadata extracted directly from the integration entities."""
        devices_by_serial: dict[str, dict[str, Any]] = {}
        for ent in self.entities.values():
            serial = getattr(ent, "_serial", None)
            if not serial or serial in devices_by_serial:
                continue
            dev_info = getattr(ent, "device_info", {}) or {}
            robot = getattr(ent, "_robot", None)
            devices_by_serial[serial] = {
                "serial": serial,
                "name": dev_info.get("name") or (robot.name if robot else serial),
                "manufacturer": dev_info.get("manufacturer", "Neato Robotics"),
                "model": dev_info.get("model", "BotVacConnected"),
                "sw_version": dev_info.get("sw_version", "4.5.3"),
                "connected": bool(robot.connected) if robot else False,
                "installed_with": robot.installed_with if robot else None,
            }
        return list(devices_by_serial.values())

    def build_entity_inspector_list(self) -> list[dict[str, Any]]:
        """Return rich metadata for all instantiated integration entities."""
        if self.entities:
            return [
                self._serialize_real_entity(eid, ent)
                for eid, ent in self.entities.items()
            ]
        # Fallback if running without homeassistant installed
        states = self.build_hass_states()
        return [
            {
                "entity_id": eid,
                "domain": eid.split(".")[0],
                "class_name": "VacuulaControllerFallback",
                "unique_id": eid,
                "serial": st.get("attributes", {}).get("serial", ""),
                "state": st["state"],
                "available": st["state"] != "unavailable",
                "attributes": st["attributes"],
            }
            for eid, st in states.items()
        ]

    def build_hass_states(self) -> dict[str, dict[str, Any]]:
        """Return Home Assistant `hass.states` dictionary from real integration entities."""
        if self.entities:
            result: dict[str, dict[str, Any]] = {}
            for eid, ent in self.entities.items():
                serialized = self._serialize_real_entity(eid, ent)
                result[eid] = {
                    "entity_id": eid,
                    "state": serialized["state"],
                    "attributes": serialized["attributes"],
                }
            return result

        # Pure-Python fallback when homeassistant is not installed
        if not self.controller:
            return {}
        states: dict[str, dict[str, Any]] = {}
        min_ver = self.controller.server_info.get("min_installer_version", "1.1.0-b3")

        for serial, robot in self.controller.robots.items():
            slug = _slugify(robot.name)
            snap = robot.to_snapshot(min_installer_version=min_ver)
            is_gen3 = robot.robot_type == ROBOT_TYPE_GEN3
            fan_list = FAN_SPEEDS_GEN3 if is_gen3 else FAN_SPEEDS_GEN4
            nav_list = GEN3_NAV_MODES if is_gen3 else GEN4_NAV_MODES

            last_area = float((robot.last_run or {}).get("cleaned_area") or 0.0)
            alert_val = snap["alert"] or snap["error"] or "none"
            is_bin = any(
                k in str(alert_val).lower() for k in ("dustbin", "bin_full", "lid_open")
            )

            states[f"vacuum.{slug}"] = {
                "entity_id": f"vacuum.{slug}",
                "state": snap["activity"] if robot.connected else "unavailable",
                "attributes": {
                    "friendly_name": robot.name,
                    "serial": serial,
                    "robot_type": robot.robot_type,
                    "fan_speed": snap["fan_speed"],
                    "fan_speed_list": fan_list,
                    "navigation_mode": snap["navigation_mode"],
                    "action": snap["action"],
                    "alert": snap["alert"],
                    "error": snap["error"],
                    "active_map_id": snap["active_map_id"],
                    "active_map_name": snap["active_map_name"],
                    "selected_zone": snap["selected_zone"],
                    "installed_with": snap["installed_with"],
                    "outdated_installer": snap["installer_outdated"],
                    "supported_features": 14204,
                },
            }
            states[f"image.{slug}_floor_map"] = {
                "entity_id": f"image.{slug}_floor_map",
                "state": "2026-10-26T09:00:00Z" if robot.floormap else "unavailable",
                "attributes": {
                    "friendly_name": f"{robot.name} Floor map",
                    "serial": serial,
                    "map_id": snap["active_map_id"],
                    "map_name": snap["active_map_name"],
                    "zones": snap["zones"],
                    "entity_picture": f"/api/sandbox/map/{serial}/floor.png?t={self._map_cache_buster}",
                },
            }
            states[f"image.{slug}_last_run_map"] = {
                "entity_id": f"image.{slug}_last_run_map",
                "state": "2026-10-26T09:34:00Z" if robot.last_runmap else "unavailable",
                "attributes": {
                    "friendly_name": f"{robot.name} Last run map",
                    "serial": serial,
                    "run_id": robot.last_run_id,
                    "entity_picture": f"/api/sandbox/map/{serial}/run.png?t={self._map_cache_buster}",
                },
            }
            states[f"sensor.{slug}_battery"] = {
                "entity_id": f"sensor.{slug}_battery",
                "state": str(snap["battery_level"] or 0),
                "attributes": {"unit_of_measurement": "%", "device_class": "battery"},
            }
            states[f"binary_sensor.{slug}_charging"] = {
                "entity_id": f"binary_sensor.{slug}_charging",
                "state": "on" if snap["is_charging"] else "off",
                "attributes": {},
            }
            states[f"binary_sensor.{slug}_dust_bin_full"] = {
                "entity_id": f"binary_sensor.{slug}_dust_bin_full",
                "state": "on" if is_bin else "off",
                "attributes": {"alert": snap["alert"]},
            }
            states[f"sensor.{slug}_alert"] = {
                "entity_id": f"sensor.{slug}_alert",
                "state": str(alert_val),
                "attributes": {},
            }
            states[f"sensor.{slug}_last_clean_area"] = {
                "entity_id": f"sensor.{slug}_last_clean_area",
                "state": f"{last_area:.1f}",
                "attributes": {"unit_of_measurement": "m²"},
            }
            states[f"sensor.{slug}_last_clean_duration"] = {
                "entity_id": f"sensor.{slug}_last_clean_duration",
                "state": "34.0",
                "attributes": {"unit_of_measurement": "min"},
            }
            states[f"select.{slug}_navigation_mode"] = {
                "entity_id": f"select.{slug}_navigation_mode",
                "state": snap["navigation_mode"],
                "attributes": {"options": nav_list},
            }
            states[f"switch.{slug}_schedule"] = {
                "entity_id": f"switch.{slug}_schedule",
                "state": "on" if snap["schedule_enabled"] else "off",
                "attributes": {},
            }
            states[f"button.{slug}_dismiss_alert"] = {
                "entity_id": f"button.{slug}_dismiss_alert",
                "state": "2026-10-26T00:00:00Z",
                "attributes": {},
            }
            states[f"button.{slug}_refresh_maps"] = {
                "entity_id": f"button.{slug}_refresh_maps",
                "state": "2026-10-26T00:00:00Z",
                "attributes": {},
            }
        return states

    def _resolve_robot(self, data: dict[str, Any]) -> VacuulaRobotData | None:
        """Resolve target robot from serial or entity_id."""
        robots = self._get_robots_dict()
        if not robots:
            return None
        serial = data.get("serial")
        if serial and serial in robots:
            return robots[serial]
        entity_id = data.get("entity_id")
        if isinstance(entity_id, list) and entity_id:
            entity_id = entity_id[0]
        if isinstance(entity_id, str):
            if entity_id in self.entities:
                ent_serial = getattr(self.entities[entity_id], "_serial", None)
                if ent_serial and ent_serial in robots:
                    return robots[ent_serial]
            for rob in robots.values():
                slug = _slugify(rob.name)
                if entity_id.startswith(f"vacuum.{slug}") or f".{slug}_" in entity_id:
                    return rob
        return next(iter(robots.values()))

    async def _async_refresh_runtime(self) -> None:
        """Refresh the active integration coordinator or fallback controller."""
        if self.coordinator is not None:
            self.coordinator.data = await self.coordinator._async_update_data()  # noqa: SLF001
            self.coordinator.last_update_success = True
            self._on_coordinator_update()
        elif self.controller is not None:
            await self.controller.async_refresh_all()

    async def _handle_favicon(self, _request: web.Request) -> web.Response:
        """Return an inline SVG favicon so browsers do not log 404 errors."""
        svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><circle cx="32" cy="32" r="28" fill="#1e293b" stroke="#38bdf8" stroke-width="4"/><circle cx="32" cy="32" r="10" fill="#38bdf8"/></svg>'
        return web.Response(text=svg, content_type="image/svg+xml")

    async def _handle_card_js(self, _request: web.Request) -> web.Response:
        """Serve custom_components/vacuula/frontend/vacuula-map-card.js directly from disk."""
        content = CARD_JS_PATH.read_text(encoding="utf-8")
        return web.Response(
            text=content,
            content_type="application/javascript",
            headers={"Cache-Control": "no-store"},
        )

    async def _handle_get_states(self, _request: web.Request) -> web.Response:
        """Poll runtime and return current hass.states, entities, and devices."""
        await self._async_refresh_runtime()
        return web.json_response(
            {
                "states": self.build_hass_states(),
                "entities": self.build_entity_inspector_list(),
                "devices": self.build_device_list(),
                "server_info": self._get_server_info(),
            }
        )

    async def _handle_sse_events(self, request: web.Request) -> web.StreamResponse:
        """Stream real-time state updates to the browser over Server-Sent Events."""
        response = web.StreamResponse(
            status=200,
            reason="OK",
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )
        await response.prepare(request)
        q: asyncio.Queue[str] = asyncio.Queue(maxsize=25)
        self._sse_Queues.add(q)
        try:
            initial = json.dumps(
                {
                    "states": self.build_hass_states(),
                    "entities": self.build_entity_inspector_list(),
                    "devices": self.build_device_list(),
                    "server_info": self._get_server_info(),
                }
            )
            await response.write(f"data: {initial}\n\n".encode())
            while True:
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=15.0)
                    await response.write(f"data: {msg}\n\n".encode())
                except TimeoutError:
                    await response.write(b": keepalive\n\n")
        except ConnectionResetError, asyncio.CancelledError, OSError:
            pass
        finally:
            self._sse_Queues.discard(q)
        return response

    def _ensure_mock_robot_connected(self, serial: str | None) -> None:
        """Ensure mock robot is connected unless explicitly disconnected by the user."""
        if not self.server_manager or not self.server_manager._robots:  # noqa: SLF001
            return
        for r in self.server_manager._robots:  # noqa: SLF001
            if serial and r.serial != serial:
                continue
            if not r.is_connected and not getattr(r, "_user_disconnected", False):
                r.connect(self.server_manager.host, self.server_manager.port)

    async def _handle_call_service(self, request: web.Request) -> web.Response:
        """Execute a Home Assistant service call through the real integration entities."""
        if not self.client:
            return web.json_response({"error": "Not initialized"}, status=500)

        payload = await request.json()
        domain = str(payload.get("domain", ""))
        service = str(payload.get("service", ""))
        data = payload.get("service_data") or {}
        target_eid = data.get("entity_id")
        if isinstance(target_eid, list) and target_eid:
            target_eid = target_eid[0]

        ent = self.entities.get(str(target_eid)) if target_eid else None
        ent_serial = getattr(ent, "_serial", None) if ent is not None else None
        self._ensure_mock_robot_connected(ent_serial)

        error_msg: str | None = None
        try:
            # 1. Dispatch directly to real integration Entity object if present
            if ent is not None and domain in ("vacuum", "select", "switch", "button"):
                if domain == "vacuum":
                    if service == "start":
                        await ent.async_start()
                    elif service == "pause":
                        await ent.async_pause()
                    elif service == "stop":
                        await ent.async_stop()
                    elif service == "return_to_base":
                        await ent.async_return_to_base()
                    elif service == "locate":
                        await ent.async_locate()
                    elif service == "set_fan_speed":
                        await ent.async_set_fan_speed(
                            str(data.get("fan_speed", "turbo"))
                        )
                elif domain == "select" and service == "select_option":
                    await ent.async_select_option(str(data.get("option", "")))
                elif domain == "switch":
                    if service == "turn_on":
                        await ent.async_turn_on()
                    elif service == "turn_off":
                        await ent.async_turn_off()
                    elif service == "toggle":
                        if getattr(ent, "is_on", False):
                            await ent.async_turn_off()
                        else:
                            await ent.async_turn_on()
                elif domain == "button" and service == "press":
                    await ent.async_press()

                self._on_coordinator_update()
                return web.json_response(
                    {
                        "states": self.build_hass_states(),
                        "entities": self.build_entity_inspector_list(),
                        "devices": self.build_device_list(),
                    }
                )

            # 2. Domain-level custom services (vacuula.clean_zones, vacuula.clean_spot, vacuula.refresh_maps)
            robot = self._resolve_robot(data)
            if not robot:
                return web.json_response({"error": "No robot found"}, status=404)

            self._ensure_mock_robot_connected(robot.serial)
            resp: dict[str, Any] | None = None
            if domain == "vacuula":
                if service == "clean_zones":
                    raw_zones = data.get("zones", [])
                    zone_list = (
                        [z.strip() for z in raw_zones.split(",") if z.strip()]
                        if isinstance(raw_zones, str)
                        else [str(z) for z in raw_zones]
                    )
                    zone_ids = robot.resolve_zone_ids(zone_list)
                    map_id = data.get("map_id") or robot.active_map_id or "map-floor-1"
                    resp = await self.client.async_start_zone_cleaning(
                        robot.serial,
                        robot.robot_type,
                        map_id,
                        zone_ids,
                        fan_speed=data.get("fan_speed") or robot.preferred_fan_speed,
                        navigation_mode=data.get("navigation_mode")
                        or robot.preferred_navigation_mode,
                    )
                elif service == "clean_spot":
                    resp = await self.client.async_start_spot_cleaning(
                        robot.serial,
                        robot.robot_type,
                        width=int(data.get("width", 200)),
                        height=int(data.get("height", 200)),
                        fan_speed=data.get("fan_speed") or robot.preferred_fan_speed,
                        navigation_mode=data.get("navigation_mode")
                        or robot.preferred_navigation_mode,
                    )
                elif service == "refresh_maps":
                    if self.coordinator is not None:
                        await self.coordinator.async_refresh_maps_and_runs(robot.serial)
                    elif self.controller is not None:
                        await self.controller.async_refresh_maps_and_runs(robot.serial)
                    self._map_cache_buster = int(time.time() * 1000)

            if resp is not None:
                if self.coordinator is not None:
                    await self.coordinator.async_apply_command_response(
                        robot.serial, resp
                    )
                elif self.controller is not None:
                    await self.controller.async_apply_command_response(
                        robot.serial, resp
                    )
        except Exception as err:  # noqa: BLE001
            logger.warning(
                "Sandbox service call %s.%s failed: %s", domain, service, err
            )
            error_msg = str(err)

        self._on_coordinator_update()
        return web.json_response(
            {
                "error": error_msg,
                "states": self.build_hass_states(),
                "entities": self.build_entity_inspector_list(),
                "devices": self.build_device_list(),
            }
        )

    async def _handle_mock_robot(self, request: web.Request) -> web.Response:
        """Manipulate the underlying MockNeatoRobot hardware state directly from the sandbox UI."""
        payload = await request.json()
        action = str(payload.get("action", ""))
        value = payload.get("value")
        serial = payload.get("serial")

        if self.server_manager and self.server_manager._robots:  # noqa: SLF001
            mock_bot = next(
                (r for r in self.server_manager._robots if r.serial == serial),  # noqa: SLF001
                self.server_manager._robots[0],  # noqa: SLF001
            )
            if action not in ("disconnect", "reconnect", "add_robot"):
                self._ensure_mock_robot_connected(mock_bot.serial)

            if action == "alert":
                mock_bot.set_alert(str(value) if value else None)
            elif action == "error":
                mock_bot.set_error(str(value) if value else None)
            elif action == "clear":
                mock_bot.set_alert(None)
                mock_bot.set_error(None)
            elif action == "battery":
                charging = (
                    bool(payload["charging"])
                    if "charging" in payload
                    else mock_bot.is_charging
                )
                mock_bot.set_battery(int(value), is_charging=charging)
            elif action == "charging":
                mock_bot.set_battery(mock_bot.charge, is_charging=bool(value))
            elif action == "dock":
                mock_bot.set_docked(True if value is None else bool(value))
            elif action == "dock_seen":
                mock_bot.set_dock_seen(bool(value))
            elif action == "schedule":
                mock_bot.set_schedule(bool(value))
            elif action == "clean":
                cat = int(payload.get("category", 4))
                act = 11 if cat == 4 else (2 if cat == 3 else 1)
                mock_bot.set_cleaning(action=act, category=cat)
            elif action == "spot":
                mock_bot.set_cleaning(action=2, category=3)
            elif action == "house_clean":
                mock_bot.set_cleaning(action=1, category=2)
            elif action == "explore":
                mock_bot.set_exploring()
            elif action == "pause":
                mock_bot.set_paused()
            elif action == "resume":
                mock_bot.set_cleaning(action=mock_bot.action or 11)
            elif action == "stop":
                mock_bot.set_idle()
            elif action == "finish_run":
                mock_bot.finish_cleaning_run()
                self._map_cache_buster = int(time.time() * 1000)
            elif action == "installer_version":
                mock_bot.installer_version = str(value or "1.1.0-b3")
                await asyncio.get_running_loop().run_in_executor(
                    None,
                    lambda: mock_bot.link(
                        self.server_manager.host,  # type: ignore[union-attr]
                        self.server_manager.port,  # type: ignore[union-attr]
                    ),
                )
            elif action == "disconnect":
                mock_bot._user_disconnected = True  # type: ignore[attr-defined]  # noqa: SLF001
                mock_bot.disconnect()
                await asyncio.sleep(0.05)
            elif action == "reconnect":
                mock_bot._user_disconnected = False  # type: ignore[attr-defined]  # noqa: SLF001
                mock_bot.connect(self.server_manager.host, self.server_manager.port)
                await asyncio.sleep(0.05)
            elif action == "add_robot":
                idx = len(self.server_manager._robots) + 1  # noqa: SLF001
                new_serial = f"OPS{idx:05d}-0011223344{idx:02d}"
                new_name = str(value or f"Upstairs Bot #{idx}")
                await asyncio.get_running_loop().run_in_executor(
                    None,
                    lambda: self.server_manager.add_mock_robot(  # type: ignore[union-attr]
                        serial=new_serial, name=new_name
                    ),
                )

            # Immediately mirror mock_bot state into coordinator data for zero-latency UI response
            if (
                self.coordinator is not None
                and self.coordinator.data
                and mock_bot.serial in self.coordinator.data
            ):
                coord_bot = self.coordinator.data[mock_bot.serial]
                coord_bot.connected = mock_bot.is_connected
                coord_bot.installed_with = mock_bot.installer_version
                if mock_bot.is_connected:
                    coord_bot.state = mock_bot._build_state_response("0")  # noqa: SLF001
                    coord_bot.sync_preferences_from_state()

        await self._async_refresh_runtime()
        return web.json_response(
            {
                "states": self.build_hass_states(),
                "entities": self.build_entity_inspector_list(),
                "devices": self.build_device_list(),
            }
        )

    async def _handle_map_png(self, request: web.Request) -> web.Response:
        """Render and serve the floor map or last run map PNG via real ImageEntity or map_renderer."""
        serial = request.match_info["serial"]
        kind = request.match_info["kind"]

        # First try the real VacuulaFloorMapImage / VacuulaLastRunMapImage entity
        for eid, ent in self.entities.items():
            if (
                self._entity_domains.get(eid) == "image"
                and getattr(ent, "_serial", None) == serial
            ):
                is_run = "last_run" in eid
                if (kind == "run" and is_run) or (kind != "run" and not is_run):
                    png_bytes = await ent.async_image()
                    if png_bytes:
                        return web.Response(
                            body=png_bytes,
                            content_type="image/png",
                            headers={"Cache-Control": "no-store"},
                        )

        robots = self._get_robots_dict()
        if serial not in robots:
            return web.Response(status=404, text="Robot not found")

        robot = robots[serial]
        png = (
            render_map_png(robot.floormap, robot.boundaries, runmap=robot.last_runmap)
            if kind == "run"
            else render_map_png(robot.floormap, robot.boundaries)
        )
        if not png:
            return web.Response(status=404, text="Map not available")
        return web.Response(
            body=png,
            content_type="image/png",
            headers={"Cache-Control": "no-store"},
        )

    async def _handle_index(self, _request: web.Request) -> web.Response:
        """Serve the Full-Stack Lovelace + Integration Entity Inspector HTML dashboard."""
        html = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Vacuula Full-Stack Developer Environment (Lovelace + Mock Entities)</title>
  <script type="module" src="/vacuula_frontend/vacuula-map-card.js"></script>
  <style>
    :root {
      color-scheme: dark;
      --primary-background-color: #0b1120;
      --card-background-color: #1e222b;
      --ha-card-background: #1e222b;
      --primary-text-color: #f8fafc;
      --secondary-text-color: #94a3b8;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      padding: 20px 24px;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: #0b1120;
      color: #f8fafc;
    }
    .topbar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 12px;
      margin-bottom: 18px;
      padding-bottom: 14px;
      border-bottom: 1px solid rgba(148, 163, 184, 0.16);
    }
    .topbar h1 {
      margin: 0;
      font-size: 1.25rem;
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .pill {
      font-size: 0.74rem;
      background: rgba(56, 189, 248, 0.15);
      color: #38bdf8;
      border: 1px solid rgba(56, 189, 248, 0.35);
      padding: 4px 10px;
      border-radius: 999px;
      font-weight: 600;
    }
    .pill.green {
      background: rgba(74, 222, 128, 0.15);
      color: #4ade80;
      border-color: rgba(74, 222, 128, 0.35);
    }
    .robot-tabs {
      display: flex;
      gap: 8px;
      margin-bottom: 16px;
      flex-wrap: wrap;
    }
    .robot-tab {
      background: #161b26;
      color: #cbd5e1;
      border: 1px solid rgba(148, 163, 184, 0.2);
      border-radius: 10px;
      padding: 8px 14px;
      font-size: 0.85rem;
      font-weight: 600;
      cursor: pointer;
    }
    .robot-tab.active {
      background: rgba(56, 189, 248, 0.18);
      color: #38bdf8;
      border-color: #38bdf8;
    }
    .workspace {
      display: grid;
      grid-template-columns: minmax(420px, 1.25fr) minmax(360px, 1fr) 340px;
      gap: 20px;
      align-items: start;
    }
    @media (max-width: 1280px) {
      .workspace { grid-template-columns: 1fr 1fr; }
    }
    @media (max-width: 860px) {
      .workspace { grid-template-columns: 1fr; }
    }
    .panel {
      background: #161b26;
      border: 1px solid rgba(148, 163, 184, 0.14);
      border-radius: 16px;
      padding: 16px;
      margin-bottom: 16px;
    }
    .panel-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 12px;
    }
    .panel h2 {
      margin: 0;
      font-size: 0.88rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: #94a3b8;
    }
    .device-box {
      background: #0f172a;
      border: 1px solid rgba(148, 163, 184, 0.14);
      border-radius: 12px;
      padding: 12px;
      margin-bottom: 14px;
      font-size: 0.82rem;
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 6px 12px;
    }
    .device-box div span { color: #64748b; }
    .entity-group-title {
      font-size: 0.76rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: #38bdf8;
      margin: 12px 0 6px;
    }
    .entity-list {
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    .entity-row {
      background: #0f172a;
      border: 1px solid rgba(148, 163, 184, 0.12);
      border-radius: 10px;
      padding: 8px 11px;
      font-size: 0.82rem;
    }
    .entity-row-main {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 8px;
    }
    .entity-meta {
      display: flex;
      flex-direction: column;
      gap: 2px;
      min-width: 0;
    }
    .entity-name {
      font-weight: 600;
      color: #f1f5f9;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .entity-id {
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 0.72rem;
      color: #64748b;
    }
    .entity-ctrl {
      display: flex;
      align-items: center;
      gap: 6px;
      flex-shrink: 0;
    }
    .state-badge {
      padding: 3px 8px;
      border-radius: 6px;
      font-weight: 600;
      font-size: 0.76rem;
      background: rgba(148, 163, 184, 0.14);
      color: #e2e8f0;
    }
    .state-badge.on, .state-badge.cleaning, .state-badge.docked {
      background: rgba(56, 189, 248, 0.18);
      color: #38bdf8;
    }
    .state-badge.error {
      background: rgba(239, 68, 68, 0.2);
      color: #f87171;
    }
    .btn-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
      margin-bottom: 14px;
    }
    button.sim-btn, button.ent-btn, select.ent-select {
      background: #1e293b;
      color: #e2e8f0;
      border: 1px solid rgba(148, 163, 184, 0.24);
      border-radius: 8px;
      padding: 6px 10px;
      font-size: 0.78rem;
      cursor: pointer;
      transition: background 0.15s;
    }
    button.sim-btn:hover, button.ent-btn:hover { background: #334155; }
    details.attr-details {
      margin-top: 5px;
      font-size: 0.72rem;
      color: #94a3b8;
    }
    details.attr-details summary {
      cursor: pointer;
      color: #64748b;
    }
    pre {
      margin: 4px 0 0;
      padding: 8px;
      background: #090d16;
      border-radius: 8px;
      font-size: 0.72rem;
      max-height: 300px;
      overflow: auto;
      color: #cbd5e1;
    }
  </style>
</head>
<body>
  <div class="topbar">
    <h1>
      <span>🤖 Vacuula Full-Stack Developer Environment</span>
      <span class="pill">Lovelace Frontend</span>
      <span class="pill green" id="entity-count-pill">Loading Entities...</span>
    </h1>
    <div id="server-meta" style="font-size: 0.83rem; color: #94a3b8;">Connecting to Vacuula Server...</div>
  </div>

  <div class="robot-tabs" id="robot-tabs"></div>

  <div class="workspace">
    <!-- Column 1: Live Lovelace Frontend Card & Visual Config Editor -->
    <div>
      <div class="panel">
        <div class="panel-header">
          <h2>Lovelace Dashboard (<code style="color:#38bdf8">vacuula-map-card</code>)</h2>
          <button class="ent-btn" onclick="toggleEditor()">⚙️ Toggle Card Editor</button>
        </div>
        <vacuula-map-card id="map-card"></vacuula-map-card>
      </div>

      <div class="panel" id="editor-panel" style="display:none;">
        <div class="panel-header">
          <h2>Lovelace Card Config Editor (<code style="color:#38bdf8">vacuula-map-card-editor</code>)</h2>
        </div>
        <vacuula-map-card-editor id="map-card-editor"></vacuula-map-card-editor>
      </div>
    </div>

    <!-- Column 2: Live Integration Device & Mock Entities Inspector -->
    <div>
      <div class="panel">
        <div class="panel-header">
          <h2>Integration Device & Entities (<code style="color:#38bdf8">custom_components/vacuula</code>)</h2>
          <button class="ent-btn" onclick="refreshAll()">↻ Refresh</button>
        </div>
        <div id="device-info-container"></div>
        <div id="entities-container"></div>
      </div>
    </div>

    <!-- Column 3: Developer Event & Scenario Studio -->
    <div>
      <div class="panel">
        <div class="panel-header">
          <h2>⚡ Developer Event & Scenario Studio</h2>
          <button class="ent-btn" style="background:#065f46;border-color:#10b981;" onclick="sim('clear')">✅ Clear Alerts/Errors</button>
        </div>

        <div class="entity-group-title" style="margin-top:0;">1. Cleaning & Lifecycle States</div>
        <div class="btn-grid">
          <button class="sim-btn" onclick="sim('clean', null, false, {category: 4})">🗺️ Map/Zone Clean</button>
          <button class="sim-btn" onclick="sim('house_clean')">▶️ House Clean</button>
          <button class="sim-btn" onclick="sim('spot')">🎯 Spot Clean</button>
          <button class="sim-btn" onclick="sim('explore')">🧭 Explore Map</button>
          <button class="sim-btn" onclick="sim('pause')">⏸️ Pause Clean</button>
          <button class="sim-btn" onclick="sim('stop')">⏹️ Stop (Idle)</button>
          <button class="sim-btn" onclick="sim('dock', true)">🏠 Dock Robot</button>
          <button class="sim-btn" onclick="sim('finish_run')">🏁 Complete Run</button>
        </div>

        <div class="entity-group-title">2. Trigger Hardware Alerts (Yellow Banner)</div>
        <div class="btn-grid">
          <button class="sim-btn" onclick="sim('alert', 'dustbin_full')">🗑️ Dustbin Full</button>
          <button class="sim-btn" onclick="sim('alert', 'dustbin_missing')">📥 Bin Missing</button>
          <button class="sim-btn" onclick="sim('alert', 'maint_brush_change')">🧹 Change Brush</button>
          <button class="sim-btn" onclick="sim('alert', 'maint_filter_change')">🌬️ Change Filter</button>
          <button class="sim-btn" onclick="sim('alert', 'clear_path')">🚧 Clear Path</button>
          <button class="sim-btn" onclick="sim('alert', 'nav_floorplan_not_created')">🗺️ No Floorplan</button>
        </div>

        <div class="entity-group-title">3. Trigger Hardware Errors (Red Error State)</div>
        <div class="btn-grid">
          <button class="sim-btn" onclick="sim('error', 'ui_error_brush_stuck')">⚠️ Brush Stuck</button>
          <button class="sim-btn" onclick="sim('error', 'ui_error_Brush_overload')">⚡ Brush Overload</button>
          <button class="sim-btn" onclick="sim('error', 'ui_error_navigation_stuck')">🛑 Robot Stuck</button>
          <button class="sim-btn" onclick="sim('error', 'ui_error_bumper_stuck')">🧱 Bumper Stuck</button>
          <button class="sim-btn" onclick="sim('error', 'ui_error_picked_up')">🙋 Picked Up</button>
          <button class="sim-btn" onclick="sim('error', 'ui_error_undock_failed')">🚪 Undock Failed</button>
        </div>

        <div style="display:flex;gap:6px;margin-bottom:14px;">
          <input id="custom-code-input" type="text" placeholder="Custom alert/error code..." style="flex:1;background:#0f172a;color:#f8fafc;border:1px solid rgba(148,163,184,0.25);border-radius:8px;padding:6px 10px;font-size:0.78rem;" />
          <button class="ent-btn" onclick="sim('alert', document.getElementById('custom-code-input').value)">Alert</button>
          <button class="ent-btn" onclick="sim('error', document.getElementById('custom-code-input').value)">Error</button>
        </div>

        <div class="entity-group-title">4. Battery, Sensors & Connectivity</div>
        <div style="background:#0f172a;border:1px solid rgba(148,163,184,0.14);border-radius:10px;padding:10px;margin-bottom:12px;">
          <div style="display:flex;justify-content:space-between;font-size:0.8rem;margin-bottom:6px;">
            <span>🔋 Battery Level: <strong id="batt-label">95%</strong></span>
            <label style="cursor:pointer;"><input type="checkbox" id="chg-toggle" onchange="sim('charging', this.checked)" /> ⚡ Charging</label>
          </div>
          <input type="range" id="batt-slider" min="0" max="100" value="95" style="width:100%;" oninput="document.getElementById('batt-label').textContent = this.value + '%'" onchange="sim('battery', Number(this.value), document.getElementById('chg-toggle').checked)" />
          <div style="display:flex;gap:6px;margin-top:8px;flex-wrap:wrap;">
            <button class="ent-btn" onclick="setBattPreset(12, false)">12% Low</button>
            <button class="ent-btn" onclick="setBattPreset(45, true)">45% Chg</button>
            <button class="ent-btn" onclick="setBattPreset(100, false)">100% Full</button>
          </div>
        </div>

        <div class="btn-grid">
          <button class="sim-btn" onclick="sim('dock_seen', true)">👀 Dock Seen: ON</button>
          <button class="sim-btn" onclick="sim('dock_seen', false)">🙈 Dock Seen: OFF</button>
          <button class="sim-btn" onclick="sim('installer_version', '1.0.0-b28')">⚠️ Outdated Installer</button>
          <button class="sim-btn" onclick="sim('installer_version', '1.1.0-b3')">✅ Latest Installer</button>
          <button class="sim-btn" onclick="sim('disconnect')">📡 Drop WiFi (Away)</button>
          <button class="sim-btn" onclick="sim('reconnect')">📶 Reconnect WiFi</button>
        </div>
        <button class="sim-btn" style="width:100%;margin-bottom:8px;" onclick="sim('add_robot', 'Upstairs D7')">➕ Spawn & Connect 2nd Mock Neato Robot</button>

        <div class="panel-header" style="margin-top:12px;">
          <h2>Live Action & SSE Stream Log</h2>
        </div>
        <pre id="service-log">Waiting for events...</pre>
      </div>
    </div>
  </div>

  <script>
    const card = document.getElementById("map-card");
    const editor = document.getElementById("map-card-editor");
    const editorPanel = document.getElementById("editor-panel");
    const logEl = document.getElementById("service-log");
    const metaEl = document.getElementById("server-meta");
    const pillEl = document.getElementById("entity-count-pill");
    const tabsEl = document.getElementById("robot-tabs");
    const devContainer = document.getElementById("device-info-container");
    const entContainer = document.getElementById("entities-container");

    let activeSerial = null;
    let cardConfig = null;
    let latestData = { states: {}, entities: [], devices: [], server_info: {} };

    function logMsg(msg) {
      const ts = new Date().toLocaleTimeString();
      logEl.textContent = `[${ts}] ${msg}\\n` + logEl.textContent.slice(0, 3000);
    }

    window.toggleEditor = () => {
      editorPanel.style.display = editorPanel.style.display === "none" ? "block" : "none";
    };

    const mockHass = {
      states: {},
      callService: async (domain, service, serviceData) => {
        logMsg(`callService: ${domain}.${service} ${JSON.stringify(serviceData || {})}`);
        const res = await fetch("/api/sandbox/call_service", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ domain, service, service_data: serviceData }),
        });
        const data = await res.json();
        if (data.error) {
          logMsg(`⚠️ service error: ${data.error}`);
        }
        if (data.states) applyPayload(data);
      },
    };

    editor.addEventListener("config-changed", (ev) => {
      if (ev.detail && ev.detail.config) {
        cardConfig = ev.detail.config;
        card.setConfig(cardConfig);
        card.hass = { ...mockHass, states: latestData.states };
        editor.setConfig(cardConfig);
        logMsg(`card config updated: ${JSON.stringify(cardConfig)}`);
      }
    });

    function selectRobot(serial) {
      activeSerial = serial;
      const vacEnt = latestData.entities.find(
        (e) => e.domain === "vacuum" && e.serial === serial
      );
      if (vacEnt) {
        cardConfig = {
          ...(cardConfig || { map_height: "large", expand_on_desktop: true }),
          entity: vacEnt.entity_id,
        };
        card.setConfig(cardConfig);
        card.hass = { ...mockHass, states: latestData.states };
        editor.hass = { ...mockHass, states: latestData.states };
        editor.setConfig(cardConfig);
      }
      renderInspector();
    }
    window.selectRobot = selectRobot;

    function renderInspector() {
      const devices = latestData.devices || [];
      const entities = latestData.entities || [];
      if (!activeSerial && devices.length > 0) {
        activeSerial = devices[0].serial;
      }

      // Render robot switcher tabs
      tabsEl.innerHTML = devices
        .map(
          (d) =>
            `<button class="robot-tab ${d.serial === activeSerial ? "active" : ""}" onclick="selectRobot('${d.serial}')">
              🤖 ${d.name} <span style="opacity:0.65;font-size:0.75rem;">(${d.serial})</span>
            </button>`
        )
        .join("");

      const dev = devices.find((d) => d.serial === activeSerial) || devices[0];
      if (dev) {
        devContainer.innerHTML = `
          <div class="device-box">
            <div><span>Device Name:</span> <strong>${dev.name}</strong></div>
            <div><span>Manufacturer:</span> <strong>${dev.manufacturer}</strong></div>
            <div><span>Model:</span> <strong>${dev.model}</strong></div>
            <div><span>Firmware:</span> <strong>${dev.sw_version}</strong></div>
            <div><span>Serial:</span> <code>${dev.serial}</code></div>
            <div><span>Installer:</span> <code>${dev.installed_with || "N/A"}</code></div>
          </div>
        `;
      }

      const robotEntities = entities.filter((e) => !activeSerial || e.serial === activeSerial);
      const groups = [
        { title: "Vacuum Entity", domains: ["vacuum"] },
        { title: "Interactive Controls (Select, Switch, Button)", domains: ["select", "switch", "button"] },
        { title: "Sensors & Diagnostics", domains: ["sensor", "binary_sensor"] },
        { title: "Map Camera / Image Entities", domains: ["image"] },
      ];

      entContainer.innerHTML = groups
        .map((g) => {
          const items = robotEntities.filter((e) => g.domains.includes(e.domain));
          if (!items.length) return "";
          const rows = items
            .map((e) => {
              let ctrlHtml = `<span class="state-badge ${e.state}">${e.state}${e.attributes.unit_of_measurement ? " " + e.attributes.unit_of_measurement : ""}</span>`;
              if (e.domain === "button") {
                ctrlHtml = `<button class="ent-btn" onclick="pressButton('${e.entity_id}')">Press</button>`;
              } else if (e.domain === "switch") {
                ctrlHtml = `<button class="ent-btn" onclick="toggleSwitch('${e.entity_id}')">${e.state === "on" ? "🟢 ON (Toggle)" : "⚪ OFF (Toggle)"}</button>`;
              } else if (e.domain === "select") {
                const opts = (e.attributes.options || [])
                  .map((o) => `<option value="${o}" ${o === e.state ? "selected" : ""}>${o}</option>`)
                  .join("");
                ctrlHtml = `<select class="ent-select" onchange="selectOption('${e.entity_id}', this.value)">${opts}</select>`;
              }
              return `
                <div class="entity-row">
                  <div class="entity-row-main">
                    <div class="entity-meta">
                      <span class="entity-name">${e.attributes.friendly_name || e.entity_id}</span>
                      <span class="entity-id">${e.entity_id} • <span style="color:#38bdf8">${e.class_name}</span></span>
                    </div>
                    <div class="entity-ctrl">${ctrlHtml}</div>
                  </div>
                  <details class="attr-details">
                    <summary>Attributes (${Object.keys(e.attributes || {}).length})</summary>
                    <pre>${JSON.stringify(e.attributes, null, 2)}</pre>
                  </details>
                </div>
              `;
            })
            .join("");
          return `<div class="entity-group-title">${g.title} (${items.length})</div><div class="entity-list">${rows}</div>`;
        })
        .join("");
    }

    window.pressButton = (entity_id) => mockHass.callService("button", "press", { entity_id });
    window.toggleSwitch = (entity_id) => mockHass.callService("switch", "toggle", { entity_id });
    window.selectOption = (entity_id, option) =>
      mockHass.callService("select", "select_option", { entity_id, option });

    function applyPayload(data) {
      latestData = { ...latestData, ...data };
      const states = latestData.states || {};
      mockHass.states = states;

      const count = (latestData.entities || []).length || Object.keys(states).length;
      pillEl.textContent = `${count} Live Integration Entities`;

      if (!activeSerial && latestData.devices && latestData.devices.length > 0) {
        activeSerial = latestData.devices[0].serial;
      }

      const vacId =
        Object.keys(states).find(
          (k) => k.startsWith("vacuum.") && (!activeSerial || states[k].attributes?.serial === activeSerial)
        ) || Object.keys(states).find((k) => k.startsWith("vacuum."));

      if (vacId && (!cardConfig || cardConfig.entity !== vacId)) {
        cardConfig = {
          entity: vacId,
          map_height: "large",
          expand_on_desktop: true,
        };
        card.setConfig(cardConfig);
        editor.setConfig(cardConfig);
      }
      card.hass = { ...mockHass, states };
      editor.hass = { ...mockHass, states };

      if (latestData.server_info && latestData.server_info.version) {
        metaEl.textContent = `Vacuula Server v${latestData.server_info.version} • SSE Connected • Python 3.14`;
      }
      renderInspector();
    }

    window.refreshAll = async () => {
      const res = await fetch("/api/sandbox/states");
      const data = await res.json();
      applyPayload(data);
    };

    window.setBattPreset = (pct, chg) => {
      const slider = document.getElementById("batt-slider");
      const label = document.getElementById("batt-label");
      const chgEl = document.getElementById("chg-toggle");
      if (slider) slider.value = String(pct);
      if (label) label.textContent = pct + "%";
      if (chgEl) chgEl.checked = Boolean(chg);
      window.sim("battery", pct, chg);
    };

    window.sim = async (action, value = null, charging = false, extra = {}) => {
      logMsg(`event trigger [${activeSerial || "default"}]: ${action}${value !== null ? "=" + value : ""}`);
      const res = await fetch("/api/sandbox/mock_robot", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ serial: activeSerial, action, value, charging, ...extra }),
      });
      const data = await res.json();
      applyPayload(data);
    };

    // Connect real-time SSE stream from Sandbox -> Browser
    const es = new EventSource("/api/sandbox/events");
    es.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data);
        applyPayload(data);
      } catch (e) {
        console.error(e);
      }
    };
    es.onerror = () => {
      // Fallback poll if SSE reconnects
      setTimeout(window.refreshAll, 2000);
    };
  </script>
</body>
</html>
"""
        return web.Response(text=html, content_type="text/html")
