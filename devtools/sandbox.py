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
from pathlib import Path
from typing import Any

# Pre-import homeassistant before voluptuous so probatio's install_as_voluptuous()
# never emits a RuntimeWarning.
with contextlib.suppress(ImportError):
    import homeassistant  # noqa: F401

import aiohttp
from aiohttp import web

from custom_components.vacuula.core import (
    VacuulaApiClient,
    VacuulaController,
    VacuulaRobotData,
    render_map_png,
)

from .server_manager import REPO_ROOT, VacuulaServerManager

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent / "static"
INDEX_HTML_PATH = STATIC_DIR / "index.html"
FAVICON_PATH = STATIC_DIR / "favicon.svg"
CARD_JS_PATH = (
    REPO_ROOT / "custom_components" / "vacuula" / "frontend" / "vacuula-map-card.js"
)
NO_STORE_HEADERS = {"Cache-Control": "no-store"}

_VACUUM_METHODS = frozenset({"start", "pause", "stop", "return_to_base", "locate"})


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

        self._mock_hass: _LightweightMockHass | None = None
        self._mock_entry: _LightweightMockConfigEntry | None = None
        self.coordinator: Any = None
        self.entities: dict[str, Any] = {}
        self._entity_domains: dict[str, str] = {}

        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None
        self._map_cache_buster: int = int(time.time() * 1000)
        self._sse_queues: set[asyncio.Queue[str]] = set()

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
        self.coordinator.data = await self.coordinator._async_update_data()  # noqa: SLF001
        self.coordinator.last_update_success = True

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

        self.coordinator.async_add_listener(self._on_coordinator_update)
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
        if platform_domain == "binary_sensor" and key == "bin_full":
            return f"binary_sensor.{robot_slug}_dust_bin_full"
        return f"{platform_domain}.{robot_slug}_{_slugify(key)}"

    def _build_state_payload(
        self,
        *,
        include_server_info: bool = False,
        error: str | None = None,
    ) -> dict[str, Any]:
        """Build the combined states, entities, and devices payload in a single pass."""
        entities = self.build_entity_inspector_list()
        states = {
            item["entity_id"]: {
                "entity_id": item["entity_id"],
                "state": item["state"],
                "attributes": item["attributes"],
            }
            for item in entities
        }
        payload: dict[str, Any] = {
            "states": states,
            "entities": entities,
            "devices": self.build_device_list(),
        }
        if include_server_info:
            payload["server_info"] = self._get_server_info()
        if error is not None:
            payload["error"] = error
        return payload

    def _on_coordinator_update(self) -> None:
        """Broadcast updated entity states to all connected browser SSE clients."""
        payload = json.dumps(self._build_state_payload(include_server_info=True))
        for q in list(self._sse_queues):
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

    def _create_web_app(self) -> web.Application:
        """Construct the aiohttp web.Application with static file and API routes."""
        app = web.Application()
        app.router.add_get("/", self._handle_index)
        app.router.add_get("/favicon.ico", self._handle_favicon)
        app.router.add_static("/static", STATIC_DIR, show_index=False)
        app.router.add_get(
            "/vacuula_frontend/vacuula-map-card.js", self._handle_card_js
        )
        app.router.add_get("/api/sandbox/states", self._handle_get_states)
        app.router.add_get("/api/sandbox/events", self._handle_sse_events)
        app.router.add_post("/api/sandbox/call_service", self._handle_call_service)
        app.router.add_post("/api/sandbox/mock_robot", self._handle_mock_robot)
        app.router.add_get("/api/sandbox/map/{serial}/{kind}.png", self._handle_map_png)
        return app

    async def async_start(self) -> None:
        """Start the aiohttp client, integration runtime, and sandbox web server."""
        self._session = aiohttp.ClientSession()
        self.client = VacuulaApiClient(self.vacuula_url, self._session)

        if not await self._setup_real_integration_entities():
            self.controller = VacuulaController(self.client)
            await self.controller.async_refresh_all()

        self._runner = web.AppRunner(self._create_web_app())
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
                if unit := getattr(ent, "native_unit_of_measurement", None):
                    raw_attrs["unit_of_measurement"] = str(unit)
                if dc := getattr(ent, "device_class", None):
                    raw_attrs["device_class"] = str(
                        dc.value if hasattr(dc, "value") else dc
                    )
            elif domain == "binary_sensor":
                is_on = getattr(ent, "is_on", None)
                state_val = "unknown" if is_on is None else ("on" if is_on else "off")
                if dc := getattr(ent, "device_class", None):
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

        if icon := (getattr(ent, "icon", None) or getattr(ent, "_attr_icon", None)):
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
        return [
            self._serialize_real_entity(eid, ent) for eid, ent in self.entities.items()
        ]

    def build_hass_states(self) -> dict[str, dict[str, Any]]:
        """Return Home Assistant `hass.states` dictionary from real integration entities."""
        return {
            item["entity_id"]: {
                "entity_id": item["entity_id"],
                "state": item["state"],
                "attributes": item["attributes"],
            }
            for item in self.build_entity_inspector_list()
        }

    def _resolve_robot(self, data: dict[str, Any]) -> VacuulaRobotData | None:
        """Resolve target robot from serial or entity_id."""
        robots = self._get_robots_dict()
        if not robots:
            return None
        if (serial := data.get("serial")) and serial in robots:
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

    async def _handle_index(self, _request: web.Request) -> web.StreamResponse:
        """Serve the Full-Stack Lovelace + Integration Entity Inspector HTML dashboard."""
        return web.FileResponse(INDEX_HTML_PATH, headers=NO_STORE_HEADERS)

    async def _handle_favicon(self, _request: web.Request) -> web.StreamResponse:
        """Serve the SVG favicon via zero-copy FileResponse."""
        return web.FileResponse(FAVICON_PATH)

    async def _handle_card_js(self, _request: web.Request) -> web.StreamResponse:
        """Serve custom_components/vacuula/frontend/vacuula-map-card.js directly from disk."""
        return web.FileResponse(CARD_JS_PATH, headers=NO_STORE_HEADERS)

    async def _handle_get_states(self, _request: web.Request) -> web.Response:
        """Poll runtime and return current hass.states, entities, and devices."""
        await self._async_refresh_runtime()
        return web.json_response(self._build_state_payload(include_server_info=True))

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
        self._sse_queues.add(q)
        try:
            initial = json.dumps(self._build_state_payload(include_server_info=True))
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
            self._sse_queues.discard(q)
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

    async def _dispatch_entity_service(
        self, ent: Any, domain: str, service: str, data: dict[str, Any]
    ) -> None:
        """Dispatch a service call directly to a real Home Assistant entity instance."""
        if domain == "vacuum":
            if service in _VACUUM_METHODS:
                await getattr(ent, f"async_{service}")()
            elif service == "set_fan_speed":
                await ent.async_set_fan_speed(str(data.get("fan_speed", "turbo")))
        elif domain == "select" and service == "select_option":
            await ent.async_select_option(str(data.get("option", "")))
        elif domain == "switch":
            turn_on = (
                not getattr(ent, "is_on", False)
                if service == "toggle"
                else service == "turn_on"
            )
            await (ent.async_turn_on() if turn_on else ent.async_turn_off())
        elif domain == "button" and service == "press":
            await ent.async_press()

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
            if ent is not None and domain in ("vacuum", "select", "switch", "button"):
                await self._dispatch_entity_service(ent, domain, service, data)
                self._on_coordinator_update()
                return web.json_response(self._build_state_payload())

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
                    target = self.coordinator or self.controller
                    if target is not None:
                        await target.async_refresh_maps_and_runs(robot.serial)
                    self._map_cache_buster = int(time.time() * 1000)

            if resp is not None:
                target = self.coordinator or self.controller
                if target is not None:
                    await target.async_apply_command_response(robot.serial, resp)
        except Exception as err:  # noqa: BLE001
            logger.warning(
                "Sandbox service call %s.%s failed: %s", domain, service, err
            )
            error_msg = str(err)

        self._on_coordinator_update()
        return web.json_response(self._build_state_payload(error=error_msg))

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
        return web.json_response(self._build_state_payload())

    async def _handle_map_png(self, request: web.Request) -> web.Response:
        """Render and serve the floor map or last run map PNG via real ImageEntity or map_renderer."""
        serial = request.match_info["serial"]
        kind = request.match_info["kind"]

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
                            headers=NO_STORE_HEADERS,
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
            headers=NO_STORE_HEADERS,
        )
