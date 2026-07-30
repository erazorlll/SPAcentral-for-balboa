"""Discovery of Balboa Wi-Fi modules via UDP broadcast.

Only the original Balboa Wi-Fi module answers this. RS-485 gateways cannot be
found: they carry their own manufacturer's MAC and are generic bridges with no
Balboa identity. Those setups are added by hand, which is a property of the
hardware, not a gap here.

Not verified against a real Wi-Fi module.
"""

from __future__ import annotations

import asyncio
import logging
import socket
from dataclasses import dataclass

_LOGGER = logging.getLogger(__name__)

__all__ = ["BALBOA_OUI", "DiscoveredSpa", "async_discover"]

DISCOVERY_PORT = 30303
DISCOVERY_MESSAGE = b"Discovery: Who is out there?"
#: Balboa Instruments' MAC prefix; also used for Home Assistant's DHCP matcher.
BALBOA_OUI = "00:15:27"
DEFAULT_TIMEOUT = 5.0


@dataclass(frozen=True, slots=True)
class DiscoveredSpa:
    host: str
    hostname: str
    mac_address: str


class _DiscoveryProtocol(asyncio.DatagramProtocol):
    def __init__(self) -> None:
        self.results: dict[str, DiscoveredSpa] = {}

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        try:
            lines = data.decode("ascii", errors="replace").split("\r\n")
        except Exception:
            return
        if len(lines) < 2:
            return

        hostname = lines[0].strip()
        mac = lines[1].strip().replace("-", ":").lower()
        if not mac.startswith(BALBOA_OUI):
            return  # some other device answered the broadcast

        host = addr[0]
        self.results[host] = DiscoveredSpa(host=host, hostname=hostname, mac_address=mac)


async def async_discover(timeout: float = DEFAULT_TIMEOUT) -> list[DiscoveredSpa]:
    """Broadcast on the local network and collect the answers."""
    loop = asyncio.get_running_loop()
    try:
        transport, protocol = await loop.create_datagram_endpoint(
            _DiscoveryProtocol,
            local_addr=("0.0.0.0", 0),
            allow_broadcast=True,
        )
    except OSError as err:
        _LOGGER.debug("discovery socket unavailable: %s", err)
        return []

    try:
        transport.get_extra_info("socket").setsockopt(
            socket.SOL_SOCKET, socket.SO_BROADCAST, 1
        )
        transport.sendto(DISCOVERY_MESSAGE, ("255.255.255.255", DISCOVERY_PORT))
        await asyncio.sleep(timeout)
        return list(protocol.results.values())
    except OSError as err:
        _LOGGER.debug("discovery failed: %s", err)
        return []
    finally:
        transport.close()
