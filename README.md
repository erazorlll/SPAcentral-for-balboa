# Balboa SPAcentral

Native Home Assistant integration for Balboa Water Group spa controllers — supporting the
original Balboa Wi-Fi module **and** RS-485 gateways such as the Elfin EW11, ser2net or a
local serial adapter.

> **Status: concept phase. No code yet.**
> The complete design lives in [`docs/`](docs/00-uebersicht.md) (German).

## Why

Existing solutions each cover part of the problem:

| | Wi-Fi module | RS-485 / EW11 | No MQTT broker | Multiple spas | Identity without MAC |
|---|:--:|:--:|:--:|:--:|:--:|
| [ccutrer/balboa_worldwide_app](https://github.com/ccutrer/balboa_worldwide_app) + [jshank/bwalink](https://github.com/jshank/bwalink) | ✅ | ✅ | ❌ | ⚠️ | ⚠️ |
| [HA core `balboa`](https://www.home-assistant.io/integrations/balboa) + [pybalboa](https://github.com/garbled1/pybalboa) | ✅ | ❌ | ✅ | ✅ | ❌ |
| [jozefnad/homeassistant-smartspaclient](https://github.com/jozefnad/homeassistant-smartspaclient) | ✅ | ❌ | ✅ | ✅ | ❌ |
| **Balboa SPAcentral** | ✅ | ✅ | ✅ | ✅ | ✅ |

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
| RS-485 gateway over TCP (Elfin EW11, ser2net, ESPHome serial server) | **verified on hardware** — this is the setup the project is developed against |
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
- `climate`, `fan`, `light`, `switch`, `select`, `number`, `time`, `sensor`,
  `binary_sensor`, `event`, `button`
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

## Licence

MIT
