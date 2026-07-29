"""The setup dialog: all three connection kinds, every failure, duplicates."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import SOURCE_DHCP, SOURCE_USER
from homeassistant.const import CONF_HOST, CONF_MAC, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.balboa_spacentral.const import (
    CONF_CONNECTION,
    CONF_DEVICE_PATH,
    CONF_IDENTITY_SOURCE,
    CONNECTION_GATEWAY,
    CONNECTION_SERIAL,
    CONNECTION_WIFI_MODULE,
    DOMAIN,
    IDENTITY_ENTRY_ID,
    IDENTITY_MAC,
)

PROBE = "custom_components.balboa_spacentral.config_flow._probe"


@pytest.fixture(autouse=True)
def _no_setup():
    """Do not actually connect after the flow finishes."""
    with patch(
        "custom_components.balboa_spacentral.async_setup_entry",
        return_value=True,
    ):
        yield


async def _choose(hass: HomeAssistant, connection: str) -> dict:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_CONNECTION: connection}
    )


async def test_gateway_is_offered_first(hass: HomeAssistant) -> None:
    """The setup this integration exists for should not be buried."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    schema = result["data_schema"].schema
    default = next(iter(schema.values()))
    assert result["data_schema"]({})[CONF_CONNECTION] == CONNECTION_GATEWAY
    assert default is not None


async def test_gateway_setup(hass: HomeAssistant) -> None:
    result = await _choose(hass, CONNECTION_GATEWAY)
    assert result["step_id"] == "gateway"
    assert result["data_schema"]({CONF_HOST: "x"})[CONF_PORT] == 8899

    with patch(PROBE, AsyncMock(return_value={"model": "BP6013G3", "mac": None})):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "192.168.0.56", CONF_PORT: 8899}
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "BP6013G3"
    assert result["data"][CONF_CONNECTION] == CONNECTION_GATEWAY
    assert result["data"][CONF_IDENTITY_SOURCE] == IDENTITY_ENTRY_ID
    assert CONF_MAC not in result["data"]


async def test_wifi_module_defaults_to_its_port(hass: HomeAssistant) -> None:
    result = await _choose(hass, CONNECTION_WIFI_MODULE)
    assert result["step_id"] == "wifi_module"
    assert result["data_schema"]({CONF_HOST: "x"})[CONF_PORT] == 4257

    with patch(
        PROBE,
        AsyncMock(return_value={"model": "BP6013G3", "mac": "00:15:27:aa:bb:cc"}),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "10.0.0.5", CONF_PORT: 4257}
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_IDENTITY_SOURCE] == IDENTITY_MAC
    assert result["data"][CONF_MAC] == "00:15:27:aa:bb:cc"


async def test_serial_setup(hass: HomeAssistant) -> None:
    result = await _choose(hass, CONNECTION_SERIAL)
    assert result["step_id"] == "serial"

    with patch(PROBE, AsyncMock(return_value={"model": "BP6013G3", "mac": None})):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_DEVICE_PATH: "/dev/serial/by-id/usb-rs485"}
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_DEVICE_PATH] == "/dev/serial/by-id/usb-rs485"


@pytest.mark.parametrize(
    ("exception", "expected"),
    [
        ("CannotConnectError", "cannot_connect"),
        ("NoDataError", "no_data"),
    ],
)
async def test_connection_errors_are_explained(
    hass: HomeAssistant, exception: str, expected: str
) -> None:
    from custom_components.balboa_spacentral import config_flow

    result = await _choose(hass, CONNECTION_GATEWAY)
    with patch(PROBE, AsyncMock(side_effect=getattr(config_flow, exception))):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "192.168.0.56", CONF_PORT: 8899}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": expected}


async def test_unexpected_errors_do_not_leak(hass: HomeAssistant) -> None:
    result = await _choose(hass, CONNECTION_GATEWAY)
    with patch(PROBE, AsyncMock(side_effect=RuntimeError("boom"))):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "192.168.0.56", CONF_PORT: 8899}
        )
    assert result["errors"] == {"base": "unknown"}


async def test_the_same_gateway_cannot_be_added_twice(hass: HomeAssistant) -> None:
    MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_CONNECTION: CONNECTION_GATEWAY,
            CONF_HOST: "192.168.0.56",
            CONF_PORT: 8899,
            CONF_IDENTITY_SOURCE: IDENTITY_ENTRY_ID,
        },
    ).add_to_hass(hass)

    result = await _choose(hass, CONNECTION_GATEWAY)
    with patch(PROBE, AsyncMock(return_value={"model": "BP6013G3", "mac": None})):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "192.168.0.56", CONF_PORT: 8899}
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_two_spas_without_macs_can_both_be_added(hass: HomeAssistant) -> None:
    """The actual deployment: two identical controllers, neither with a MAC."""
    for host in ("192.168.0.56", "192.168.0.23"):
        result = await _choose(hass, CONNECTION_GATEWAY)
        with patch(PROBE, AsyncMock(return_value={"model": "BP6013G3", "mac": None})):
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], {CONF_HOST: host, CONF_PORT: 8899}
            )
        assert result["type"] is FlowResultType.CREATE_ENTRY

    entries = hass.config_entries.async_entries(DOMAIN)
    assert len(entries) == 2
    assert entries[0].entry_id != entries[1].entry_id


async def test_dhcp_discovery_offers_the_spa(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_DHCP},
        data=DhcpServiceInfo(ip="10.0.0.5", hostname="BWGSPA", macaddress="001527aabbcc"),
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "discovery_confirm"

    with patch(
        PROBE,
        AsyncMock(return_value={"model": "BP6013G3", "mac": "00:15:27:aa:bb:cc"}),
    ):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_HOST] == "10.0.0.5"
    assert result["data"][CONF_PORT] == 4257


async def test_reconfigure_keeps_the_entry(hass: HomeAssistant) -> None:
    """Moving the spa to a new address must not recreate anything."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_CONNECTION: CONNECTION_GATEWAY,
            CONF_HOST: "192.168.0.56",
            CONF_PORT: 8899,
            CONF_IDENTITY_SOURCE: IDENTITY_ENTRY_ID,
        },
    )
    entry.add_to_hass(hass)
    entry_id_before = entry.entry_id

    result = await entry.start_reconfigure_flow(hass)
    assert result["step_id"] == "reconfigure"

    with patch(PROBE, AsyncMock(return_value={"model": "BP6013G3", "mac": None})):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "192.168.0.77", CONF_PORT: 8899}
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_HOST] == "192.168.0.77"
    assert entry.entry_id == entry_id_before
