"""Unit tests for Vacuula integration lifecycle (__init__.py)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.vacuula import (
    _async_register_frontend,
    _async_register_lovelace_resource,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.vacuula.const import (
    DOMAIN,
    SERVICE_CLEAN_SPOT,
    SERVICE_CLEAN_ZONES,
    SERVICE_REFRESH_MAPS,
)


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
