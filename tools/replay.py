#!/usr/bin/env python3
"""Replay a recorded capture over TCP, so the library can be driven end to end.

Acts like an EW11 with a spa behind it: serves the recorded byte stream, and
answers configuration requests from the recording. Useful for exercising the
whole stack -- transport, client, entities -- with no hardware attached.

    python tools/replay.py fixtures/ew11_idle.bin --port 8899
    python -m balboa 127.0.0.1 --port 8899        # in another shell
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "custom_components" / "balboa_spacentral"))

from balboa.framing import FrameReader  # noqa: E402
from balboa.messages import (  # noqa: E402
    ControlConfiguration,
    ControlConfiguration2,
    FilterCycles,
    parse_frame,
)

#: Real controllers emit a status roughly every 300 ms.
DEFAULT_RATE = 0.3


def _load(paths: list[Path]) -> tuple[list[bytes], dict[bytes, bytes]]:
    """Split a capture into a stream to replay and the answers to requests."""
    stream: list[bytes] = []
    answers: dict[bytes, bytes] = {}

    for path in paths:
        for frame in FrameReader().feed(path.read_bytes()):
            message = parse_frame(frame)
            if isinstance(message, ControlConfiguration):
                answers[b"\x02\x00\x00"] = frame
            elif isinstance(message, ControlConfiguration2):
                answers[b"\x00\x00\x01"] = frame
            elif isinstance(message, FilterCycles):
                answers[b"\x01\x00\x00"] = frame
            else:
                stream.append(frame)
    return stream, answers


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("captures", nargs="+", type=Path)
    parser.add_argument("--port", type=int, default=8899)
    parser.add_argument("--rate", type=float, default=DEFAULT_RATE)
    args = parser.parse_args()

    stream, answers = _load(args.captures)
    if not stream:
        print("no frames in the given captures")
        return 1
    print(f"replaying {len(stream)} frames, {len(answers)} canned answers")

    async def serve(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        peer = writer.get_extra_info("peername")
        print(f"client connected: {peer}")

        async def answer_requests() -> None:
            frame_reader = FrameReader()
            while data := await reader.read(4096):
                for frame in frame_reader.feed(data):
                    payload = frame[5:-2]
                    if frame[3:5] == b"\xbf\x22" and payload in answers:
                        writer.write(answers[payload])
                        await writer.drain()

        task = asyncio.create_task(answer_requests())
        try:
            for frame in stream:
                writer.write(frame)
                await writer.drain()
                if frame[3:5] == b"\xaf\x13":
                    await asyncio.sleep(args.rate)
        except (ConnectionError, asyncio.CancelledError):
            pass
        finally:
            task.cancel()
            writer.close()
            print(f"client gone: {peer}")

    server = await asyncio.start_server(serve, "127.0.0.1", args.port)
    print(f"listening on 127.0.0.1:{args.port}, Ctrl+C to stop")
    async with server:
        await server.serve_forever()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        sys.exit(0)
