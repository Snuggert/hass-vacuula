"""Config flow for Vacuula integration."""
from __future__ import annotations

from typing import Any
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_URL
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from .api import VacuulaApiClient, VacuulaApiError
from .const import DEFAULT_URL, DOMAIN


class VacuulaConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Vacuula."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovered_url: str | None = None
        self._discovered_version: str = "Server"

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step initiated by the user."""
        errors: dict[str, str] = {}

        if user_input is not None:
            url = user_input[CONF_URL].rstrip("/")
            session = async_get_clientsession(self.hass)
            client = VacuulaApiClient(url, session)
            try:
                info = await client.async_get_server_info()
            except VacuulaApiError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(url)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"Vacuula ({info.get('version', 'Server')})",
                    data={CONF_URL: url},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_URL, default=DEFAULT_URL): str}),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reconfiguration of the Vacuula server URL."""
        reconfigure_entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            url = user_input[CONF_URL].rstrip("/")
            session = async_get_clientsession(self.hass)
            client = VacuulaApiClient(url, session)
            try:
                info = await client.async_get_server_info()
            except VacuulaApiError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(
                    reconfigure_entry,
                    title=f"Vacuula ({info.get('version', 'Server')})",
                    data_updates={CONF_URL: url},
                )

        current_url = reconfigure_entry.data.get(CONF_URL, DEFAULT_URL)
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema({vol.Required(CONF_URL, default=current_url): str}),
            errors=errors,
        )

    async def async_step_zeroconf(
        self, discovery_info: ZeroconfServiceInfo
    ) -> ConfigFlowResult:
        """Handle zeroconf discovery of a Vacuula server (_vacuula._tcp.local.)."""
        host = discovery_info.host
        port = discovery_info.port or 80
        url = f"http://{host}" if port == 80 else f"http://{host}:{port}"

        await self.async_set_unique_id(url)
        self._abort_if_unique_id_configured()

        session = async_get_clientsession(self.hass)
        client = VacuulaApiClient(url, session)
        try:
            info = await client.async_get_server_info()
        except VacuulaApiError:
            return self.async_abort(reason="cannot_connect")

        self._discovered_url = url
        self._discovered_version = str(info.get("version", "Server"))
        self.context["title_placeholders"] = {
            "url": url,
            "version": self._discovered_version,
        }
        return await self.async_step_zeroconf_confirm()

    async def async_step_zeroconf_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm setup of a zeroconf-discovered Vacuula server."""
        assert self._discovered_url is not None

        if user_input is not None:
            return self.async_create_entry(
                title=f"Vacuula ({self._discovered_version})",
                data={CONF_URL: self._discovered_url},
            )

        return self.async_show_form(
            step_id="zeroconf_confirm",
            description_placeholders={
                "url": self._discovered_url,
                "version": self._discovered_version,
            },
        )
