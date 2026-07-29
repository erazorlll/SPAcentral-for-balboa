# 07 — Umsetzungsplan

## 1. Reihenfolge

Die Protokollbibliothek zuerst, und zwar gegen echte Aufzeichnungen. Alles danach baut
darauf auf. Wer mit dem Config Flow beginnt, testet gegen Vermutungen.

### Phase 0 — Aufzeichnungen (0,5 Tage)

**Vor jeder Zeile Code.** Rohdaten mitschneiden:

```bash
# WLAN-Modul
nc 10.0.0.5 4257 | xxd > fixtures/wifi_module.hex
# EW11
nc 10.0.0.9 8899 | xxd > fixtures/ew11.hex
```

Jeweils ~60 Sekunden im Ruhezustand, dann mit Bedienung am Spa-Panel (Pumpe an/aus,
Temperatur ändern). Diese Dateien sind die Grundlage aller Parsertests und **beantworten
nebenbei die offene Frage**, ob über den EW11 eine Configuration Response mit MAC eintrifft.

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

### Phase 5 — Discovery und Politur (1–2 Tage)

UDP-30303-Discovery, DHCP-Discovery, Rekonfiguration, Snapshot-Tests, README mit
Aufbauanleitungen je Hardware, Umstiegsanleitung von bwalink/MQTT.

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
| 5 Discovery & Politur | 2 PT |
| 6 Veröffentlichung | 1 PT |
| **Summe** | **≈ 14,5 PT** |

Erster produktiv nutzbarer Stand nach Phase 3, also **≈ 9,5 PT**.

## 3. Optionale Ausbaustufen

| Idee | Nutzen | Aufwand |
|---|---|---|
| `Rfc2217Transport` | Gateways mit korrekter rfc2217-Firmware | 1 PT |
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
