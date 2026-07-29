# 06 — Qualitätssicherung

## 1. Zielniveau

Angestrebt wird das Äquivalent von **Platinum** der HA Integration Quality Scale — auch
wenn die Skala formal nur für Core-Integrationen gilt, ist sie die beste verfügbare
Messlatte.

| Stufe | Anforderung | Umsetzung hier |
|---|---|---|
| Bronze | Einrichtung per UI | Config Flow mit drei Anschlussarten |
| Bronze | Automatisierte Tests | pytest + `pytest-homeassistant-custom-component` |
| Bronze | Grunddokumentation | README + `docs/` |
| Silver | Fehlererholung | Reconnect mit Backoff, Stale-Erkennung |
| Silver | Reauth | entfällt — das Protokoll kennt keine Authentifizierung |
| Silver | Aktiver Code-Owner | `codeowners` im Manifest |
| Gold | Discovery | ⏸ zurückgestellt — nur mit WLAN-Modul möglich, nicht verifizierbar |
| Gold | Rekonfiguration | `async_step_reconfigure` |
| Gold | Übersetzungen | `strings.json` + `translations/{en,de}.json` |
| Gold | Diagnose | `diagnostics.py` mit Redaction |
| Gold | Volle Testabdeckung | Zielwert 90 % Zeilen |
| Platinum | Vollständig typisiert | `mypy --strict` auf `balboa/`, `py.typed` |
| Platinum | Vollständig asynchron | keine blockierenden Aufrufe, `pyserial-asyncio` |

## 2. Teststrategie

Die Zweiteilung der Architektur zahlt sich hier aus: Die Protokollbibliothek ist ohne
Home Assistant testbar, die HA-Schicht ohne echte Hardware.

### Ebene 1 — Protokoll (reines pytest, keine HA-Abhängigkeit)

| Testart | Inhalt |
|---|---|
| Framing | CRC-8 gegen bekannte Frames, Erkennung an Bytegrenzen, **zerstückelte Frames** (Frame über zwei `read()`-Aufrufe verteilt), Müll zwischen Frames |
| Parser | jeder Nachrichtentyp gegen aufgezeichnete Rohdaten; unbekannte Typen werden verworfen, nicht geworfen |
| Serialisierung | jeder Sendebefehl byteweise gegen Referenz aus `doc/protocol.md` |
| Arbitrierung | `IMMEDIATE` schreibt sofort; `TOKEN` schreibt erst nach `Ready`; Timeout ohne `Ready` löst Warnung aus |
| Zustandsmaschine | Reconnect-Backoff-Folge, Stale-Erkennung, Handshake ohne Modul-Identifikation |

**Fixtures aus echten Aufzeichnungen.** Vor der Umsetzung werden Rohdaten über den EW11
mitgeschnitten — im Ruhezustand und während der Bedienung am Spa-Panel. Diese Byteströme
sind die Grundlage aller Parsertests; synthetische Testdaten würden genau die Abweichungen
verdecken, um die es geht.

Für das Balboa-WLAN-Modul stehen keine eigenen Aufzeichnungen zur Verfügung. Die
Parsertests dafür stützen sich auf die Referenzframes aus `doc/protocol.md` des Gems.
Das genügt für die Protokollebene, ersetzt aber keinen Hardwaretest — siehe
[08-validierung.md](08-validierung.md) §7.

### Ebene 2 — Integration (`pytest-homeassistant-custom-component`)

| Testart | Inhalt |
|---|---|
| Config Flow | alle drei Anschlussarten, Erfolg und jeder Fehlerpfad, Discovery-Bestätigung, Duplikaterkennung, Rekonfiguration |
| Identität | die sieben Fälle aus [03-geraeteidentitaet.md](03-geraeteidentitaet.md) §6 — insbesondere **zwei Spas ohne MAC** |
| Setup/Unload | sauberes Auf- und Abbauen, keine hängenden Tasks |
| Entities | korrekte Anzahl je nach Control Configuration; ein Spa mit zwei Pumpen erzeugt keine dritte |
| Verfügbarkeit | Verbindungsverlust setzt Entities auf `unavailable` und zurück |
| Snapshot-Tests | `syrupy` über alle erzeugten Entities — fängt unbeabsichtigte Änderungen an `unique_id`, Namen und Attributen |

### Ebene 3 — Hardware (manuell, dokumentiert)

Eine Testmatrix, die vor jedem Release durchlaufen wird:

| Aufbau | Lesen | Schreiben | Reconnect | Prüfbar |
|---|---|---|---|---|
| EW11, TCP-Server 8899 | ☐ | ☐ | ☐ | ✅ eigene Hardware |
| EW11 mit `TOKEN`-Arbitrierung | ☐ | ☐ | ☐ | ✅ eigene Hardware |
| Zwei Instanzen gleichzeitig | ☐ | ☐ | ☐ | ✅ zwei Becken vorhanden |
| EW11 stromlos → Reconnect | ☐ | ☐ | ☐ | ✅ eigene Hardware |
| Balboa WLAN-Modul, TCP 4257 | — | — | — | ❌ **keine Hardware** |
| USB-RS-485-Adapter lokal | — | — | — | ❌ keine Hardware |

Die beiden unteren Zeilen bleiben dauerhaft offen. Sie werden im Release nicht als
„getestet" ausgewiesen, sondern als **unterstützt laut Entwurf, nicht auf Hardware
verifiziert** — mit der Bitte um Rückmeldung im README. Alles andere wäre ein
Qualitätsversprechen, das niemand eingelöst hat.

## 3. Continuous Integration

| Workflow | Inhalt |
|---|---|
| `hassfest` | offizielle HA-Manifestprüfung |
| `HACS validate` | Struktur- und Metadatenprüfung für HACS |
| `tests` | pytest + Coverage-Gate, Matrix über die unterstützten Python-Versionen |
| `lint` | `ruff` (Format + Lint), `mypy --strict` auf `balboa/` |

Alle vier laufen bei jedem Push und PR. Ein fehlgeschlagener Lauf blockiert den Merge.

## 4. Versionierung und Releases

- Semantische Versionierung, Version im `manifest.json` als einzige Quelle.
- Release über GitHub-Tag; HACS zieht Releases automatisch.
- Changelog aus Conventional Commits generiert.
- Ein `breaking`-Marker ist Pflicht, sobald sich ein `unique_id`-Schema ändert — solche
  Änderungen sind grundsätzlich zu vermeiden.

## 5. Lizenz

**MIT.** Bewusst gewählt, weil das Projekt Erkenntnisse aus MIT-lizenzierten Vorbildern
(`balboa_worldwide_app`, `pybalboa`) aufgreift und selbst nachnutzbar sein soll.
Der fehlenden Lizenz bei `smartspaclient` wird damit ausdrücklich nicht gefolgt —
aus diesem Projekt wird **kein Code** übernommen, nur konzeptionelle Anregungen
(Entity-Abdeckung, Namensabfrage im Dialog), und das wird im README offengelegt.
