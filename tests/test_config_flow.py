"""Tests for the Vacuula config flow."""

from __future__ import annotations

import ipaddress
from unittest.mock import patch

import pytest
from homeassistant import config_entries
from homeassistant.const import CONF_URL
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

try:
    from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
except ImportError:
    from homeassistant.components.zeroconf import ZeroconfServiceInfo  # type: ignore[no-redef]

from custom_components.vacuula.api import VacuulaApiError
from custom_components.vacuula.const import DOMAIN


async def test_user_step_success(hass: HomeAssistant) -> None:
    """Test standard successful setup initiated by user."""
    with patch(
        "custom_components.vacuula.config_flow.VacuulaApiClient.async_get_server_info",
        return_value={"version": "1.0.0"},
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "user"

        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_URL: "http://192.168.1.50:8085"},
        )
        assert result2["type"] == FlowResultType.CREATE_ENTRY
        assert result2["title"] == "Vacuula (1.0.0)"
        assert result2["data"] == {CONF_URL: "http://192.168.1.50:8085"}
        assert result2["result"].unique_id == "http://192.168.1.50:8085"


async def test_user_step_url_normalized(hass: HomeAssistant) -> None:
    """Test URL missing scheme automatically gets http:// prefix."""
    with patch(
        "custom_components.vacuula.config_flow.VacuulaApiClient.async_get_server_info",
        return_value={"version": "1.0.0"},
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_URL: "192.168.1.50:8085/"},
        )
        assert result2["type"] == FlowResultType.CREATE_ENTRY
        assert result2["data"] == {CONF_URL: "http://192.168.1.50:8085"}


async def test_user_step_invalid_url(hass: HomeAssistant) -> None:
    """Test that invalid URLs show invalid_url error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    # Test invalid scheme
    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_URL: "ftp://vacuula.local"},
    )
    assert result2["type"] == FlowResultType.FORM
    assert result2["errors"] == {CONF_URL: "invalid_url"}

    # Test invalid port
    result3 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_URL: "http://vacuula.local:99999"},
    )
    assert result3["type"] == FlowResultType.FORM
    assert result3["errors"] == {CONF_URL: "invalid_url"}


async def test_user_step_cannot_connect(hass: HomeAssistant) -> None:
    """Test connection error shows cannot_connect."""
    with patch(
        "custom_components.vacuula.config_flow.VacuulaApiClient.async_get_server_info",
        side_effect=VacuulaApiError("Connection refused"),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_URL: "http://192.168.1.99:8085"},
        )
        assert result2["type"] == FlowResultType.FORM
        assert result2["errors"] == {"base": "cannot_connect"}


async def test_user_step_already_configured(hass: HomeAssistant) -> None:
    """Test duplicate unique_id aborts."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="http://192.168.1.50:8085",
        data={CONF_URL: "http://192.168.1.50:8085"},
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.vacuula.config_flow.VacuulaApiClient.async_get_server_info",
        return_value={"version": "1.0.0"},
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_URL: "http://192.168.1.50:8085"},
        )
        assert result2["type"] == FlowResultType.ABORT
        assert result2["reason"] == "already_configured"


def make_zeroconf_info(ip_str: str, port: int = 8085) -> ZeroconfServiceInfo:
    """Create a ZeroconfServiceInfo instance compatible across HA versions."""
    ip = ipaddress.ip_address(ip_str)
    try:
        return ZeroconfServiceInfo(
            ip_address=ip,
            ip_addresses=[ip],
            port=port,
            hostname="vacuula.local.",
            type="_vacuula._tcp.local.",
            name="Vacuula._vacuula._tcp.local.",
            properties={},
        )
    except TypeError:
        return ZeroconfServiceInfo(
            host=str(ip),
            addresses=[str(ip)],
            port=port,
            hostname="vacuula.local.",
            type="_vacuula._tcp.local.",
            name="Vacuula._vacuula._tcp.local.",
            properties={},
        )


async def test_zeroconf_discovery_success(hass: HomeAssistant) -> None:
    """Test Zeroconf auto-discovery and user confirmation."""
    discovery_info = make_zeroconf_info("192.168.1.55", 8085)

    with patch(
        "custom_components.vacuula.config_flow.VacuulaApiClient.async_get_server_info",
        return_value={"version": "1.2.0"},
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_ZEROCONF},
            data=discovery_info,
        )
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "zeroconf_confirm"

        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={}
        )
        assert result2["type"] == FlowResultType.CREATE_ENTRY
        assert result2["title"] == "Vacuula (1.2.0)"
        assert result2["data"] == {CONF_URL: "http://192.168.1.55:8085"}


async def test_zeroconf_discovery_ipv6(hass: HomeAssistant) -> None:
    """Test Zeroconf discovery with routable IPv6 address formatting."""
    discovery_info = make_zeroconf_info("2001:db8::1", 8085)

    with patch(
        "custom_components.vacuula.config_flow.VacuulaApiClient.async_get_server_info",
        return_value={"version": "1.2.0"},
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_ZEROCONF},
            data=discovery_info,
        )
        assert result["type"] == FlowResultType.FORM
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"], user_input={}
        )
        assert result2["type"] == FlowResultType.CREATE_ENTRY
        assert result2["data"] == {CONF_URL: "http://[2001:db8::1]:8085"}


async def test_zeroconf_link_local_rejected(hass: HomeAssistant) -> None:
    """Test Zeroconf discovery aborts on link-local addresses."""
    discovery_info = make_zeroconf_info("169.254.10.20", 8085)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_ZEROCONF},
        data=discovery_info,
    )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "link_local_address"


@pytest.mark.skipif(
    not hasattr(config_entries, "SOURCE_RECONFIGURE"),
    reason="SOURCE_RECONFIGURE requires Home Assistant 2024.4+",
)
async def test_reconfigure_step_success(hass: HomeAssistant) -> None:
    """Test reconfiguring an existing config entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="http://192.168.1.50:8085",
        data={CONF_URL: "http://192.168.1.50:8085"},
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.vacuula.config_flow.VacuulaApiClient.async_get_server_info",
        return_value={"version": "1.5.0"},
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={
                "source": getattr(config_entries, "SOURCE_RECONFIGURE", "reconfigure"),
                "entry_id": entry.entry_id,
            },
        )
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "reconfigure"

        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_URL: "http://192.168.1.75:8085"},
        )
        assert result2["type"] == FlowResultType.ABORT
        assert result2["reason"] == "reconfigure_successful"
        assert entry.data[CONF_URL] == "http://192.168.1.75:8085"
        assert entry.unique_id == "http://192.168.1.75:8085"
