# 07 — Umsetzungsplan

## 1. Reihenfolge

Die Protokollbibliothek zuerst, und zwar gegen echte Aufzeichnungen. Alles danach baut
darauf auf. Wer mit dem Config Flow beginnt, testet gegen Vermutungen.

### Phase 0 — Aufzeichnungen (0,5 Tage)

**Vor jeder Zeile Code.** Rohdaten mitschneiden:

```bash
nc 10.0.0.9 8899 | xxd > fixtures/ew11_idle.hex      # ~60 s Ruhezustand
nc 10.0.0.9 8899 | xxd > fixtures/ew11_control.hex   # mit Bedienung am Spa-Panel
```

Für die zweite Aufzeichnung am Panel: Pumpe 1 durchschalten (aus → Stufe 1 → Stufe 2 → aus),
Licht an/aus, Solltemperatur ändern, Heizmodus umschalten. Das liefert die Fixtures für die
Toggle-Logik mehrstufiger Pumpen (Risiko R3).

Diese Dateien sind die Grundlage aller Parsertests und **beantworten die offene Frage**,
ob über den EW11 eine Configuration Response (`0A BF 94`) mit MAC-Adresse eintrifft.

> **Nur der EW11-Pfad ist auf eigener Hardware prüfbar** — ein Balboa-WLAN-Modul steht nicht
> zur Verfügung. Die Folgen für Testmatrix und Umfang stehen in
> [08-validierung.md](08-validierung.md) §7.

**Ohne diesen Schritt bleibt eine zentrale Entwurfsannahme ungeprüft.**

### Phase 1 — Protokollbibliothek (3–4 Tage)

`balboa/` vollständig, ohne HA-Bezug: Framing, CRC, Parser, Serialisierung, Transporte
(TCP + Serial), Arbitrierung, Client-Zustandsmaschine, Discovery.
**Abnahme:** Ein CLI-Skript (`python -m balboa tcp://10.0.0.9:8899`) zeigt live den
Spa-Zustand und kann eine Pumpe schalten. Testabdeckung ≥ 90 %.

### Phase 2 — HA-Grundgerüst (2 Tage)

`manifest.json`, `__init__.py` mit typisiertem `runtime_data`, Config Flow für alle drei
Anschlussarten, Identitätslogik, `entity.py`, und als erste Plattform `sensor` +
`binary_sensor`.
**Abnahme:** Integration lässt sich per HACS installieren, zwei Instanzen parallel
einrichten, Temperatur wird angezeigt.

### Phase 3 — Steuerung (2–3 Tage)

`climate`, `fan` (Pumpen inkl. Mehrstufenlogik), `light`, `switch`, `select`.
**Abnahme:** Alle Bedienelemente des Spa-Panels sind aus HA bedienbar; die Testmatrix aus
[06-qualitaet-tests.md](06-qualitaet-tests.md) §2.3 läuft für WLAN-Modul und EW11 durch.

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
| 1 Protokollbibliothek | 4 PT |
| 2 HA-Grundgerüst | 2 PT |
| 3 Steuerung | 3 PT |
| 4 Feinschliff | 2 PT |
| 5 Politur | 1 PT |
| 6 Veröffentlichung | 1 PT |
| **Summe** | **≈ 13,5 PT** |

Erster produktiv nutzbarer Stand nach Phase 3, also **≈ 9,5 PT**.

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
