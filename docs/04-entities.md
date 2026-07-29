# 04 — Entity-Modell

Ziel: die Abdeckung von smartspaclient, aber mit den korrekten HA-Entity-Typen und
`has_entity_name`-Konvention.

## 1. Grundsätze

- `_attr_has_entity_name = True` — HA setzt den Gerätenamen davor. Die Entity heißt
  „Pumpe 1", angezeigt wird „Whirlpool Pumpe 1". Kein Namenspräfix im Code.
- Alles, was das Gerät nicht meldet, wird **nicht angelegt**. Die Control Configuration
  (`0A BF 24`) sagt, wie viele Pumpen mit wie vielen Stufen, wie viele Lichter, ob Blower,
  Mister, Umwälzpumpe und Aux vorhanden sind. Ein Spa mit zwei Pumpen bekommt keine
  Entity „Pumpe 3".
- Diagnose- und Konfigurationsentities bekommen die passende `EntityCategory`, damit die
  Hauptansicht des Geräts aufgeräumt bleibt.
- Übersetzungen über `translation_key` — keine hartkodierten deutschen oder englischen
  Anzeigenamen.

## 2. Entities

### Kern

| Plattform | Entity | Bedingung | Anmerkung |
|---|---|---|---|
| `climate` | Spa | immer | Solltemperatur, Ist-Temperatur, HVAC-Aktion (heizt/leerlauf), Presets für Temperaturbereich |
| `water_heater` | — | — | bewusst **nicht**: `climate` ist die passendere Karte und deckt beides ab |

> Entscheidung: **eine** Klimaentität statt der Homie-typischen Aufteilung in Einzelwerte.
> Das ist der sichtbarste UX-Gewinn gegenüber dem MQTT-Weg.

### Steuerung

| Plattform | Entity | Bedingung |
|---|---|---|
| `fan` | Pumpe 1..6 | pro konfigurierter Pumpe; mehrstufige Pumpen als Geschwindigkeitsstufen (`percentage_step`) |
| `switch` | Pumpe 1..6 | nur bei einstufigen Pumpen (Alternative zu `fan`, konfigurierbar) |
| `fan` | Gebläse | wenn vorhanden; 1-stufig → `switch`, mehrstufig → `fan` |
| `light` | Licht 1..2 | pro konfiguriertem Licht |
| `switch` | Mister | wenn vorhanden |
| `switch` | Aux 1..2 | pro konfiguriertem Aux |
| `select` | Heizmodus | `Ready` / `Rest` / `Ready in Rest` |
| `select` | Temperaturbereich | `Hoch` / `Niedrig` |
| `switch` | Temperatursperre / Bediensperre | wenn unterstützt |
| `button` | Filterzyklus starten | wenn unterstützt |

### Sensorik

| Plattform | Entity | Kategorie |
|---|---|---|
| `sensor` | Wassertemperatur | — |
| `sensor` | Solltemperatur | diagnostic |
| `binary_sensor` | Heizung aktiv | — |
| `binary_sensor` | Umwälzpumpe läuft | — |
| `binary_sensor` | Filterzyklus 1/2 läuft | — |
| `binary_sensor` | Priming | diagnostic |
| `binary_sensor` | Hold-Modus | — |
| `sensor` | Letzte Störung (Text + Code) | diagnostic |
| `event` | Störungsmeldung | diagnostic — HA-`event`-Entity, wie Core-Integration |
| `sensor` | Modell / Softwareversion | diagnostic |
| `sensor` | Verbindungsqualität (Frames/s, CRC-Fehler) | diagnostic |

### Konfiguration

| Plattform | Entity | Kategorie |
|---|---|---|
| `time` | Filterzyklus 1 Start | config |
| `number` | Filterzyklus 1 Dauer | config |
| `time` | Filterzyklus 2 Start | config |
| `number` | Filterzyklus 2 Dauer | config |
| `switch` | Filterzyklus 2 aktiv | config |
| `switch` | 24-Stunden-Anzeige | config |
| `select` | Temperatureinheit | config |

## 3. Verfügbarkeit

Eine Entity ist `available`, wenn die Verbindung steht **und** innerhalb der letzten
15 Sekunden ein Statusframe eintraf. Zusätzlich wird `assumed_state` gesetzt, solange ein
gesendeter Befehl noch nicht durch einen Statusframe bestätigt wurde — dann zeigt die
Oberfläche den Zustand als „vermutet" an, statt zu flackern.

## 4. Mehrstufige Pumpen

Der Knackpunkt der Balboa-Steuerung: Pumpen kennen keinen „Setze auf Stufe 2"-Befehl,
nur `Toggle Item`, das zyklisch weiterschaltet (`aus → 1 → 2 → aus`). Die Umsetzung:

```
Zielstufe bestimmen → Differenz zur Ist-Stufe → so oft togglen, mit ~300 ms Abstand
→ nach jedem Toggle den nächsten Statusframe abwarten → Abbruch bei Zielerreichung
```

Mit Timeout und Obergrenze für die Toggle-Anzahl, damit ein nicht reagierendes Gerät keine
Endlosschleife erzeugt. Während des Vorgangs ist `assumed_state` aktiv.

## 5. Was bewusst fehlt

| Nicht umgesetzt | Grund |
|---|---|
| GFCI-Test auslösen | löst am Gerät einen Schutzschaltertest aus — versehentlich per Dashboard auslösbar, potenziell störend. Wenn überhaupt, dann als `button` mit `EntityCategory.CONFIG` und Bestätigungsdialog in Phase 3 |
| Fehlerspeicher komplett auslesen | die `event`-Entity plus „Letzte Störung" deckt den Alltag ab; der vollständige Speicher gehört in die Diagnose-Datei, nicht in Entities |
| Vollständige Zeitsynchronisation als Entity | als Option (`sync_time`) umgesetzt, wie in der Core-Integration |
