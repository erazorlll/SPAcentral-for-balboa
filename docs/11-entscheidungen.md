# 11 — Getroffene Entscheidungen (ADR)

Alle bis dahin offenen Punkte, entschieden unter der Vorgabe: **Veröffentlichung über HACS,
nutzbar für alle** — nicht nur für den eigenen EW11-Aufbau.

| # | Frage | Entscheidung | Begründung |
|---|---|---|---|
| E1 | Produktname / Domain | technische Domain bleibt `balboa_spacentral`; Anzeigename „SPAcentral for Balboa Whirlpool" | Domain kollidiert nicht mit der Core-Integration `balboa`; Anzeigename stellt klar, dass es keine offizielle Balboa-Integration ist |
| E2 | Eigene Protokollbibliothek oder `pybalboa`? | **eigene** | Phase 0 hat gemessen, dass `pybalboa` an der Modul-Identifikation scheitert. Kein Weg daran vorbei |
| E3 | Discovery in v1? | **ja, doch aufnehmen** | Bei öffentlicher Veröffentlichung sind WLAN-Modul-Nutzer eine relevante Gruppe. Beide Verfahren sind rein additiv: DHCP greift nur bei OUI `001527*`, der UDP-Broadcast nur während der Einrichtung. Schlimmstenfalls findet er nichts. Wird als „nicht auf Hardware verifiziert" gekennzeichnet |
| E4 | Mehrstufige Pumpen | **voll implementieren** | Die eigene Anlage hat nur einstufige, andere Nutzer nicht. Für eine öffentliche Integration nicht verhandelbar |
| E5 | Alle Ausstattungsmerkmale | **voll implementieren** | Mister, Aux 1–2, Licht 2, Pumpen 4–6, mehrstufiges Gebläse — auch wenn die eigene Anlage sie nicht hat |
| E6 | Temperaturskala | beide, aus dem Status gelesen | Celsius wird halbiert übertragen, Fahrenheit ganzzahlig |
| E7 | Sendeverfahren | `IMMEDIATE`, einziger Modus | Phase 0: `Ready` gehört Kanal `0x10`. Kanalanmeldung als spätere Ausbaustufe |
| E8 | Transporte in v1 | TCP **und** seriell | Seriell ist für Nutzer mit USB-RS-485-Adapter unverzichtbar; `rfc2217` später |
| E9 | Identität | MAC wenn vorhanden, sonst `entry_id` | in Phase 0 als notwendig belegt |
| E10 | Bibliothek als eigenes PyPI-Paket? | **nein, mitgeliefert** | HACS-Integrationen dürfen reinen Python-Code bündeln. Kein Versionspinning, keine zweite Veröffentlichung. Die Schichtung bleibt so streng, dass eine spätere Auslagerung möglich bleibt |
| E11 | Mindest-Python | 3.13 | entspricht der aktuellen HA-Basis |
| E12 | Lizenz | MIT | |

## Konsequenz für die eigene Hardware

Merkmale, die die eigene Anlage (BP6013G3) **nicht** hat, werden trotzdem gebaut und
getestet — gegen synthetische Frames, die aus der Protokollstruktur abgeleitet und mit
den echten Frames auf Formatgleichheit geprüft werden. Sie tragen im Code den Hinweis
`# not covered by own hardware`.

## Ein Fund aus den Aufzeichnungen, der Code-Wirkung hat

Eine **einstufige** Pumpe meldet im Statusframe den Wert `2`, nicht `1`:

```
Control Configuration 2 : pumps = [1, 1, 1, 0, 0, 0]   # 1 = einstufig
Status nach Einschalten : pumps = [2, 0, 0, 0, 0, 0]   # 2 = an
```

Die Zahl im Status ist also **keine** Stufennummer, die man direkt mit der Stufenzahl aus
der Konfiguration vergleichen dürfte. Richtig ist:

- einstufige Pumpe: `an = wert != 0`
- zweistufige Pumpe: `wert` ist die Stufe (0/1/2)

Das Ruby-Gem behandelt es ebenso (`speeds == 1 ? value != 0 : value`). Ohne die
Aufzeichnung wäre hier ein Fehler entstanden, der genau bei einstufigen Pumpen — also den
häufigsten — zugeschlagen hätte.
