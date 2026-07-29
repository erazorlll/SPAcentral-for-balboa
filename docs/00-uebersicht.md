# 00 — Übersicht und Leitentscheidungen

## Vorhaben

Eine native Home-Assistant-Integration für Balboa-Whirlpools und -Pools, die **jeden
gängigen Anschlussweg** abdeckt und ohne Zwischenschichten auskommt.

Sie ersetzt einen gewachsenen Aufbau aus zwei Repository-Forks, einem Docker-Add-on und
einem MQTT-Broker durch **ein Repository, eine Installation über HACS, ein
Konfigurationsdialog**.

## Die fünf Leitentscheidungen

### 1. Ein Transport, zwei Welten
Das originale Balboa-WLAN-Modul und ein serieller Netzwerk-Gateway wie der Elfin EW11
unterscheiden sich **nur im Port** — 4257 gegen 8899. Beide sprechen dasselbe
Binärprotokoll über einen TCP-Socket. Ein einziger `TcpTransport` bedient damit beide,
ohne Sonderbehandlung. Der lokale serielle Adapter kommt als zweite Transportklasse hinzu.

### 2. Identität kommt nicht vom Gerät
Alle drei bestehenden Lösungen binden die Entity-Identität an etwas Unzuverlässiges: an
einen frei gewählten Namen oder an eine MAC-Adresse, die in RS-485-Aufbauten fehlen kann.
Hier gilt: **MAC, wenn verfügbar — sonst die von Home Assistant vergebene `entry_id`.**
Beides ist eindeutig und stabil, keines hängt am Anzeigenamen. Damit ist Umbenennen
folgenlos und zwei Instanzen können nicht kollidieren.

### 3. Die Protokollschicht kennt Home Assistant nicht
`balboa/` ist eine eigenständige, typisierte, asynchrone Bibliothek ohne einen einzigen
Import aus `homeassistant.*`. Sie ist gegen aufgezeichnete Byteströme testbar und könnte
unverändert auf PyPI veröffentlicht werden. Die HA-Schicht darüber enthält keine
Protokolllogik.

### 4. Arbitrierung ist eine Richtlinie, keine Pflicht
RS-485 ist ein geteilter Bus und kennt ein Sendetoken. Über TCP-Gateways ist es
nachweislich entbehrlich, bei direktem Anschluss sinnvoll. Deshalb: umschaltbar, vom
Transport vorbelegt, mit einem Sicherheitsnetz, das stille Funkstille verhindert.

### 5. Push, nicht Polling
Die Steuerung sendet sekündlich von selbst. Ein `DataUpdateCoordinator` wäre der falsche
Baustein und ein Abfrageintervall eine Scheinoption. Entities abonnieren ein Update-Event.

## Was daraus folgt

| Bisher nötig | Künftig |
|---|---|
| Fork des Ruby-Gems | entfällt |
| Fork des HA-Add-ons | entfällt |
| MQTT-Broker | entfällt |
| Zwei Add-on-Verzeichnisse mit verschiedenen Slugs | zwei Config Entries |
| Manuell eindeutig zu haltende Geräte-ID | automatisch eindeutig |
| Tag-Pinning zwischen zwei Repositories | ein Repository |
| YAML für den Namen | Dialogfeld bei der Einrichtung |

## Dokumente

| Dokument | Inhalt |
|---|---|
| [01-analyse.md](01-analyse.md) | Protokoll, Transporte, Vergleich der drei bestehenden Lösungen |
| [02-architektur.md](02-architektur.md) | Schichten, Transport-Abstraktion, Lebenszyklus, Fehlerbehandlung |
| [03-geraeteidentitaet.md](03-geraeteidentitaet.md) | Das Kernproblem und seine Lösung |
| [04-entities.md](04-entities.md) | Welche Entities entstehen, unter welcher Bedingung |
| [05-ux-configflow.md](05-ux-configflow.md) | Einrichtungsdialog, Discovery, Optionen, Diagnose |
| [06-qualitaet-tests.md](06-qualitaet-tests.md) | Qualitätsziel, Teststrategie, CI, Lizenz |
| [07-roadmap.md](07-roadmap.md) | Phasen, Aufwand, Ausbaustufen |
| [08-validierung.md](08-validierung.md) | Kritische Prüfung, Risiken, Abbruchkriterien |
| [09-phase0-aufzeichnung.md](09-phase0-aufzeichnung.md) | Was aufzuzeichnen war und wie |
| [10-phase0-ergebnis.md](10-phase0-ergebnis.md) | **Messergebnis** — alle offenen Fragen beantwortet, Freigabe für Phase 1 |

## Verfügbare Hardware

Zwei Balboa-Anlagen, beide über einen **Elfin EW11** angebunden. Kein Balboa-WLAN-Modul.

Das trifft sich günstig: Der EW11 ist genau der Aufbau, den keine bestehende
Python-Lösung bedient — dort liegt das Neuland, und dort wird auf echter Hardware getestet,
einschließlich zweier gleichzeitiger Instanzen. Der WLAN-Modul-Pfad nutzt denselben
Transport und denselben Parser und wird durch dieselben Tests abgedeckt, bleibt aber
mangels Hardware als **„unterstützt laut Entwurf, nicht verifiziert"** gekennzeichnet.
Discovery ist deshalb aus dem Erstumfang genommen. Begründung in
[08-validierung.md](08-validierung.md) §7.

## Status

**Phase 0 abgeschlossen, Phase 1 freigegeben.** 34 616 Frames aufgezeichnet, alle drei
offenen Entwurfsfragen beantwortet, kein Abbruchkriterium eingetreten.

Die drei Kernergebnisse:

- **Keine MAC-Adresse** — der `entry_id`-Rückfall ist der Normalfall, die zentrale
  Entwurfsentscheidung ist bestätigt. `pybalboa` wäre hier nachweislich gescheitert.
- **`Ready`-Token gehören dem Bedienpanel** (Kanal `0x10`), nicht uns — der geplante
  `TOKEN`-Modus entfällt, `IMMEDIATE` ist der einzige funktionierende Weg. Das
  vereinfacht die Architektur.
- **CRC-Annahme bestätigt** — null Fehler bei 34 616 Frames.

Aufwand dadurch von 13,5 auf **≈ 12 PT** gesunken. Einzelheiten in
[10-phase0-ergebnis.md](10-phase0-ergebnis.md).
