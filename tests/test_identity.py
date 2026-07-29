"""Device identity -- the seven cases from docs/03-geraeteidentitaet.md §6.

The case that matters most here is two spas without a MAC. Both of the
controllers this was built against are the same model on the same firmware and
neither reports a MAC, so anything derived from the device itself would make
them collide.
"""

from __future__ import annotations

import pytest
from homeassistant.const import CONF_HOST, CONF_MAC, CONF_PORT
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.balboa_spacentral.const import (
    CONF_CONNECTION,
    CONF_IDENTITY_SOURCE,
    CONNECTION_GATEWAY,
    DOMAIN,
    IDENTITY_ENTRY_ID,
    IDENTITY_MAC,
)
from custom_components.balboa_spacentral.identity import (
    device_key,
    entity_unique_id,
    initial_identity_source,
)


def _entry(*, mac: str | None = None, host: str = "10.0.0.9") -> MockConfigEntry:
    data = {
        CONF_CONNECTION: CONNECTION_GATEWAY,
        CONF_HOST: host,
        CONF_PORT: 8899,
        CONF_IDENTITY_SOURCE: initial_identity_source(mac),
    }
    if mac:
        data[CONF_MAC] = mac
    return MockConfigEntry(domain=DOMAIN, data=data, title="Spa")


def test_identity_source_prefers_the_mac() -> None:
    assert initial_identity_source("00:15:27:aa:bb:cc") == IDENTITY_MAC
    assert initial_identity_source(None) == IDENTITY_ENTRY_ID


def test_key_uses_the_mac_when_there_is_one() -> None:
    entry = _entry(mac="00:15:27:aa:bb:cc")
    assert device_key(entry) == "001527aabbcc"


def test_key_falls_back_to_the_entry_id() -> None:
    entry = _entry()
    assert device_key(entry) == entry.entry_id


def test_two_spas_with_macs_do_not_collide() -> None:
    a = _entry(mac="00:15:27:aa:bb:cc")
    b = _entry(mac="00:15:27:dd:ee:ff", host="10.0.0.10")
    assert device_key(a) != device_key(b)


def test_two_spas_without_macs_do_not_collide() -> None:
    """The real situation: identical model, identical firmware, no MAC."""
    a = _entry()
    b = _entry(host="192.168.0.23")
    assert device_key(a) != device_key(b)
    assert entity_unique_id(a, "water_temperature") != entity_unique_id(
        b, "water_temperature"
    )


def test_mixed_setups_do_not_collide() -> None:
    a = _entry(mac="00:15:27:aa:bb:cc")
    b = _entry(host="192.168.0.23")
    assert device_key(a) != device_key(b)


def test_changing_the_host_keeps_the_identity() -> None:
    """A DHCP lease must never orphan entities."""
    entry = _entry()
    before = device_key(entry)
    entry.data = {**entry.data, CONF_HOST: "10.0.0.99"}
    assert device_key(entry) == before


def test_a_late_mac_does_not_change_the_identity() -> None:
    """Recorded once, honoured forever -- otherwise entities would be recreated."""
    entry = _entry()
    before = device_key(entry)
    entry.data = {**entry.data, CONF_MAC: "00:15:27:aa:bb:cc"}
    assert device_key(entry) == before, (
        "identity_source stays entry_id, so the key must not switch to the MAC"
    )


@pytest.mark.parametrize("key", ["water_temperature", "heating", "pump_1"])
def test_entity_ids_are_prefixed_by_the_device(key: str) -> None:
    entry = _entry()
    assert entity_unique_id(entry, key) == f"{entry.entry_id}_{key}"
