"""Command line front end -- the acceptance test for the protocol library.

python -m balboa 10.0.0.9                     # gateway, default port 8899
python -m balboa 10.0.0.5 --port 4257         # Balboa Wi-Fi module
python -m balboa /dev/ttyUSB0 --serial        # local RS-485 adapter
python -m balboa 10.0.0.9 --toggle pump1      # switch something
python -m balboa --discover                   # find Wi-Fi modules
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from .client import SpaClient
from .const import MAX_AUX, MAX_LIGHTS, MAX_PUMPS, ToggleItem
from .discovery import async_discover
from .state import SpaState
from .transport import GATEWAY_PORT, SerialTransport, TcpTransport, Transport


def _render(state: SpaState, available: bool) -> str:
    status = state.status
    if status is None:
        return "waiting for data ..."

    unit = "C" if status.temperature_unit.value == "celsius" else "F"
    current = f"{status.current_temperature:g}" if status.current_temperature else "--"
    lines = [
        f"  {state.model}  (software {state.software_version or '?'})",
        f"  water {current} °{unit}   target {status.target_temperature:g} °{unit}"
        f"   {'HEATING' if status.heating else 'idle'}",
        f"  mode {status.heat_mode.name.lower()}"
        f"   range {status.temperature_range.name.lower()}"
        f"   clock {status.hour:02d}:{status.minute:02d}",
    ]

    controls: list[str] = []
    for index in range(MAX_PUMPS):
        if speeds := state.pump_speeds(index):
            value = state.pump_state(index)
            shown = (
                "on" if speeds == 1 and value else ("off" if not value else str(value))
            )
            controls.append(f"pump{index + 1}={shown}")
    if state.blower_speeds:
        controls.append(f"blower={status.blower}")
    for index in range(MAX_LIGHTS):
        if state.has_light(index):
            on = "on" if state.is_light_on(index) else "off"
            controls.append(f"light{index + 1}={on}")
    for index in range(MAX_AUX):
        if state.has_aux(index):
            on = "on" if state.is_aux_on(index) else "off"
            controls.append(f"aux{index + 1}={on}")
    if state.has_circulation_pump:
        controls.append(f"circ={'on' if status.circulation_pump else 'off'}")
    if state.has_mister:
        controls.append(f"mister={'on' if status.mister else 'off'}")
    if controls:
        lines.append("  " + "  ".join(controls))

    if status.notification.name != "NONE":
        lines.append(f"  notification: {status.notification.name.lower()}")
    if not available:
        lines.append("  !! stale -- no frames arriving")
    if state.mac_address:
        lines.append(f"  mac {state.mac_address}")
    return "\n".join(lines)


async def _run(args: argparse.Namespace) -> int:
    transport: Transport = (
        SerialTransport(args.target)
        if args.serial
        else TcpTransport(args.target, args.port)
    )
    client = SpaClient(transport)

    print(f"connecting to {transport.description} ...")
    if not await client.connect():
        print("failed: no usable configuration received")
        await client.disconnect()
        return 1

    print("connected.\n")
    print(_render(client.state, client.available))

    try:
        if args.toggle:
            item = ToggleItem[args.toggle.upper()]
            print(f"\ntoggling {item.name.lower()} ...")
            await client.toggle_item(item)
            await asyncio.sleep(2)
            print(_render(client.state, client.available))
            return 0

        print("\nwatching for changes, Ctrl+C to stop\n")
        changed = asyncio.Event()
        client.subscribe(changed.set)
        while True:
            await changed.wait()
            changed.clear()
            print(_render(client.state, client.available))
            print(
                f"  [frames {client.frames_read}  crc errors {client.crc_errors}"
                f"  unknown {client.unknown_messages}]\n"
            )
    except KeyboardInterrupt:
        return 0
    finally:
        await client.disconnect()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="balboa", description=__doc__)
    parser.add_argument("target", nargs="?", help="IP address or serial device")
    parser.add_argument("--port", type=int, default=GATEWAY_PORT)
    parser.add_argument("--serial", action="store_true", help="target is a serial device")
    parser.add_argument("--toggle", metavar="ITEM", help="e.g. pump1, light1, blower")
    parser.add_argument(
        "--discover", action="store_true", help="search for Wi-Fi modules"
    )
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    if args.discover:
        found = asyncio.run(async_discover())
        if not found:
            print("no Balboa Wi-Fi module found")
            return 1
        for spa in found:
            print(f"{spa.host}  {spa.hostname}  {spa.mac_address}")
        return 0

    if not args.target:
        parser.error("target is required unless --discover is given")
    return asyncio.run(_run(args))


if __name__ == "__main__":
    sys.exit(main())
