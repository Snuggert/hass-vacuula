"""Config flow for Vacuula integration."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

import voluptuous as vol

try:
    from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
except ImportError:  # pragma: no cover
    from homeassistant.config_entries import ConfigFlow
    from homeassistant.data_entry_flow import FlowResult as ConfigFlowResult  # type: ignore[assignment]
from homeassistant.const import CONF_URL
from homeassistant.helpers.aiohttp_client import async_get_clientsession

try:
    from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
except ImportError:  # pragma: no cover
    from homeassistant.components.zeroconf import ZeroconfServiceInfo  # type: ignore[attr-defined,no-redef]

from .api import VacuulaApiClient, VacuulaApiError
from .const import DEFAULT_URL, DOMAIN


def _normalize_url(raw: str) -> str | None:
    """Normalize a user-supplied server URL, returning None if it is invalid.

    A missing scheme defaults to http://. Only http and https are accepted,
    and the URL must contain a host. Trailing slashes are stripped.
    """
    value = raw.strip()
    if not value:
        return None
    if "://" not in value:
        value = f"http://{value}"
    try:
        parts = urlsplit(value)
        _ = parts.port  # Raises ValueError on an invalid port
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return None
    if parts.query or parts.fragment:
        return None
    return value.rstrip("/")


class VacuulaConfigFlow(ConfigFlow, domain=DOMAIN):  # type: ignore[call-arg]
    """Handle a config flow for Vacuula."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovered_url: str | None = None
        self._discovered_version: str = "Server"

    async def _async_validate(
        self, raw_url: str, errors: dict[str, str]
    ) -> tuple[str, dict[str, Any]] | None:
        """Validate a URL and connectivity, populating errors on failure."""
        url = _normalize_url(raw_url)
        if url is None:
            errors[CONF_URL] = "invalid_url"
            return None
        client = VacuulaApiClient(url, async_get_clientsession(self.hass))
        try:
            info = await client.async_get_server_info()
        except VacuulaApiError:
            errors["base"] = "cannot_connect"
            return None
        if not isinstance(info, dict):
            errors["base"] = "cannot_connect"
            return None
        return url, info

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step initiated by the user."""
        errors: dict[str, str] = {}

        if user_input is not None:
            result = await self._async_validate(user_input[CONF_URL], errors)
            if result is not None:
                url, info = result
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
            result = await self._async_validate(user_input[CONF_URL], errors)
            if result is not None:
                url, info = result
                if url != reconfigure_entry.unique_id:
                    await self.async_set_unique_id(url)
                    self._abort_if_unique_id_configured()
                return self.async_update_reload_and_abort(
                    reconfigure_entry,
                    unique_id=url,
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
        ip_addr = getattr(discovery_info, "ip_address", None)
        if ip_addr is None:
            import ipaddress

            ip_addr = ipaddress.ip_address(discovery_info.host)
        if ip_addr.is_link_local:
            return self.async_abort(reason="link_local_address")

        host = f"[{ip_addr}]" if ip_addr.version == 6 else str(ip_addr)
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
        if not isinstance(info, dict):
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
