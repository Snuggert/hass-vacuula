"""Tests for the Vacuula diagnostics platform."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.vacuula.const import DOMAIN
from custom_components.vacuula.coordinator import VacuulaCoordinator, VacuulaRobotData
from custom_components.vacuula.diagnostics import (
    async_get_config_entry_diagnostics,
    async_get_device_diagnostics,
)


async def test_config_entry_diagnostics_redaction(hass: HomeAssistant) -> None:
    """Test that config entry diagnostics redacts all sensitive fields and serial keys."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Vacuula (1.0.0)",
        data={"url": "http://192.168.1.50:8085"},
    )
    entry.add_to_hass(hass)

    coordinator = MagicMock()
    coordinator.client.async_get_server_info = AsyncMock(
        return_value={
            "version": "1.0.0",
            "secret": "super_secret_token",
            "mac": "AA:BB:CC:DD:EE:FF",
        }
    )
    robot = VacuulaRobotData(
        serial="OPS123-SECRET-SERIAL",
        name="Living Room Bot",
        robot_type="neato.gen3",
        connected=True,
        installed_with="1.1.0-b6",
        floormap={"width": 475, "height": 472, "rle": []},
        last_run_floormap={"width": 347, "height": 305, "rle": []},
        last_runmap={"width": 347, "height": 305, "rle": []},
    )
    coordinator.data = {"OPS123-SECRET-SERIAL": robot}
    entry.runtime_data = coordinator

    diag = await async_get_config_entry_diagnostics(hass, entry)

    # Entry URL must be redacted
    assert diag["entry"]["url"] == "**REDACTED**"

    # Server info secrets must be redacted
    assert diag["server_info"]["secret"] == "**REDACTED**"
    assert diag["server_info"]["mac"] == "**REDACTED**"

    # Robot serial key must not leak raw hardware serial
    assert "OPS123-SECRET-SERIAL" not in diag["robots"]
    assert "robot_1" in diag["robots"]

    # Robot serial field must be redacted
    assert diag["robots"]["robot_1"]["serial"] == "**REDACTED**"
    assert diag["robots"]["robot_1"]["name"] == "Living Room Bot"
    assert diag["robots"]["robot_1"]["installed_with"] == "1.1.0-b6"
    assert diag["robots"]["robot_1"]["floormap_size"] == [475, 472]
    assert diag["robots"]["robot_1"]["last_run_floormap_size"] == [347, 305]
    assert diag["robots"]["robot_1"]["last_runmap_size"] == [347, 305]

    # Test when async_get_server_info raises exception
    coordinator.client.async_get_server_info = AsyncMock(
        side_effect=RuntimeError("Connection failed")
    )
    diag_err = await async_get_config_entry_diagnostics(hass, entry)
    assert diag_err["server_info"] == {"error": "Connection failed"}


async def test_device_diagnostics(hass: HomeAssistant) -> None:
    """Test device diagnostics redaction and not-found behavior."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Vacuula",
        data={"url": "http://192.168.1.50:8085"},
    )
    entry.add_to_hass(hass)

    coordinator = MagicMock(spec=VacuulaCoordinator)
    robot = VacuulaRobotData(
        serial="OPS999-BOT",
        name="Basement",
        robot_type="neato.gen3",
        connected=False,
    )
    coordinator.data = {"OPS999-BOT": robot}
    entry.runtime_data = coordinator

    # Test matching device
    device_entry = MagicMock()
    device_entry.identifiers = {(DOMAIN, "OPS999-BOT")}

    diag = await async_get_device_diagnostics(hass, entry, device_entry)
    assert diag["serial"] == "**REDACTED**"
    assert diag["name"] == "Basement"
    assert diag["connected"] is False
    assert diag["floormap_size"] is None
    assert diag["last_run_floormap_size"] is None
    assert diag["last_runmap_size"] is None

    # Test non-matching device
    device_missing = MagicMock()
    device_missing.identifiers = {(DOMAIN, "UNKNOWN-SERIAL")}
    diag_missing = await async_get_device_diagnostics(hass, entry, device_missing)
    assert diag_missing == {"error": "Robot not found in coordinator data"}
