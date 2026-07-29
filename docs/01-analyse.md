# 01 — Analyse des Bestands

## 1. Das Protokoll

Balboa-Steuerungen sprechen ein reverse-engineertes Binärprotokoll. Der Rahmen ist bei
**allen** Transportwegen identisch:

```
 0   1    2    3    4   ...  -2   -1
0x7e LEN  CH  0xBF  TYPE ...  CRC 0x7e
```

- `LEN` — Länge ab diesem Byte
- `CH` — Kanal/Adresse: `0xFF` = Broadcast der Steuerung, `0x0A` = erster Client-Kanal
- `CRC` — CRC-8, Initialwert `0x02`, finales XOR `0x02`
- RS-485-Parameter: 115200, 8N1

Nachweis: `doc/protocol.md` im Gem, gegengeprüft gegen die Implementierungen in
`pybalboa/client.py` (`send_message`) und `smartspaclient/spaclient.py` (`send_message`).
**Beide bauen byteweise denselben Frame und verwenden `0x0A` als Quelladresse.**

### Relevante Nachrichtentypen

| Typ | Richtung | Bedeutung |
|---|---|---|
| `FF AF 13` | ← Spa | Statusupdate, ca. 1×/Sekunde |
| `0A BF 94` | ← Spa | Configuration Response — **enthält die MAC-Adresse** (Bytes 3–8) |
| `0A BF 24` | ← Spa | Control Configuration (Pumpen, Lichter, Aux, Blower …) |
| `0A BF 23` | ← Spa | Control Configuration 2 |
| `0A BF 11` | → Spa | Toggle Item (Pumpe, Licht, Aux …) |
| `0A BF 20` | → Spa | Solltemperatur |
| `0A BF 21` | → Spa | Uhrzeit setzen |
| `10 BF 06` | ← Spa | **Ready — nur auf RS-485.** Signalisiert Sendeerlaubnis |
| `BF 07` | ← Spa | Nothing To Send |
| `BF 00` | ← Spa | New Client Clear To Send |

Die letzten drei Typen sind die **Bus-Arbitrierung**: RS-485 ist ein geteilter Bus, auf dem
ohne Token gesendete Frames kollidieren können. Über das WLAN-Modul entfällt das, weil das
Modul die Arbitrierung selbst übernimmt.

## 2. Die drei existierenden Implementierungen

| | **ccutrer/balboa_worldwide_app** | **pybalboa** (HA-Core) | **jozefnad/smartspaclient** |
|---|---|---|---|
| Sprache | Ruby | Python, async, typisiert | Python |
| Transporte | TCP, rfc2217, ESPHome, serieller Port | **nur TCP** (`asyncio.open_connection`) | **nur TCP, Port 4257 fest** |
| Port konfigurierbar | ja (URI) | ja (`port=4257` Default) | **nein** |
| RS-485-Arbitrierung | **ja** — Queue, sendet erst bei `Ready` | nein | nein |
| MAC-Adresse | empfängt `bf 94`, wertet sie nicht aus | ja, plus injizierbar | ja, **zwingend erforderlich** |
| Weg nach HA | MQTT/Homie + Discovery | native Integration | native Integration |
| Mehrfachinstanz | über Add-on-Kopien | nativ (Config Entries) | nativ (Config Entries) |
| Identität der Entities | aus dem **frei gewählten** Homie-`device_id` | `f"{model}-{key}-{mac[-6:]}"` | `f"{mac}#{key}"` |
| Reifegrad | seit Jahren produktiv | HA-Core-Abhängigkeit | Jan 2026, 4 Sterne, keine Lizenzdatei |

### Was jede Lösung richtig macht

- **Gem:** die einzige mit echter Transportvielfalt *und* Bus-Arbitrierung. Der URI-Ansatz
  (`tcp://`, `rfc2217://`, `esphome://`, Gerätepfad) ist ein sauberes Abstraktionsmodell.
- **pybalboa / HA-Core-Integration:** der moderne HA-Baukasten — `ConfigEntry[SpaClient]`
  als typisierte `runtime_data`, `_attr_has_entity_name`, `should_poll = False` mit
  ereignisgetriebenem `async_write_ha_state`, Reconnect-Monitor mit exponentiellem Backoff
  (gedeckelt auf 60 s), DHCP-Discovery über die OUI `001527*`.
- **smartspaclient:** die reichhaltigste Entity-Abdeckung (Climate, Fehlerspeicher,
  GFCI-Test, Filterzyklus-Konfiguration, Panel-/Settings-Lock) und ein Config-Flow, der den
  Namen beim Hinzufügen abfragt.

### Was jede Lösung falsch macht

- **Gem:** kein natives HA-Modell — der Umweg über MQTT/Homie erzwingt einen Broker und
  macht die frei gewählte Geräte-ID zur `unique_id`. Umbenennen verwaist alle Entities.
- **pybalboa:** `_check_configuration_loaded()` verlangt zwingend
  `_module_identification_loaded`. Bleibt die Antwort aus, wird `configuration_loaded`
  nie gesetzt, `async_configuration_loaded()` läuft in den Timeout und die HA-Integration
  scheitert mit `ConfigEntryNotReady`. Für Aufbauten ohne Balboa-WLAN-Modul ein K.-o.
- **smartspaclient:** Port hart auf 4257 verdrahtet, und die `unique_id` hängt an einer MAC,
  die ohne WLAN-Modul `"Unknown"` bleibt — bei zwei Spas kollidieren dann alle Entities.

## 3. Der zentrale Zielkonflikt

Alle drei binden die Geräteidentität an etwas, das in mindestens einem Aufbau nicht
verfügbar ist:

| Aufbau | MAC verfügbar? | Folge |
|---|---|---|
| Balboa-WLAN-Modul (50350) | ja, per UDP-Discovery *und* `bf 94` | alle drei funktionieren |
| EW11/ser2net am RS-485-Bus | **ungeklärt** | pybalboa & smartspaclient riskieren Ausfall |
| Serieller Adapter direkt am Bus | **ungeklärt** | dito |

Ob `0A BF 94` auch ohne WLAN-Modul beantwortet wird, ließ sich aus den Quellen **nicht**
abschließend klären. Das Gem fordert die Nachricht zwar an, verwendet sie aber nicht für
seine `full_configuration?`-Prüfung — sein Erfolg über EW11 beweist also nicht, dass die
Antwort kommt.

→ **Konsequenz für den Entwurf:** Die Identität darf nicht von der MAC abhängen.
Sie wird verwendet, wenn sie da ist, und ist sonst entbehrlich. Details in
[03-geraeteidentitaet.md](03-geraeteidentitaet.md).

## 4. Ist Bus-Arbitrierung zwingend?

Empirisch nein — jedenfalls nicht über einen EW11. In
[ccutrer/balboa_worldwide_app#73](https://github.com/ccutrer/balboa_worldwide_app/issues/73)
berichtet ein Nutzer mit `tcp://10.10.10.214:9999/` von „full reporting and control", also
auch funktionierenden **Schreibbefehlen**. Der TCP-Zweig des Gems legt keine Warteschlange
an und sendet sofort — dieser Aufbau läuft also ohne Arbitrierung.

Plausible Erklärung: Der EW11 puffert, der Bus ist zwischen den Statusframes überwiegend
frei, und der Adapter übernimmt die Richtungsumschaltung des RS-485-Treibers.

→ **Konsequenz:** Arbitrierung wird als *umschaltbare Richtlinie* modelliert, nicht als
Pflicht. Für den direkt angeschlossenen seriellen Adapter bleibt sie sinnvoll, für
TCP-Gateways ist „sofort senden" der belegte Normalfall.

## 5. Discovery

Zwei unabhängige Wege, beide nur für das **Balboa-WLAN-Modul**:

1. **UDP-Broadcast** auf Port 30303 mit dem Text `Discovery: Who is out there?`.
   Antwort (unicast, CRLF-getrennt): Hostname `BWGSPA` + MAC. Gefiltert wird auf die
   Balboa-OUI `00-15-27-`. Liefert die MAC **vor** dem Verbindungsaufbau.
2. **DHCP** — HA kann über `"macaddress": "001527*"` im Manifest auf neue Leases reagieren.
   Die Core-Integration nutzt genau das.

Für EW11/ser2net gibt es prinzipiell keine Discovery: Der Adapter trägt die MAC seines
eigenen Herstellers und ist eine generische Brücke ohne Balboa-Kennung. Diese Aufbauten
müssen manuell angelegt werden — das ist keine Lücke im Entwurf, sondern eine
Eigenschaft der Hardware.

## 6. Home Assistant: Stand der Technik 2026

Aus der Integration Quality Scale und der Core-Referenzimplementierung:

| Stufe | Anforderung | Relevanz hier |
|---|---|---|
| Bronze | Einrichtung per UI, Tests, Doku | Pflicht |
| Silver | stabiler Betrieb, Fehlererholung, Reauth | Reconnect ja, Reauth entfällt (keine Authentifizierung) |
| Gold | Discovery, Rekonfiguration, Übersetzungen, Diagnose, volle Testabdeckung | alles anwendbar |
| Platinum | vollständig typisiert, vollständig asynchron | anwendbar |

Konkrete Muster, die aus der Core-Integration übernommen werden:
`type BalboaConfigEntry = ConfigEntry[SpaClient]` (typisierte `runtime_data`),
`_attr_has_entity_name = True`, `_attr_should_poll = False` mit Push über einen
Event-Callback, `DeviceInfo` mit `connections={(CONNECTION_NETWORK_MAC, mac)}`,
`entry.async_on_unload(...)` für Aufräumarbeiten, `ConfigEntryNotReady` beim Fehlschlag.
