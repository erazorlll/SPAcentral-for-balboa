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

## Status

**Konzeptphase. Noch kein Code.** Der erste Umsetzungsschritt ist bewusst kein Code,
sondern eine Aufzeichnung echter Byteströme von beiden Aufbauten — sie beantwortet die
einzige offene Entwurfsfrage und liefert zugleich sämtliche Testfixtures.
