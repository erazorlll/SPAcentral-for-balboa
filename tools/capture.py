#!/usr/bin/env python3
"""Record and analyse the raw byte stream of a Balboa spa controller.

Phase 0 tool. It answers the open design questions before a single line of the
integration is written:

  * Does the controller answer a configuration request with a MAC address?
    (decides whether entity identity can use the MAC or has to fall back)
  * Do RS-485 "Ready" tokens appear? (decides the default write policy)
  * Which message types occur, and does the assumed CRC hold?

It writes three files:

  <prefix>.bin    raw stream, used as a test fixture later
  <prefix>.jsonl  one decoded frame per line, with timestamps
  <prefix>.txt    human readable log

Usage:
    python capture.py 192.168.1.50 --seconds 120 --prefix ew11_idle
    python capture.py 192.168.1.50 --seconds 60  --prefix ew11_probe --probe
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

DELIMITER = 0x7E

# Frames the Ruby gem sends on startup. Replaying them tells us whether this
# setup answers them at all -- passive listening never shows a response,
# because nobody asked.
PROBES: dict[str, bytes] = {
    "configuration_request": bytes([0x0A, 0xBF, 0x04]),
    "control_config_1": bytes([0x0A, 0xBF, 0x22, 0x02, 0x00, 0x00]),
    "control_config_2": bytes([0x0A, 0xBF, 0x22, 0x00, 0x00, 0x01]),
    "filter_cycles": bytes([0x0A, 0xBF, 0x22, 0x01, 0x00, 0x00]),
}

# The first payload byte selects which answer you get: 0x02 control
# configuration, 0x01 filter cycles, 0x20 the fault log. So it is a selector,
# not an entry number -- asking for "entry 1" with 0x01 would just return the
# filter cycles again.
#
# Where the entry number lives is unknown, so these probe the two plausible
# places without disturbing the other selectors.
FAULT_LOG_PROBES: dict[str, bytes] = {
    "fault_log_latest": bytes([0x0A, 0xBF, 0x22, 0x20, 0x00, 0x00]),
    "fault_log_byte1_is_1": bytes([0x0A, 0xBF, 0x22, 0x20, 0x01, 0x00]),
    "fault_log_byte2_is_1": bytes([0x0A, 0xBF, 0x22, 0x20, 0x00, 0x01]),
}

MESSAGE_TYPES: dict[bytes, str] = {
    bytes([0xAF, 0x13]): "status_update",
    bytes([0xBF, 0x94]): "configuration_response  <-- carries the MAC",
    bytes([0xBF, 0x24]): "control_configuration (model, version)",
    bytes([0xBF, 0x2E]): "control_configuration_2 (pumps, lights, blower)",
    bytes([0xBF, 0x23]): "filter_cycles",
    bytes([0xBF, 0x28]): "FAULT LOG ENTRY",
    bytes([0xBF, 0xE1]): "error",
    bytes([0xBF, 0x06]): "READY  <-- RS-485 arbitration token",
    bytes([0xBF, 0x07]): "nothing_to_send",
    bytes([0xBF, 0x00]): "new_client_clear_to_send",
    bytes([0xBF, 0x04]): "configuration_request (outgoing)",
    bytes([0xBF, 0x11]): "toggle_item (outgoing)",
    bytes([0xBF, 0x20]): "set_temperature (outgoing)",
    bytes([0xBF, 0x21]): "set_time (outgoing)",
    bytes([0xBF, 0x22]): "control_config_request (outgoing)",
    bytes([0xBF, 0x27]): "set_temperature_scale (outgoing)",
}


def crc8(data: bytes) -> int:
    """CRC-8, poly 0x07, init 0x02, final XOR 0x02 (per the Balboa protocol)."""
    crc = 0x02
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = ((crc << 1) ^ 0x07) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc ^ 0x02


def build_frame(payload: bytes) -> bytes:
    """Wrap a payload (src + type + data) into a complete frame."""
    length = len(payload) + 2
    body = bytes([length]) + payload
    return bytes([DELIMITER]) + body + bytes([crc8(body), DELIMITER])


def describe(payload: bytes) -> str:
    """Human readable name for a frame payload (channel + type + data)."""
    if len(payload) < 3:
        return "too_short"
    return MESSAGE_TYPES.get(payload[1:3], f"unknown_{payload[1]:02x}{payload[2]:02x}")


def describe_fault(payload: bytes) -> str | None:
    """Decode a fault log entry, if that is what this frame is."""
    if payload[1:3] != bytes([0xBF, 0x28]) or len(payload) < 13:
        return None
    d = payload[3:]
    return (
        f"entry {d[1] + 1}/{d[0]}  code {d[2]}  {d[3]} days ago  "
        f"{d[4]:02d}:{d[5]:02d}  flags 0x{d[6]:02x}  "
        f"set {d[7]}  sensorA {d[8]}  sensorB {d[9]}"
    )


def extract_mac(payload: bytes) -> str | None:
    """Pull the MAC out of a configuration response (0x?? BF 94)."""
    if payload[1:3] != bytes([0xBF, 0x94]) or len(payload) < 12:
        return None
    # payload = channel, BF, 94, then the data block; MAC sits at data[3:9]
    mac = payload[6:12]
    if not any(mac):
        return None
    return ":".join(f"{b:02x}" for b in mac)


class FrameReader:
    """Turns a byte stream into validated frames. Tolerates split reads."""

    def __init__(self) -> None:
        self.buffer = bytearray()
        self.crc_errors = 0
        self.discarded = 0

    def feed(self, chunk: bytes) -> list[bytes]:
        self.buffer.extend(chunk)
        frames: list[bytes] = []

        while True:
            start = self.buffer.find(DELIMITER)
            if start < 0:
                self.discarded += len(self.buffer)
                self.buffer.clear()
                break
            if start:
                self.discarded += start
                del self.buffer[:start]
            if len(self.buffer) < 2:
                break

            length = self.buffer[1]
            total = length + 2
            if length < 3 or total > 64:
                # implausible length -- resynchronise past this delimiter
                self.discarded += 1
                del self.buffer[:1]
                continue
            if len(self.buffer) < total:
                break  # wait for the rest

            frame = bytes(self.buffer[:total])
            if frame[-1] != DELIMITER:
                self.discarded += 1
                del self.buffer[:1]
                continue
            if crc8(frame[1:-2]) != frame[-2]:
                self.crc_errors += 1
                self.discarded += 1
                del self.buffer[:1]
                continue

            frames.append(frame)
            del self.buffer[:total]

        return frames


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("host", help="IP of the EW11 / Wi-Fi module")
    parser.add_argument(
        "--port",
        type=int,
        default=8899,
        help="8899 for EW11, 4257 for the Balboa Wi-Fi module",
    )
    parser.add_argument("--seconds", type=int, default=120, help="capture duration")
    parser.add_argument("--prefix", default="capture", help="output file prefix")
    parser.add_argument(
        "--probe",
        action="store_true",
        help="send the four startup requests to see whether they are answered",
    )
    parser.add_argument(
        "--fault-log",
        action="store_true",
        help="also ask for fault log entries (implies --probe)",
    )
    parser.add_argument("--outdir", default="fixtures", help="output directory")
    args = parser.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    raw_path = outdir / f"{args.prefix}.bin"
    jsonl_path = outdir / f"{args.prefix}.jsonl"
    text_path = outdir / f"{args.prefix}.txt"

    print(f"Connecting to {args.host}:{args.port} ...")
    try:
        sock = socket.create_connection((args.host, args.port), timeout=10)
    except OSError as err:
        print(f"FAILED: {err}")
        print("\nIf the add-on is running it may be holding the only allowed connection.")
        print("Stop it and try again.")
        return 1
    sock.settimeout(1.0)
    print("Connected. Recording ...\n")

    reader = FrameReader()
    counts: Counter[str] = Counter()
    macs: set[str] = set()
    faults: list[str] = []
    started = time.monotonic()
    first_frame_at: float | None = None
    probe_sent = False
    closed_by_peer = False

    with (
        raw_path.open("wb") as raw_f,
        jsonl_path.open("w", encoding="utf-8") as jsonl_f,
        text_path.open("w", encoding="utf-8") as text_f,
    ):
        try:
            while time.monotonic() - started < args.seconds:
                # send the probes once, a few seconds in, so the idle baseline
                # is recorded first
                elapsed_now = time.monotonic() - started
                if (args.probe or args.fault_log) and not probe_sent and elapsed_now > 5:
                    probes = dict(PROBES)
                    if args.fault_log:
                        probes.update(FAULT_LOG_PROBES)
                    for name, payload in probes.items():
                        frame = build_frame(payload)
                        sock.sendall(frame)
                        line = f"--> SENT {name}: {frame.hex(' ')}"
                        print(line)
                        text_f.write(line + "\n")
                        time.sleep(0.5)
                    probe_sent = True

                try:
                    chunk = sock.recv(4096)
                except TimeoutError:
                    continue
                if not chunk:
                    closed_by_peer = True
                    print("Connection closed by the remote end.")
                    break

                raw_f.write(chunk)
                raw_f.flush()

                for frame in reader.feed(chunk):
                    now = time.monotonic()
                    if first_frame_at is None:
                        first_frame_at = now
                    payload = frame[2:-2]
                    name = describe(payload)
                    counts[name] += 1

                    if mac := extract_mac(payload):
                        macs.add(mac)
                        print(f"    MAC ADDRESS FOUND: {mac}")
                    if fault := describe_fault(payload):
                        faults.append(fault)
                        print(f"    FAULT LOG: {fault}")

                    record = {
                        "t": round(now - started, 3),
                        "utc": datetime.now(UTC).isoformat(),
                        "type": name,
                        "hex": frame.hex(" "),
                    }
                    jsonl_f.write(json.dumps(record) + "\n")
                    text_f.write(f"[{record['t']:8.3f}] {name:<40} {record['hex']}\n")

                    elapsed = int(now - started)
                    if elapsed and elapsed % 15 == 0:
                        print(f"  {elapsed:3d}s  {sum(counts.values())} frames", end="\r")
        except KeyboardInterrupt:
            print("\nStopped early.")
        finally:
            sock.close()

    # ---- verdict -----------------------------------------------------------
    total = sum(counts.values())
    print("\n" + "=" * 66)
    print("RESULT")
    print("=" * 66)
    print(f"Frames captured : {total}")
    print(f"CRC errors      : {reader.crc_errors}")
    print(f"Bytes discarded : {reader.discarded}")
    print()

    if not total:
        print("NO FRAMES AT ALL.")
        if closed_by_peer:
            print("  The gateway accepted the connection and closed it again.")
            print("  That is almost always its connection limit: something else")
            print("  is already connected. Stop the Home Assistant integration")
            print("  or the add-on and try again.")
        else:
            print("  The connection stayed open but nothing arrived. Check on the")
            print("  EW11: baud rate 115200, 8 data bits, no parity, 1 stop bit,")
            print("  and that the RS-485 A/B lines are not swapped.")
        return 1

    print("Message types:")
    for name, count in counts.most_common():
        print(f"  {count:6d}  {name}")
    print()

    print("Answers to the open design questions:")
    if macs:
        print(f"  1. MAC address available    : YES -> {', '.join(sorted(macs))}")
        print("     Entity identity can use the MAC.")
    else:
        answered = any("configuration_response" in k for k in counts)
        if answered:
            print("  1. MAC address available    : NO (answered, but no MAC)")
        elif args.probe or args.fault_log:
            print("  1. MAC address available    : NO (request unanswered)")
        else:
            print("  1. MAC address available    : UNKNOWN -- rerun with --probe")
        print("     The entry_id fallback becomes the normal path. This is expected")
        print("     for RS-485 setups and the design accounts for it.")

    if args.fault_log:
        if faults:
            print(f"  4. Fault log                : YES ({len(faults)} entries)")
            for line in faults:
                print(f"       {line}")
        else:
            print("  4. Fault log                : no response to the request")
        print()

    ready = sum(v for k, v in counts.items() if k.startswith("READY"))
    if ready:
        print(f"  2. RS-485 Ready tokens      : YES ({ready} seen)")
        print("     Token-bound writing is available; immediate stays the default.")
    else:
        print("  2. RS-485 Ready tokens      : none seen")
        print("     Immediate write policy is the only sensible default here.")

    if reader.crc_errors > total * 0.05:
        print(f"  3. CRC assumption           : DOUBTFUL ({reader.crc_errors} errors)")
        print("     Poly 0x07 / init 0x02 / xor 0x02 may not hold -- worth a look.")
    else:
        print("  3. CRC assumption           : holds")

    print()
    print(f"Files written:\n  {raw_path}\n  {jsonl_path}\n  {text_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
