"""Unit tests for Vacuula integration lifecycle (__init__.py)."""

from __future__ import annotations

import base64
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.vacuula import (
    _async_register_frontend,
    _async_register_lovelace_resource,
    _async_register_websocket_commands,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.vacuula.const import (
    DOMAIN,
    ROBOT_TYPE_GEN3,
    SERVICE_CLEAN_SPOT,
    SERVICE_CLEAN_ZONES,
    SERVICE_REFRESH_MAPS,
)
from custom_components.vacuula.coordinator import VacuulaCoordinator, VacuulaRobotData


async def test_init_setup_and_unload_entry(hass: HomeAssistant) -> None:
    """Test full async_setup_entry and async_unload_entry lifecycle."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="http://192.168.1.50:8085",
        data={"url": "http://192.168.1.50:8085"},
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.vacuula.coordinator.VacuulaCoordinator.async_config_entry_first_refresh",
            AsyncMock(),
        ),
        patch(
            "custom_components.vacuula.coordinator.VacuulaCoordinator.async_start_sse",
            AsyncMock(),
        ),
        patch(
            "custom_components.vacuula.coordinator.VacuulaCoordinator.async_stop_sse",
            AsyncMock(),
        ),
        patch(
            "homeassistant.config_entries.ConfigEntries.async_forward_entry_setups",
            AsyncMock(return_value=True),
        ),
        patch(
            "homeassistant.config_entries.ConfigEntries.async_unload_platforms",
            AsyncMock(return_value=True),
        ),
    ):
        # 1. Setup entry
        assert await async_setup_entry(hass, entry) is True
        assert entry.runtime_data is not None
        assert hass.services.has_service(DOMAIN, SERVICE_CLEAN_ZONES)
        assert hass.services.has_service(DOMAIN, SERVICE_CLEAN_SPOT)
        assert hass.services.has_service(DOMAIN, SERVICE_REFRESH_MAPS)

        # Verify server hub device registration
        device_registry = dr.async_get(hass)
        hub_device = device_registry.async_get_device_by_identifier(
            (DOMAIN, f"server_{entry.entry_id}"),
            entry.entry_id,
        )
        assert hub_device is not None
        assert hub_device.manufacturer == "Vacuula"
        assert hub_device.model == "Vacuula Server"
        assert hub_device.entry_type == dr.DeviceEntryType.SERVICE
        # 2. Unload entry
        entry.mock_state(hass, ConfigEntryState.NOT_LOADED)
        assert await async_unload_entry(hass, entry) is True
        # Services removed when no loaded entries remain
        assert not hass.services.has_service(DOMAIN, SERVICE_CLEAN_ZONES)


async def test_lovelace_resource_registration(hass: HomeAssistant) -> None:
    """Test _async_register_lovelace_resource and frontend registration."""
    # Test when lovelace data not in hass
    await _async_register_lovelace_resource(hass, "/test/url")

    # Mock Lovelace storage collection
    mock_resources = MagicMock()
    mock_resources.loaded = False
    mock_resources.async_load = AsyncMock()
    mock_resources.async_items.return_value = [
        {"id": "res-1", "url": "/vacuula_frontend/vacuula-map-card.js?v=0.5.2"}
    ]
    mock_resources.async_update_item = AsyncMock()
    mock_resources.async_create_item = AsyncMock()

    class MockLovelaceData:
        resources = mock_resources

    hass.data["lovelace"] = MockLovelaceData()

    # Should update existing item with new version
    await _async_register_lovelace_resource(
        hass, "/vacuula_frontend/vacuula-map-card.js?v=0.6.0"
    )
    mock_resources.async_update_item.assert_awaited_once_with(
        "res-1", {"url": "/vacuula_frontend/vacuula-map-card.js?v=0.6.0"}
    )

    # When resource not found, should create item
    mock_resources.async_items.return_value = []
    await _async_register_lovelace_resource(
        hass, "/vacuula_frontend/vacuula-map-card.js?v=0.6.0"
    )
    mock_resources.async_create_item.assert_awaited_once_with(
        {"res_type": "module", "url": "/vacuula_frontend/vacuula-map-card.js?v=0.6.0"}
    )

    # Test frontend register
    with patch("pathlib.Path.is_file", return_value=True):
        await _async_register_frontend(hass)

    # Test frontend register when card file is missing -> returns early
    with patch("pathlib.Path.is_file", return_value=False):
        await _async_register_frontend(hass)

    # Test lovelace registration when resources is None or has no async_items
    hass.data["lovelace"] = MagicMock()
    del hass.data["lovelace"].resources
    await _async_register_lovelace_resource(hass, "/test/url")


async def test_websocket_get_run_map_image(
    hass: HomeAssistant,
    hass_ws_client: Any,
    socket_enabled: None,
) -> None:
    """Test vacuula/get_run_map_image WebSocket command variants and errors."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="http://192.168.1.50:8085",
        data={"url": "http://192.168.1.50:8085"},
        state=ConfigEntryState.LOADED,
    )
    entry.add_to_hass(hass)

    client = AsyncMock()
    coordinator = VacuulaCoordinator(hass, entry, client)
    robot = VacuulaRobotData(
        serial="OPS123",
        name="Neato D7",
        robot_type=ROBOT_TYPE_GEN3,
        connected=True,
        active_map_id="map-1",
        last_run_id="run-42",
        floormap={"width": 20, "height": 20, "rle": [[1, 400]]},
        last_run_floormap={"width": 10, "height": 10, "rle": [[2, 10], [1, 90]]},
        last_runmap={
            "width": 10,
            "height": 10,
            "rle": [[128, 40], [150, 10], [128, 50]],
        },
    )
    coordinator.data = {"OPS123": robot}
    entry.runtime_data = coordinator

    hass.states.async_set(
        "image.neato_d7_last_run_map",
        "2026-11-21T12:00:00Z",
        {"serial": "OPS123"},
    )

    _async_register_websocket_commands(hass)
    ws_client = await hass_ws_client(hass)

    # 1. include_basemap=True by serial
    await ws_client.send_json(
        {
            "id": 1,
            "type": "vacuula/get_run_map_image",
            "serial": "OPS123",
            "include_basemap": True,
        }
    )
    resp_with_base = await ws_client.receive_json()
    assert resp_with_base["success"] is True
    res_with_base = resp_with_base["result"]
    assert res_with_base["serial"] == "OPS123"
    assert res_with_base["run_id"] == "run-42"
    assert res_with_base["include_basemap"] is True
    assert res_with_base["content_type"] == "image/png"
    with_basemap_bytes = base64.b64decode(res_with_base["image_base64"])
    assert with_basemap_bytes.startswith(b"\x89PNG")

    # 2. include_basemap=False by serial
    await ws_client.send_json(
        {
            "id": 2,
            "type": "vacuula/get_run_map_image",
            "serial": "OPS123",
            "include_basemap": False,
        }
    )
    resp_path_only = await ws_client.receive_json()
    assert resp_path_only["success"] is True
    res_path_only = resp_path_only["result"]
    assert res_path_only["include_basemap"] is False
    path_only_bytes = base64.b64decode(res_path_only["image_base64"])
    assert path_only_bytes.startswith(b"\x89PNG")
    assert path_only_bytes != with_basemap_bytes

    # 3. include_basemap=False by entity_id
    await ws_client.send_json(
        {
            "id": 3,
            "type": "vacuula/get_run_map_image",
            "entity_id": "image.neato_d7_last_run_map",
            "include_basemap": False,
        }
    )
    resp_by_entity = await ws_client.receive_json()
    assert resp_by_entity["success"] is True
    assert base64.b64decode(resp_by_entity["result"]["image_base64"]) == path_only_bytes

    # 4. Missing last_runmap returns not_found
    robot.last_runmap = None
    await ws_client.send_json(
        {
            "id": 4,
            "type": "vacuula/get_run_map_image",
            "serial": "OPS123",
            "include_basemap": False,
        }
    )
    resp_missing = await ws_client.receive_json()
    assert resp_missing["success"] is False
    assert resp_missing["error"]["code"] == "not_found"

    # 5. Unknown serial returns not_found
    await ws_client.send_json(
        {
            "id": 5,
            "type": "vacuula/get_run_map_image",
            "serial": "UNKNOWN",
        }
    )
    resp_unknown = await ws_client.receive_json()
    assert resp_unknown["success"] is False
    assert resp_unknown["error"]["code"] == "not_found"
