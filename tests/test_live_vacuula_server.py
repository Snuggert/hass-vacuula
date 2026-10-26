"""Live integration tests running against an actual Vacuula Dev Server backed by mock Neato robots."""

from __future__ import annotations

import asyncio
from typing import Any

import aiohttp
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.vacuula.api import (
    VacuulaApiClient,
)
from custom_components.vacuula.const import (
    DOMAIN,
    GEN3_ACTION_DOCKING,
    GEN3_ACTION_MAP_CLEANING,
    GEN3_ACTION_NONE,
    GEN3_STATE_BUSY,
    GEN3_STATE_IDLE,
    GEN3_STATE_PAUSED,
    ROBOT_TYPE_GEN3,
)
from custom_components.vacuula.coordinator import (
    VacuulaCoordinator,
    is_installer_outdated,
)
from devtools.sandbox import VacuulaDevSandbox
from devtools.server_manager import VacuulaServerManager


@pytest.fixture(scope="module")
def _shared_vacuula_server():
    """Start a shared isolated real Vacuula dev server for the module."""
    with VacuulaServerManager(
        app_version="1.1.0-b9", min_installer_version="1.1.0-b3"
    ) as srv:
        yield srv


@pytest.fixture
def vacuula_dev_server(
    socket_enabled: None, _shared_vacuula_server: VacuulaServerManager
):
    """Reset the shared Vacuula dev server before and after each test for clean isolation."""
    _shared_vacuula_server.reset()
    yield _shared_vacuula_server
    _shared_vacuula_server.reset()


@pytest.mark.asyncio
async def test_live_server_info(vacuula_dev_server: VacuulaServerManager) -> None:
    """Test fetching server metadata from a running Vacuula dev server."""
    async with aiohttp.ClientSession() as session:
        client = VacuulaApiClient(vacuula_dev_server.base_url, session)
        info = await client.async_get_server_info()

        assert info["version"] == "1.1.0-b9"
        assert info["min_installer_version"] == "1.1.0-b3"
        assert "timezone" in info
        assert "gen3_port" in info


@pytest.mark.asyncio
async def test_live_robot_discovery_and_linking(
    vacuula_dev_server: VacuulaServerManager,
) -> None:
    """Test linking mock robots and discovering them via GET /api/robots."""
    vacuula_dev_server.add_mock_robot(
        serial="OPS00001-001122334401",
        name="Living Room D7",
        installer_version="1.1.0-b3",
    )
    vacuula_dev_server.add_mock_robot(
        serial="OPS00002-001122334402",
        name="Bedroom D5",
        installer_version="1.0.0-b28",
        model="BotVacD5Connected",
    )

    async with aiohttp.ClientSession() as session:
        client = VacuulaApiClient(vacuula_dev_server.base_url, session)
        robots = await client.async_get_robots()

        assert "OPS00001-001122334401" in robots
        assert "OPS00002-001122334402" in robots

        r1_data = robots["OPS00001-001122334401"]
        assert r1_data["name"] == "Living Room D7"
        assert r1_data["connected"] is True
        assert r1_data["installed_with"] == "1.1.0-b3"

        r2_data = robots["OPS00002-001122334402"]
        assert r2_data["name"] == "Bedroom D5"
        assert r2_data["connected"] is True
        assert r2_data["installed_with"] == "1.0.0-b28"


@pytest.mark.asyncio
async def test_live_get_robot_state(vacuula_dev_server: VacuulaServerManager) -> None:
    """Test getRobotState dispatch from client through Vacuula to mock Neato robot."""
    robot = vacuula_dev_server.add_mock_robot(
        serial="OPS00003-001122334403",
        name="Kitchen Bot",
        installer_version="1.1.0-b3",
    )
    robot.set_battery(87, is_charging=False)
    robot.set_docked(True)

    async with aiohttp.ClientSession() as session:
        client = VacuulaApiClient(vacuula_dev_server.base_url, session)
        state = await client.async_get_robot_state(robot.serial, ROBOT_TYPE_GEN3)

        assert state["result"] == "ok"
        assert state["state"] == GEN3_STATE_IDLE
        assert state["details"]["charge"] == 87
        assert state["details"]["isDocked"] is True
        assert state["details"]["isCharging"] is False
        assert state["meta"]["modelName"] == "BotVacD7Connected"


@pytest.mark.asyncio
async def test_live_cleaning_cycle_commands(
    vacuula_dev_server: VacuulaServerManager,
) -> None:
    """Test startCleaning, pauseCleaning, resumeCleaning, and stopCleaning commands."""
    robot = vacuula_dev_server.add_mock_robot(
        serial="OPS00004-001122334404",
        name="Main Floor Bot",
        installer_version="1.1.0-b3",
    )

    async with aiohttp.ClientSession() as session:
        client = VacuulaApiClient(vacuula_dev_server.base_url, session)

        # 1. Start cleaning (defaults to GEN3_CATEGORY_MAP -> action 11)
        start_res = await client.async_start_cleaning(robot.serial, ROBOT_TYPE_GEN3)
        assert start_res["result"] == "ok"
        assert robot.state == GEN3_STATE_BUSY
        assert robot.action == GEN3_ACTION_MAP_CLEANING
        assert robot.is_docked is False

        # Verify state through API
        st = await client.async_get_robot_state(robot.serial, ROBOT_TYPE_GEN3)
        assert st["state"] == GEN3_STATE_BUSY
        assert st["details"]["isDocked"] is False

        # 2. Pause cleaning
        pause_res = await client.async_pause_cleaning(robot.serial, ROBOT_TYPE_GEN3)
        assert pause_res["result"] == "ok"
        assert robot.state == GEN3_STATE_PAUSED

        # 3. Resume cleaning
        resume_res = await client.async_resume_cleaning(robot.serial, ROBOT_TYPE_GEN3)
        assert resume_res["result"] == "ok"
        assert robot.state == GEN3_STATE_BUSY

        # 4. Stop cleaning
        stop_res = await client.async_stop_cleaning(robot.serial, ROBOT_TYPE_GEN3)
        assert stop_res["result"] == "ok"
        assert robot.state == GEN3_STATE_IDLE
        assert robot.action == GEN3_ACTION_NONE


@pytest.mark.asyncio
async def test_live_return_to_base_and_docking(
    vacuula_dev_server: VacuulaServerManager,
) -> None:
    """Test sending robot to charging base."""
    robot = vacuula_dev_server.add_mock_robot(
        serial="OPS00005-001122334405",
        name="Dock Test Bot",
    )
    robot.set_cleaning()
    assert robot.is_docked is False

    async with aiohttp.ClientSession() as session:
        client = VacuulaApiClient(vacuula_dev_server.base_url, session)
        resp = await client.async_return_to_base(robot.serial, ROBOT_TYPE_GEN3)
        assert resp["result"] == "ok"

        assert robot.action == GEN3_ACTION_DOCKING
        assert robot.is_docked is True
        assert robot.is_charging is True


@pytest.mark.asyncio
async def test_live_locate_and_schedule(
    vacuula_dev_server: VacuulaServerManager,
) -> None:
    """Test locate (findMe) and schedule toggles."""
    robot = vacuula_dev_server.add_mock_robot(
        serial="OPS00006-001122334406",
        name="Utility Bot",
    )

    async with aiohttp.ClientSession() as session:
        client = VacuulaApiClient(vacuula_dev_server.base_url, session)

        # Locate
        locate_res = await client.async_locate(robot.serial, ROBOT_TYPE_GEN3)
        assert locate_res["result"] == "ok"
        assert robot.locate_calls == 1

        # Disable schedule
        await client.async_set_schedule_enabled(robot.serial, False, ROBOT_TYPE_GEN3)
        assert robot.is_schedule_enabled is False

        # Enable schedule
        await client.async_set_schedule_enabled(robot.serial, True, ROBOT_TYPE_GEN3)
        assert robot.is_schedule_enabled is True


@pytest.mark.asyncio
async def test_live_zone_cleaning_and_seeded_maps(
    vacuula_dev_server: VacuulaServerManager,
) -> None:
    """Test seeded RLE maps/runs and zone cleaning command dispatch."""
    robot = vacuula_dev_server.add_mock_robot(
        serial="OPS00007-001122334407",
        name="Zone Bot",
    )

    async with aiohttp.ClientSession() as session:
        client = VacuulaApiClient(vacuula_dev_server.base_url, session)

        maps = await client.async_get_maps(robot.serial)
        assert len(maps) == 1
        assert maps[0]["id"] == "map-floor-1"

        floormap = await client.async_get_map_detail(robot.serial, "map-floor-1")
        assert floormap["width"] == 64
        assert floormap["height"] == 64
        assert isinstance(floormap["rle"], list)

        runs = await client.async_get_runs(robot.serial)
        assert len(runs) == 1
        runmap = await client.async_get_run_detail(robot.serial, runs[0]["id"])
        assert runmap["width"] == 64

        res = await client.async_start_zone_cleaning(
            serial=robot.serial,
            robot_type=ROBOT_TYPE_GEN3,
            map_id="map-floor-1",
            zone_ids=["bnd-kitchen"],
        )
        assert res["result"] == "ok"
        assert robot.state == GEN3_STATE_BUSY
        assert robot.action == GEN3_ACTION_MAP_CLEANING
        assert robot.last_command is not None
        assert robot.last_command["params"]["boundaryId"] == "bnd-kitchen"


@pytest.mark.asyncio
async def test_live_sse_events_stream(
    vacuula_dev_server: VacuulaServerManager,
) -> None:
    """Test receiving real-time SSE push events when robots connect or change."""
    async with aiohttp.ClientSession() as session:
        client = VacuulaApiClient(vacuula_dev_server.base_url, session)

        received_events: list[tuple[str, Any]] = []

        async def _listen():
            async for ev_name, ev_data in client.async_iter_server_events():
                received_events.append((ev_name, ev_data))
                if len(received_events) >= 2:
                    break

        listener_task = asyncio.create_task(_listen())

        # Give listener time to connect and receive initial robots event
        await asyncio.sleep(0.3)

        # Trigger event by adding a new robot
        vacuula_dev_server.add_mock_robot(
            serial="OPS00008-001122334408",
            name="SSE Stream Bot",
        )

        try:
            await asyncio.wait_for(listener_task, timeout=3.0)
        except TimeoutError:
            pass
        finally:
            listener_task.cancel()

        assert len(received_events) >= 1
        event_names = [name for name, _ in received_events]
        assert "robots" in event_names


@pytest.mark.asyncio
async def test_live_coordinator_polling(
    hass, vacuula_dev_server: VacuulaServerManager
) -> None:
    """Test VacuulaCoordinator polling and data structure with live Vacuula dev server."""
    robot = vacuula_dev_server.add_mock_robot(
        serial="OPS00009-001122334409",
        name="Coordinator Bot",
        installer_version="1.1.0-b3",
    )
    robot.set_battery(72)

    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=vacuula_dev_server.base_url,
        data={"url": vacuula_dev_server.base_url},
    )
    entry.add_to_hass(hass)

    async with aiohttp.ClientSession() as session:
        client = VacuulaApiClient(vacuula_dev_server.base_url, session)
        coordinator = VacuulaCoordinator(hass, entry, client)

        await coordinator.async_refresh()

        assert robot.serial in coordinator.data
        data = coordinator.data[robot.serial]
        assert data.name == "Coordinator Bot"
        assert data.connected is True
        assert data.state["details"]["charge"] == 72
        assert data.installed_with == "1.1.0-b3"
        assert data.active_map_id == "map-floor-1"
        assert len(data.zones) == 2
        assert is_installer_outdated(data.installed_with, "1.1.0-b3") is False


@pytest.mark.asyncio
async def test_live_coordinator_installer_compatibility_check(
    hass, vacuula_dev_server: VacuulaServerManager
) -> None:
    """Test coordinator installer version check against Vacuula min_installer_version."""
    legacy_robot = vacuula_dev_server.add_mock_robot(
        serial="OPS00010-001122334410",
        name="Legacy Bot",
        installer_version="1.0.0-b28",
    )

    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=vacuula_dev_server.base_url,
        data={"url": vacuula_dev_server.base_url},
    )
    entry.add_to_hass(hass)

    async with aiohttp.ClientSession() as session:
        client = VacuulaApiClient(vacuula_dev_server.base_url, session)
        coordinator = VacuulaCoordinator(hass, entry, client)

        await coordinator.async_refresh()

        assert legacy_robot.serial in coordinator.data
        data = coordinator.data[legacy_robot.serial]
        assert data.installed_with == "1.0.0-b28"
        assert is_installer_outdated(data.installed_with, "1.1.0-b3") is True


@pytest.mark.asyncio
async def test_live_robot_disconnect_handling(
    hass, vacuula_dev_server: VacuulaServerManager
) -> None:
    """Test that robot disconnection is detected and reflected by Vacuula and coordinator."""
    robot = vacuula_dev_server.add_mock_robot(
        serial="OPS00011-001122334411",
        name="Disconnect Bot",
    )

    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=vacuula_dev_server.base_url,
        data={"url": vacuula_dev_server.base_url},
    )
    entry.add_to_hass(hass)

    async with aiohttp.ClientSession() as session:
        client = VacuulaApiClient(vacuula_dev_server.base_url, session)
        coordinator = VacuulaCoordinator(hass, entry, client)
        await coordinator.async_refresh()
        assert coordinator.data[robot.serial].connected is True

        # Disconnect robot
        robot.disconnect()
        await asyncio.sleep(0.2)

        # Refresh coordinator
        await coordinator.async_refresh()
        assert coordinator.data[robot.serial].connected is False


@pytest.mark.asyncio
async def test_live_standalone_sandbox_end_to_end(
    vacuula_dev_server: VacuulaServerManager,
) -> None:
    """Test the Zero-HA Standalone Developer Sandbox hosting vacuula-map-card.js."""
    robot = vacuula_dev_server.add_mock_robot(
        serial="OPS00012-001122334412",
        name="Sandbox D7",
    )

    sandbox = VacuulaDevSandbox(
        vacuula_url=vacuula_dev_server.base_url,
        server_manager=vacuula_dev_server,
        port=0,
    )
    await sandbox.async_start()
    try:
        async with aiohttp.ClientSession() as session:
            # 1. Verify HTML, static assets & JS card serving
            async with session.get(f"{sandbox.sandbox_url}/") as resp:
                assert resp.status == 200
                text = await resp.text()
                assert "<vacuula-map-card" in text

            for static_asset in ("/static/sandbox.css", "/static/sandbox.js"):
                async with session.get(f"{sandbox.sandbox_url}{static_asset}") as resp:
                    assert resp.status == 200

            async with session.get(
                f"{sandbox.sandbox_url}/vacuula_frontend/vacuula-map-card.js"
            ) as resp:
                assert resp.status == 200
                js_text = await resp.text()
                assert "VacuulaMapCard" in js_text

            # 2. Verify synthesized hass.states and real integration entities
            async with session.get(f"{sandbox.sandbox_url}/api/sandbox/states") as resp:
                assert resp.status == 200
                payload = await resp.json()
                states = payload["states"]
                assert "vacuum.sandbox_d7" in states
                assert states["vacuum.sandbox_d7"]["state"] == "docked"
                assert "image.sandbox_d7_floor_map" in states
                assert (
                    len(states["image.sandbox_d7_floor_map"]["attributes"]["zones"])
                    == 2
                )

                # Verify that all 7 custom_components/vacuula entity platforms are instantiated
                entities = payload["entities"]
                assert len(entities) >= 20
                entity_classes = {e["entity_class"] for e in entities}
                assert "VacuulaVacuumEntity" in entity_classes
                assert "VacuulaFloorMapImage" in entity_classes
                assert "VacuulaBatterySensor" in entity_classes
                assert "VacuulaConnectedBinarySensor" in entity_classes
                assert "VacuulaNavigationModeSelect" in entity_classes
                assert "VacuulaScheduleSwitch" in entity_classes
                assert "VacuulaCleanZoneButton" in entity_classes

                # Verify Device Registry info from VacuulaEntity.device_info
                devices = payload["devices"]
                assert len(devices) == 1
                assert devices[0]["serial"] == robot.serial
                assert devices[0]["name"] == "Sandbox D7"

            # 3. Verify PNG map rendering endpoints
            async with session.get(
                f"{sandbox.sandbox_url}/api/sandbox/map/{robot.serial}/floor.png"
            ) as resp:
                assert resp.status == 200
                png = await resp.read()
                assert png.startswith(b"\x89PNG\r\n\x1a\n")

            # 4. Verify interacting with real integration entities (Select, Switch, Button)
            async with session.post(
                f"{sandbox.sandbox_url}/api/sandbox/call_service",
                json={
                    "domain": "select",
                    "service": "select_option",
                    "service_data": {
                        "entity_id": "select.sandbox_d7_target_zone",
                        "option": "Kitchen",
                    },
                },
            ) as resp:
                assert resp.status == 200
                updated = await resp.json()
                assert (
                    updated["states"]["select.sandbox_d7_target_zone"]["state"]
                    == "Kitchen"
                )

            async with session.post(
                f"{sandbox.sandbox_url}/api/sandbox/call_service",
                json={
                    "domain": "button",
                    "service": "press",
                    "service_data": {
                        "entity_id": "button.sandbox_d7_locate",
                    },
                },
            ) as resp:
                assert resp.status == 200
                assert robot.locate_calls == 1

            # 5. Verify calling zone cleaning service via sandbox bridge
            async with session.post(
                f"{sandbox.sandbox_url}/api/sandbox/call_service",
                json={
                    "domain": "vacuula",
                    "service": "clean_zones",
                    "service_data": {
                        "entity_id": "vacuum.sandbox_d7",
                        "zones": ["Kitchen"],
                    },
                },
            ) as resp:
                assert resp.status == 200
                updated = await resp.json()
                assert updated["states"]["vacuum.sandbox_d7"]["state"] == "cleaning"
                assert robot.state == GEN3_STATE_BUSY

            # 6. Verify triggering hardware events & scenarios via /api/sandbox/mock_robot
            async with session.post(
                f"{sandbox.sandbox_url}/api/sandbox/mock_robot",
                json={
                    "serial": robot.serial,
                    "action": "alert",
                    "value": "dustbin_full",
                },
            ) as resp:
                assert resp.status == 200
                ev_data = await resp.json()
                assert (
                    ev_data["states"]["sensor.sandbox_d7_alert"]["state"]
                    == "dustbin_full"
                )
                assert (
                    ev_data["states"]["binary_sensor.sandbox_d7_dust_bin_full"]["state"]
                    == "on"
                )

            async with session.post(
                f"{sandbox.sandbox_url}/api/sandbox/mock_robot",
                json={
                    "serial": robot.serial,
                    "action": "error",
                    "value": "ui_error_brush_stuck",
                },
            ) as resp:
                assert resp.status == 200
                ev_data = await resp.json()
                assert ev_data["states"]["vacuum.sandbox_d7"]["state"] == "error"

            async with session.post(
                f"{sandbox.sandbox_url}/api/sandbox/mock_robot",
                json={"serial": robot.serial, "action": "clear"},
            ) as resp:
                assert resp.status == 200
                ev_data = await resp.json()
                assert (
                    ev_data["states"]["binary_sensor.sandbox_d7_dust_bin_full"]["state"]
                    == "off"
                )
    finally:
        await sandbox.async_stop()


@pytest.mark.asyncio
async def test_live_legacy_server_v1_0_0(socket_enabled: None) -> None:
    """Test compatibility when running against a Vacuula v1.0.0 server release."""
    with VacuulaServerManager(
        app_version="1.0.0", min_installer_version=None
    ) as legacy_srv:
        robot = legacy_srv.add_mock_robot(
            serial="OPS00013-001122334413",
            name="Vintage D7",
            installer_version="1.0.0-b28",
        )

        async with aiohttp.ClientSession() as session:
            client = VacuulaApiClient(legacy_srv.base_url, session)
            info = await client.async_get_server_info()
            assert info["version"] == "1.0.0"
            assert info.get("min_installer_version") is None

            st = await client.async_get_robot_state(robot.serial, ROBOT_TYPE_GEN3)
            assert st["result"] == "ok"
            assert st["state"] == GEN3_STATE_IDLE
