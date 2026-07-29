# 07 — Umsetzungsplan

## 1. Reihenfolge

Die Protokollbibliothek zuerst, und zwar gegen echte Aufzeichnungen. Alles danach baut
darauf auf. Wer mit dem Config Flow beginnt, testet gegen Vermutungen.

### Phase 0 — Aufzeichnungen ✅ **abgeschlossen**

Durchgeführt mit [`tools/capture.py`](../tools/capture.py), Anleitung in
[09-phase0-aufzeichnung.md](09-phase0-aufzeichnung.md), Ergebnis in
[10-phase0-ergebnis.md](10-phase0-ergebnis.md).

34 616 Frames in drei Läufen. Alle drei offenen Entwurfsfragen beantwortet, kein
Abbruchkriterium eingetreten, Fixtures und echte Referenzframes für die
Serialisierungstests liegen vor.

### Phase 1 — Protokollbibliothek ✅ **abgeschlossen**

`balboa/` vollständig, ohne einen einzigen `homeassistant`-Import: Framing, CRC, Parser,
Serialisierung, Transporte (TCP + Serial), Client-Zustandsmaschine, Discovery, CLI.

**Abnahme erfüllt:**

| Kriterium | Ergebnis |
|---|---|
| Testabdeckung ≥ 90 % | **91 %**, 126 Tests |
| `ruff check` + `ruff format` | sauber |
| `mypy --strict` | sauber |
| Alle Nachrichtentypen der Aufzeichnungen modelliert | ja, null unbekannte bei 34 616 Frames |
| CLI zeigt den Spa-Zustand live | ja, gegen abgespielte Echtdaten verifiziert |
| Zustandsänderungen werden gemeldet | ja, 17 Wechsel im Panel-Mitschnitt erkannt |
| **Lesen an echter Hardware** | ✅ EW11, 192.168.0.56 — Modell, Hardware, Temperaturen, Uhr |
| **Schreiben an echter Hardware** | ✅ `--toggle light1` schaltet, Zustand kommt zurück |

Verifiziert über [`tools/replay.py`](../tools/replay.py): Die Aufzeichnungen werden über
einen echten TCP-Socket abgespielt, das CLI verbindet sich, führt den Handshake durch,
dekodiert Modell (BP6013G3), Hardware und Temperaturen und reagiert auf jede
Zustandsänderung — ohne angeschlossene Hardware.

Discovery ist **doch enthalten**: Bei einer öffentlichen Veröffentlichung sind
WLAN-Modul-Nutzer eine relevante Gruppe, und beide Verfahren sind rein additiv
(siehe [11-entscheidungen.md](11-entscheidungen.md), E3).

### Phase 2 — HA-Grundgerüst (2 Tage)

`manifest.json`, `__init__.py` mit typisiertem `runtime_data`, Config Flow für alle drei
Anschlussarten, Identitätslogik, `entity.py`, und als erste Plattform `sensor` +
`binary_sensor`.
**Abnahme:** Integration lässt sich per HACS installieren, zwei Instanzen parallel
einrichten, Temperatur wird angezeigt.

### Phase 3 — Steuerung (2,5 Tage)

`climate`, `light`, `switch`/`fan` (Pumpen, Gebläse), `select`.
**Abnahme:** Alle Bedienelemente des Spa-Panels sind aus HA bedienbar; die Testmatrix aus
[06-qualitaet-tests.md](06-qualitaet-tests.md) §2.3 läuft für den EW11 durch.

Die Mehrstufen-Toggle-Logik ist hier **nicht** enthalten — Phase 0 hat gezeigt, dass alle
drei Pumpen dieser Anlage einstufig sind. Sie entsteht danach für fremde Installationen.

### Phase 4 — Feinschliff (2 Tage)

`time`, `number`, `event`, `button`, Filterzyklus-Konfiguration, Zeitsynchronisation,
Diagnose, Übersetzungen (en/de), Reparaturhinweise.

### Phase 5 — Politur (1 Tag)

Rekonfiguration, Snapshot-Tests, README mit Aufbauanleitungen je Hardware,
Umstiegsanleitung von bwalink/MQTT.

**Discovery ist hier bewusst nicht enthalten.** UDP-30303- und DHCP-Discovery funktionieren
ausschließlich mit dem Balboa-WLAN-Modul und wären auf der verfügbaren Hardware nicht
prüfbar. Nicht verifizierbarer Code, der ungefragt Einrichtungsvorschläge in fremden
Installationen erzeugt, ist ein schlechter Tausch für einen Punkt auf der Qualitätsskala.
→ verschoben in die Ausbaustufen, umzusetzen wenn ein Nutzer mit WLAN-Modul testen kann.

### Phase 6 — Veröffentlichung (1 Tag)

HACS-Metadaten, CI-Workflows, erstes Release, Einreichung als HACS-Default-Repository.

## 2. Aufwand

| Phase | Aufwand |
|---|---|
| 0 Aufzeichnungen | 0,5 PT |
| 1 Protokollbibliothek | 3,5 PT |
| 2 HA-Grundgerüst | 2 PT |
| 3 Steuerung | 2,5 PT |
| 4 Feinschliff | 2 PT |
| 5 Politur | 1 PT |
| 6 Veröffentlichung | 1 PT |
| **Summe** | **≈ 12 PT** (nach Phase 0 neu geschätzt) |

Erster produktiv nutzbarer Stand nach Phase 3, also **≈ 8,5 PT**.

## 3. Optionale Ausbaustufen

| Idee | Nutzen | Aufwand | Voraussetzung |
|---|---|---|---|
| **UDP-30303- und DHCP-Discovery** | Einrichtung ohne IP-Eingabe für WLAN-Modul-Nutzer | 1 PT | **Tester mit Balboa-WLAN-Modul** |
| `Rfc2217Transport` | Gateways mit korrekter rfc2217-Firmware | 1 PT | |
| ESPHome-Serial-Proxy als Transport | Anbindung über vorhandene ESPHome-Knoten | 1,5 PT |
| Transport-Abstraktion an `pybalboa` beitragen | die eigene Bibliothek würde langfristig entbehrlich | 2 PT + Wartezeit |
| Einreichung als HA-Core-Integration | Installation ohne HACS | hoch, erst nach Reifung |
| Energiemessung / Laufzeitstatistik | Heizstunden, Pumpenlaufzeit als `sensor` mit `state_class` | 1 PT |

## 4. Was dieses Projekt ablöst

Nach Phase 3 wird der bestehende Aufbau überflüssig:

| Bisher | Danach |
|---|---|
| `erazorlll/balboa_worldwide_app` (Fork) | entfällt |
| `erazorlll/bwalink` (Add-on-Fork) | entfällt |
| MQTT-Broker als Zwischenschicht | entfällt |
| Zwei Add-on-Verzeichnisse mit verschiedenen Slugs | entfällt — zwei Config Entries |
| Manuell eindeutig zu haltende `device_id` | entfällt — Identität ist automatisch |
| Tag-Pinning zwischen zwei Repos | entfällt — ein Repo |

Die beiden Forks bleiben bestehen, bis der Umstieg abgeschlossen ist, und werden danach
archiviert statt gelöscht — sie dokumentieren die Vorgeschichte.
