<img src="images/logo.png" alt="SPAcentral for Balboa Whirlpool" width="320">

# SPAcentral for Balboa Whirlpool

> **This is an unofficial, community-built integration.** It is not affiliated with,
> endorsed by, sponsored by, or in any way officially connected to Balboa Water Group, or
> any of its subsidiaries or affiliates. "Balboa" and any related names, marks and logos
> are trademarks of Balboa Water Group and are used here only to describe hardware
> compatibility. The official website can be found at
> [balboawatergroup.com](https://www.balboawatergroup.com).

Native Home Assistant integration for Balboa Water Group spa controllers — supporting the
original Balboa Wi-Fi module **and** RS-485 gateways such as the Elfin EW11, ser2net or a
local serial adapter.

> **Status: running on real hardware.** Verified against 40,000+ frames captured from two
> real controllers and driving both of them from Home Assistant.

## Installation

### Through HACS

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=erazorlll&repository=SPAcentral-for-balboa&category=integration)

SPAcentral for Balboa Whirlpool is in the default HACS store — no custom repository needed.

1. HACS → **Integrations** → search for **SPAcentral for Balboa Whirlpool**
2. Download it
3. Restart Home Assistant

### By hand

Copy `custom_components/spacentral_for_balboa/` into your `<config>/custom_components/` and
restart Home Assistant.

## Setup

**Settings → Devices & Services → Add Integration → SPAcentral for Balboa Whirlpool**, then pick how the
spa is connected:

| Choice | For | Default port |
|---|---|---|
| **Serial gateway on the network** | Elfin EW11, ser2net, ESPHome serial server | 8899 |
| **Balboa Wi-Fi module** | the original bwa module (50350) | 4257 |
| **Serial adapter on this machine** | USB or GPIO RS-485 adapter | — |

Add the integration once per spa. There is no limit, and the two do not interfere: entity
identity never comes from the model or the MAC, so two identical controllers stay apart.

A gateway has to run in **TCP server mode at 115200 baud, 8 data bits, no parity, 1 stop
bit**. If the setup dialog says it connected but the spa sends nothing, that is almost
always the baud rate or swapped RS-485 A/B wires.

## What you get

Only for hardware the controller actually reports — a spa with three pumps gets three.

| Entity | Notes |
|---|---|
| `climate` | water and target temperature, heating action, heat mode, temperature range |
| `fan` | pumps 1–6 and the blower, single- and two-speed |
| `light` | lights 1–2 |
| `switch` | auxiliary outputs, mister, second filter cycle |
| `time` / `number` | filter cycle start times and durations |
| `sensor` | water and target temperature, heat mode, temperature range, reminder, last fault |
| `binary_sensor` | heating, circulation pump, filter cycles, priming, hold |
| `event` | maintenance reminders |

Options: keep the spa clock in sync with Home Assistant. Diagnostics can be downloaded
from the device page, with the address and MAC redacted.

## Why

Existing solutions each cover part of the problem:

| | Wi-Fi module | RS-485 / EW11 | No MQTT broker | Multiple spas | Identity without MAC |
|---|:--:|:--:|:--:|:--:|:--:|
| [ccutrer/balboa_worldwide_app](https://github.com/ccutrer/balboa_worldwide_app) + [jshank/bwalink](https://github.com/jshank/bwalink) | ✅ | ✅ | ❌ | ⚠️ | ⚠️ |
| [HA core `balboa`](https://www.home-assistant.io/integrations/balboa) + [pybalboa](https://github.com/garbled1/pybalboa) | ✅ | ❌ | ✅ | ✅ | ❌ |
| [jozefnad/homeassistant-smartspaclient](https://github.com/jozefnad/homeassistant-smartspaclient) | ✅ | ❌ | ✅ | ✅ | ❌ |
| **SPAcentral for Balboa Whirlpool** | ✅ | ✅ | ✅ | ✅ | ✅ |

The last column is the one that matters for anyone running two spas over an RS-485 gateway:
every existing integration derives Home Assistant entity identity from a MAC address that
such a setup may never report, or from a name the user is free to change.

## Design in five decisions

1. **One transport, two worlds.** The Balboa Wi-Fi module (TCP 4257) and a serial gateway
   like the EW11 (TCP 8899) speak the same protocol over the same kind of socket. They
   differ only in port number.
2. **Identity does not come from the device.** MAC address when available, Home Assistant's
   own `entry_id` otherwise. Never the display name. Renaming is always safe. This is what
   makes two spas over an RS-485 gateway work at all.
3. **The protocol layer does not know Home Assistant.** `balboa/` imports nothing from
   `homeassistant.*` and is tested against recorded byte streams.
4. **Bus arbitration is a policy, not a requirement.** Immediate writes for TCP gateways,
   token-bound writes for direct RS-485 — switchable, with a safety net.
5. **Push, not polling.** The controller sends a status frame every second. No
   `DataUpdateCoordinator`, no poll interval option.

## Hardware support

| Connection | Status |
|---|---|
| RS-485 gateway over TCP (Elfin EW11, ser2net, ESPHome serial server) | **verified on hardware, reading and writing** — this is the setup the project is developed against |
| Local serial adapter (USB / GPIO RS-485) | supported by design, not verified on hardware |
| Balboa Wi-Fi module (bwa 50350, TCP 4257) | supported by design, not verified on hardware |

The Wi-Fi module uses the *same* transport, framing and parser as the RS-485 gateway —
only the default port and write policy differ — so it is exercised by the same tests.
It is nevertheless listed as unverified because nobody has run it on real hardware.
**Reports from Wi-Fi module owners are very welcome.**

Automatic discovery (UDP broadcast + DHCP) only works with the Balboa Wi-Fi module and is
deliberately deferred until someone with that hardware can test it.

## Planned features

- Setup entirely through the UI, with connection presets in plain language
- Any number of spas side by side
- `climate`, `fan` (pumps and blower), `light`, `switch`, `sensor`, `binary_sensor`,
  `time` and `number` for the filter cycles, `event` for reminders
- Diagnostics download with the address redacted
- Only creates entities the spa actually reports
- Diagnostics download, English and German translations
- Reconnect with exponential backoff and stale-stream detection

## Credits

Built on protocol work and design ideas from
[ccutrer/balboa_worldwide_app](https://github.com/ccutrer/balboa_worldwide_app) (MIT) and
[garbled1/pybalboa](https://github.com/garbled1/pybalboa) (Apache-2.0).
[jozefnad/homeassistant-smartspaclient](https://github.com/jozefnad/homeassistant-smartspaclient)
informed the entity coverage and setup dialog — no code was taken from it, as it carries
no licence.

## Trademark notice

"Balboa," "Balboa Water Group," "bwa," and any associated logos are trademarks or
registered trademarks of Balboa Water Group. This project is an independent,
community-written implementation of a publicly reverse-engineered communication protocol.
It is not produced, reviewed, or supported by Balboa Water Group, and no license or other
affiliation is implied. All trademarks belong to their respective owners.

## Licence

MIT — applies to the code in this repository. It does not grant any rights to the Balboa
trademarks referenced above.

## Development

```bash
pip install pytest pytest-asyncio pytest-cov ruff mypy
pytest                      # everything
ruff check . && mypy        # lint and types
python tools/replay.py fixtures/ew11_idle.bin --port 8899   # a spa without a spa
```

The Home Assistant test harness imports `fcntl` and therefore only runs on Linux and
macOS, the same platforms HA core itself is developed on. On Windows the protocol suite
still runs in full with `pytest -p no:homeassistant`; the integration tests are covered
by CI.
