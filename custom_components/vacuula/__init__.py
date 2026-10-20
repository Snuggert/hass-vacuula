"""The Vacuula integration."""
from __future__ import annotations

from typing import TypeAlias

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_URL
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import VacuulaApiClient
from .const import PLATFORMS
from .coordinator import VacuulaCoordinator

VacuulaConfigEntry: TypeAlias = ConfigEntry[VacuulaCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: VacuulaConfigEntry) -> bool:
    """Set up Vacuula from a config entry."""
    session = async_get_clientsession(hass)
    client = VacuulaApiClient(entry.data[CONF_URL], session)
    coordinator = VacuulaCoordinator(hass, client)

    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await coordinator.async_start_sse()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: VacuulaConfigEntry) -> bool:
    """Unload a config entry."""
    await entry.runtime_data.async_stop_sse()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
