"""Tests for the Vacuula config flow."""

from __future__ import annotations

import ipaddress
from typing import Any
from unittest.mock import patch

import pytest
from homeassistant import config_entries
from homeassistant.const import CONF_URL
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

try:
    from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
except ImportError, ModuleNotFoundError:
    try:
        from homeassistant.components.zeroconf import ZeroconfServiceInfo  # type: ignore[no-redef]
    except ImportError, ModuleNotFoundError:
        from dataclasses import dataclass

        @dataclass
        class ZeroconfServiceInfo:  # type: ignore[no-redef]
            ip_address: Any = None
            ip_addresses: list[Any] | None = None
            host: str = ""
            addresses: list[str] | None = None
            port: int = 80
            hostname: str = ""
            type: str = ""
            name: str = ""
            properties: dict[str, Any] | None = None


from custom_components.vacuula.api import VacuulaApiError
from custom_components.vacuula.const import DOMAIN


@pytest.fixture(autouse=True)
def bypass_setup_entry():
    """Bypass entry setup during config flow tests."""
    with patch("custom_components.vacuula.async_setup_entry", return_value=True):
        yield


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


async def test_user_step_empty_and_query_urls(hass: HomeAssistant) -> None:
    """Test empty URL and URL with query params return invalid_url."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    # Empty URL
    result_empty = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_URL: "   "},
    )
    assert result_empty["type"] == FlowResultType.FORM
    assert result_empty["errors"] == {CONF_URL: "invalid_url"}

    # Query param URL
    result_query = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_URL: "http://192.168.1.50:8085?query=1"},
    )
    assert result_query["type"] == FlowResultType.FORM
    assert result_query["errors"] == {CONF_URL: "invalid_url"}


async def test_user_step_non_dict_server_info(hass: HomeAssistant) -> None:
    """Test cannot_connect when server returns non-dict payload."""
    with patch(
        "custom_components.vacuula.config_flow.VacuulaApiClient.async_get_server_info",
        return_value="unexpected string response",
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input={CONF_URL: "http://192.168.1.50:8085"},
        )
        assert result2["type"] == FlowResultType.FORM
        assert result2["errors"] == {"base": "cannot_connect"}


async def test_zeroconf_host_fallback_and_connection_failures(
    hass: HomeAssistant,
) -> None:
    """Test zeroconf host fallback when ip_address is None and connection errors."""
    from dataclasses import dataclass

    @dataclass
    class HostOnlyZeroconfInfo:
        host: str = "192.168.1.60"
        port: int = 8085
        hostname: str = "vacuula.local."
        name: str = "vacuula"
        type: str = "_vacuula._tcp.local."
        ip_address: Any = None
        ip_addresses: list[Any] | None = None
        addresses: list[str] | None = None
        properties: dict[str, Any] | None = None

    # 1. Connection error during Zeroconf
    with patch(
        "custom_components.vacuula.config_flow.VacuulaApiClient.async_get_server_info",
        side_effect=VacuulaApiError("Cannot reach server"),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_ZEROCONF},
            data=HostOnlyZeroconfInfo(),
        )
        assert result["type"] == FlowResultType.ABORT
        assert result["reason"] == "cannot_connect"

    # 2. Non-dict response during Zeroconf
    with patch(
        "custom_components.vacuula.config_flow.VacuulaApiClient.async_get_server_info",
        return_value=["invalid", "list"],
    ):
        result2 = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_ZEROCONF},
            data=HostOnlyZeroconfInfo(),
        )
        assert result2["type"] == FlowResultType.ABORT
        assert result2["reason"] == "cannot_connect"
