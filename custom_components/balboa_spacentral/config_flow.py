"""Setting a spa up through the user interface.

Three connection kinds, described in the words people use for their hardware
rather than in protocol terms. The gateway comes first: it is the setup this
integration exists for and the one no other Balboa client serves.
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST, CONF_MAC, CONF_PORT
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import format_mac
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo

from .balboa import GATEWAY_PORT, WIFI_MODULE_PORT, SpaClient
from .const import (
    CONF_CONNECTION,
    CONF_DEVICE_PATH,
    CONF_IDENTITY_SOURCE,
    CONNECTION_GATEWAY,
    CONNECTION_SERIAL,
    CONNECTION_WIFI_MODULE,
    DEFAULT_SYNC_TIME,
    DOMAIN,
    OPT_SYNC_TIME,
)
from .identity import initial_identity_source

_LOGGER = logging.getLogger(__name__)


async def _probe(data: dict[str, Any]) -> dict[str, Any]:
    """Connect for real and report what came back.

    Raises `CannotConnectError` if the link fails, and `NoDataError` if it opens
    but the controller stays silent -- the everyday gateway misconfiguration,
    which deserves its own message rather than a generic failure.
    """
    from . import build_transport

    transport = build_transport(data)
    client = SpaClient(transport)
    try:
        if not await client.connect():
            if client.frames_read:
                raise NoDataError
            raise CannotConnectError
        return {
            "model": client.state.model,
            "mac": client.state.mac_address,
        }
    finally:
        await client.disconnect()


# `domain=` is Home Assistant's registration hook; mypy cannot see it because
# the framework's own types are deliberately skipped (see pyproject.toml).
class BalboaSpacentralConfigFlow(ConfigFlow, domain=DOMAIN):  # type: ignore[call-arg]
    """Handle the setup dialog."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovered: dict[str, Any] = {}

    # ── Entry points ─────────────────────────────────────────────────────────

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask which kind of connection this spa uses."""
        if user_input is not None:
            kind = user_input[CONF_CONNECTION]
            if kind == CONNECTION_SERIAL:
                return await self.async_step_serial()
            if kind == CONNECTION_WIFI_MODULE:
                return await self.async_step_wifi_module()
            return await self.async_step_gateway()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_CONNECTION, default=CONNECTION_GATEWAY): vol.In(
                        [
                            CONNECTION_GATEWAY,
                            CONNECTION_WIFI_MODULE,
                            CONNECTION_SERIAL,
                        ]
                    )
                }
            ),
        )

    async def async_step_dhcp(self, discovery_info: DhcpServiceInfo) -> ConfigFlowResult:
        """A Balboa Wi-Fi module appeared on the network."""
        await self.async_set_unique_id(format_mac(discovery_info.macaddress))
        self._abort_if_unique_id_configured(updates={CONF_HOST: discovery_info.ip})
        self._async_abort_entries_match({CONF_HOST: discovery_info.ip})

        self._discovered = {
            CONF_CONNECTION: CONNECTION_WIFI_MODULE,
            CONF_HOST: discovery_info.ip,
            CONF_PORT: WIFI_MODULE_PORT,
        }
        self.context["title_placeholders"] = {"name": discovery_info.ip}
        return await self.async_step_discovery_confirm()

    async def async_step_discovery_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user accept a discovered spa."""
        if user_input is not None:
            return await self._create(self._discovered)

        return self.async_show_form(
            step_id="discovery_confirm",
            description_placeholders={"host": self._discovered[CONF_HOST]},
        )

    # ── Manual paths ─────────────────────────────────────────────────────────

    async def async_step_gateway(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """An RS-485 gateway reachable over the network."""
        return await self._network_step(
            "gateway", CONNECTION_GATEWAY, GATEWAY_PORT, user_input
        )

    async def async_step_wifi_module(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """The original Balboa Wi-Fi module."""
        return await self._network_step(
            "wifi_module", CONNECTION_WIFI_MODULE, WIFI_MODULE_PORT, user_input
        )

    async def _network_step(
        self,
        step_id: str,
        connection: str,
        default_port: int,
        user_input: dict[str, Any] | None,
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {
                CONF_CONNECTION: connection,
                CONF_HOST: user_input[CONF_HOST],
                CONF_PORT: user_input[CONF_PORT],
            }
            self._async_abort_entries_match(
                {CONF_HOST: data[CONF_HOST], CONF_PORT: data[CONF_PORT]}
            )
            errors = await self._try(data)
            if not errors:
                return await self._create(data)

        return self.async_show_form(
            step_id=step_id,
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST): str,
                    vol.Required(CONF_PORT, default=default_port): int,
                }
            ),
            errors=errors,
        )

    async def async_step_serial(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """A serial adapter attached to the Home Assistant host."""
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {
                CONF_CONNECTION: CONNECTION_SERIAL,
                CONF_DEVICE_PATH: user_input[CONF_DEVICE_PATH],
            }
            self._async_abort_entries_match({CONF_DEVICE_PATH: data[CONF_DEVICE_PATH]})
            errors = await self._try(data)
            if not errors:
                return await self._create(data)

        return self.async_show_form(
            step_id="serial",
            data_schema=vol.Schema({vol.Required(CONF_DEVICE_PATH): str}),
            errors=errors,
        )

    # ── Reconfiguration ──────────────────────────────────────────────────────

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change where the spa lives without losing its entities.

        The identity stays put on purpose: an IP change or a move from the
        Wi-Fi module to a gateway must not orphan anything.
        """
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            data = {**entry.data, **user_input}
            errors = await self._try(data)
            if not errors:
                return self.async_update_reload_and_abort(entry, data_updates=data)

        if entry.data.get(CONF_CONNECTION) == CONNECTION_SERIAL:
            schema = vol.Schema(
                {
                    vol.Required(
                        CONF_DEVICE_PATH, default=entry.data.get(CONF_DEVICE_PATH)
                    ): str
                }
            )
        else:
            schema = vol.Schema(
                {
                    vol.Required(CONF_HOST, default=entry.data.get(CONF_HOST)): str,
                    vol.Required(CONF_PORT, default=entry.data.get(CONF_PORT)): int,
                }
            )

        return self.async_show_form(
            step_id="reconfigure", data_schema=schema, errors=errors
        )

    # ── Helpers ──────────────────────────────────────────────────────────────

    async def _try(self, data: dict[str, Any]) -> dict[str, str]:
        """Probe the connection and translate failures into form errors."""
        try:
            self._discovered = {**data, **await _probe(data)}
        except CannotConnectError:
            return {"base": "cannot_connect"}
        except NoDataError:
            return {"base": "no_data"}
        except Exception:
            _LOGGER.exception("unexpected error while probing")
            return {"base": "unknown"}
        return {}

    async def _create(self, data: dict[str, Any]) -> ConfigFlowResult:
        """Store the entry, freezing how it will be identified."""
        probed = self._discovered
        mac = probed.get("mac")
        if mac:
            await self.async_set_unique_id(format_mac(mac), raise_on_progress=False)
            self._abort_if_unique_id_configured()

        entry_data = {
            **{k: v for k, v in data.items() if k not in ("model", "mac")},
            CONF_IDENTITY_SOURCE: initial_identity_source(mac),
        }
        if mac:
            entry_data[CONF_MAC] = mac

        return self.async_create_entry(
            title=probed.get("model") or "Balboa Spa", data=entry_data
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> OptionsFlow:
        return BalboaSpacentralOptionsFlow()


class BalboaSpacentralOptionsFlow(OptionsFlow):
    """The handful of settings worth changing later."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        OPT_SYNC_TIME,
                        default=self.config_entry.options.get(
                            OPT_SYNC_TIME, DEFAULT_SYNC_TIME
                        ),
                    ): bool
                }
            ),
        )


class CannotConnectError(HomeAssistantError):
    """The link could not be established at all."""


class NoDataError(HomeAssistantError):
    """The link opened but the controller never said anything."""
