# 09 — Phase 0: Aufzeichnung

Ziel: die drei offenen Entwurfsfragen beantworten und alle Testfixtures gewinnen —
**bevor** eine Zeile Integrationscode entsteht.

| # | Frage | Wirkung auf den Entwurf |
|---|---|---|
| 1 | Liefert der Aufbau eine MAC-Adresse? | entscheidet, ob die Identität die MAC nutzt oder auf `entry_id` zurückfällt |
| 2 | Erscheinen RS-485-`Ready`-Token? | entscheidet über die Voreinstellung des Sendeverfahrens |
| 3 | Stimmen die angenommenen CRC-Parameter? | Grundlage des gesamten Parsers |

Zusätzlich liefern die Mitschnitte die Rohdaten für die Toggle-Logik mehrstufiger Pumpen
(Risiko R3) und für sämtliche Parsertests.

## Vorbereitung

**Das bwalink-Add-on vorher stoppen.** Zwei Gründe: Der EW11 erlaubt je nach Firmware nur
eine begrenzte Zahl gleichzeitiger TCP-Verbindungen, und das laufende Add-on sendet selbst
auf den Bus — der Mitschnitt wäre dann nicht die Grundlast, sondern eine Mischung.

Gebraucht wird nur Python (bereits vorhanden) und die IP des EW11.

## Die drei Läufe

### Lauf 1 — Grundlast (2 Minuten)

```bash
python tools/capture.py <EW11-IP> --seconds 120 --prefix ew11_idle
```

Nichts tun, nur laufen lassen. Zeigt, was der Bus von sich aus trägt: Statusframes,
gegebenenfalls `Ready`-Token, und ob überhaupt sauber dekodiert werden kann.

### Lauf 2 — Konfigurationsabfrage (1 Minute) ← **der wichtigste**

```bash
python tools/capture.py <EW11-IP> --seconds 60 --prefix ew11_probe --probe
```

Sendet nach fünf Sekunden genau die vier Anfragen, die das Ruby-Gem beim Start stellt, und
prüft, ob Antworten kommen. **Nur so lässt sich Frage 1 beantworten** — eine
Configuration Response entsteht nur auf Anfrage, passives Lauschen zeigt sie nie.

### Lauf 3 — Bedienung am Panel (3 Minuten)

```bash
python tools/capture.py <EW11-IP> --seconds 180 --prefix ew11_panel
```

Nach dem Start am Spa-Panel folgende Aktionen ausführen, **jeweils etwa 15 Sekunden
Abstand**, und den Ablauf mitschreiben:

| ≈ Sekunde | Aktion |
|---|---|
| 15 | Pumpe 1 einschalten (Stufe 1) |
| 30 | Pumpe 1 auf Stufe 2 |
| 45 | Pumpe 1 aus |
| 60 | Licht ein |
| 75 | Licht aus |
| 90 | Solltemperatur um 1 °C erhöhen |
| 105 | Solltemperatur um 1 °C zurück |
| 120 | Heizmodus umschalten (Ready ↔ Rest) |
| 135 | Temperaturbereich umschalten (Hoch ↔ Niedrig) |
| 150 | nichts — Ruhephase zum Vergleich |

Die genauen Sekunden sind unkritisch, die **Reihenfolge** zählt: Sie erlaubt, die
beobachteten Frames den Aktionen zuzuordnen. Notiere Abweichungen (etwa wenn dein Spa
keinen zweistufigen Pumpenbetrieb hat).

Falls dein Aufbau zwei Anlagen hat: **Lauf 1 und 2 bitte an beiden** durchführen
(`--prefix ew11b_idle` usw.). Das prüft zugleich, ob sich die beiden Steuerungen
unterscheiden.

## Was das Werkzeug ausgibt

Je Lauf drei Dateien unter `fixtures/`:

| Datei | Zweck |
|---|---|
| `<prefix>.bin` | Rohstrom — die eigentliche Testfixture |
| `<prefix>.jsonl` | ein dekodierter Frame je Zeile mit Zeitstempel, maschinenlesbar |
| `<prefix>.txt` | dieselben Daten lesbar, zum Durchscrollen |

Am Ende steht eine Auswertung auf der Konsole, die die drei Fragen direkt beantwortet —
inklusive gefundener MAC-Adresse, Zahl der `Ready`-Token und CRC-Fehlerquote.

## Wenn nichts ankommt

Meldet das Werkzeug „NO FRAMES AT ALL", ist die TCP-Verbindung zustande gekommen, aber
der serielle Teil stimmt nicht. Zu prüfen am EW11:

- **Baudrate 115200, 8 Datenbits, keine Parität, 1 Stoppbit**
- Betriebsart **TCP-Server**
- RS-485-Leitungen A und B nicht vertauscht

Kommen Frames, aber die CRC-Fehlerquote ist hoch, stimmt die Baudrate meist nicht ganz
oder es liegt ein Terminierungsproblem am Bus vor.

## Mögliches Ergebnis, das kein Fehler ist

Zeigt Lauf 3 **nur Statusframes und keine Toggle-Befehle**, sieht der EW11-Abgriff nur die
Senderichtung der Steuerung, nicht die des Bedienpanels. Das ist keine Störung — es
bedeutet lediglich, dass die Fixtures für die Toggle-Logik aus den *Zustandsänderungen* in
den Statusframes abgeleitet werden statt aus den Befehlsframes. Für die Umsetzung reicht
das, es ist nur etwas weniger komfortabel.

## Danach

Die Konsolenauswertung und die drei `.txt`-Dateien genügen, um die Abbruchkriterien aus
[08-validierung.md](08-validierung.md) §6 zu prüfen. Erst danach beginnt Phase 1.
