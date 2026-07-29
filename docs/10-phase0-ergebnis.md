# 10 — Phase 0: Ergebnis

Drei Mitschnitte über den EW11, zusammen **34 616 Frames** aus 360 Sekunden.
Alle drei offenen Entwurfsfragen sind beantwortet, dazu fünf Erkenntnisse, die nicht auf
dem Zettel standen.

## 1. Die drei Fragen

### Frage 1 — MAC-Adresse: **nein**

Die Konfigurationsanfrage `7e 05 0a bf 04 77 7e` blieb **unbeantwortet**. Es kam keine
einzige Configuration Response (`BF 94`) — in keinem der drei Läufe.

Beantwortet wurden dagegen alle drei `BF 22`-Anfragen, jeweils innerhalb derselben
Sekunde:

| Antwort | Inhalt |
|---|---|
| `BF 24` Control Configuration | Modell und Softwareversion |
| `BF 2E` Control Configuration 2 | Pumpen, Lichter, Blower, Umwälzpumpe |
| `BF 23` Filter Cycles | Filterzyklen |

**Folge:** Der `entry_id`-Rückfall aus [03-geraeteidentitaet.md](03-geraeteidentitaet.md)
ist für diesen Aufbau nicht die Ausnahme, sondern der Normalfall. Die zentrale
Entwurfsentscheidung ist damit bestätigt — und zugleich ist belegt, dass `pybalboa` und die
HA-Core-Integration hier **tatsächlich gescheitert wären**: Beide warten in
`_check_configuration_loaded()` auf `_module_identification_loaded`, das nie eintrifft.
Das war bis hierher eine begründete Vermutung, jetzt ist es gemessen.

### Frage 2 — RS-485-`Ready`-Token: **ja, aber nicht für uns**

`Ready`-Frames sind allgegenwärtig — 5 509 in 120 Sekunden, also rund 46 pro Sekunde.
Entscheidend ist das Adressbyte:

| Frame | Kanal | Bedeutung |
|---|---|---|
| `Ready` (`BF 06`) | **`0x10`** | Sendeerlaubnis für den Bedienpanel-Kanal |
| `Nothing to send` (`BF 07`) | **`0x10`** | Antwort des Panels |
| `Status Update` (`AF 13`) | `0xFF` | Broadcast |
| `New Client Clear To Send` (`BF 00`) | `0xFE` | Einladung an unregistrierte Clients |

Ein sauberer Beleg für das Arbitrierungsmodell steckt im Panel-Lauf: 8 247 `Ready` stehen
8 237 `Nothing to send` gegenüber — **eine Differenz von exakt 10**, und genau 10
Befehlsframes wurden gesendet. Das Panel antwortet auf jede Sendeerlaubnis entweder mit
„nichts zu senden" oder mit einem Befehl.

**Folge — und die wichtigste Entwurfsänderung:** Der `TOKEN`-Modus, wie ich ihn geplant
hatte, ist **unbrauchbar**. Er hätte auf ein `Ready` für den eigenen Kanal gewartet, das
nie kommt, weil `0x10` dem Bedienpanel gehört. Wer hier auf das Token wartet, sendet nie.
Details in Abschnitt 3.

### Frage 3 — CRC-Annahme: **hält**

| Lauf | Bytes | Frames | CRC-Fehler | Verworfen |
|---|---|---|---|---|
| idle | 91 648 | 11 541 | **0** | 4 |
| probe | 46 080 | 5 798 | **0** | 2 |
| panel | 137 216 | 17 277 | **0** | 6 |

Null CRC-Fehler bei 34 616 Frames. Polynom `0x07`, Initialwert `0x02`, finales XOR `0x02`
über den Bereich vom Längenbyte bis vor die Prüfsumme — bestätigt. Die zwölf verworfenen
Bytes sind jeweils das angeschnittene erste Frame beim Verbindungsaufbau, also erwartet.

## 2. Was sonst noch herauskam

### Kanal `0x0A` funktioniert ohne Anmeldung
Alle drei Antworten kamen adressiert an `0x0A` zurück — den Kanal, unter dem angefragt
wurde. Die Steuerung akzeptiert also Anfragen von einem Kanal, den sie gar nicht pollt,
und antwortet dorthin. Für **Befehle** (Toggle, Solltemperatur) ist das hier nicht direkt
gemessen worden; dass es funktioniert, belegt der tägliche Betrieb des bestehenden
bwalink-Aufbaus, der genau so sendet.

### Statusframes kommen alle 300 ms, nicht jede Sekunde
Mittlerer Abstand 299 ms über alle Läufe, größte Lücke 2,0 s (während der eigenen Sendungen
im Probe-Lauf), sonst maximal 726 ms. Die Protokolldokumentation spricht von „about once
per second" — der Bus ist dreimal schneller. Das erlaubt eine deutlich engere
Ausfallerkennung.

### Das Bedienpanel ist auf dem Bus sichtbar
Der Panel-Lauf zeigt echte Befehlsframes — die Sorge aus der Anleitung, der Abgriff könne
nur die Senderichtung der Steuerung sehen, hat sich nicht bestätigt:

```
t= 48.81  7e 07 10 bf 11 04 00 6a 7e   toggle pump1
t= 66.35  7e 07 10 bf 11 04 00 6a 7e   toggle pump1
t= 75.09  7e 07 10 bf 11 11 00 7c 7e   toggle light1
t= 87.90  7e 07 10 bf 11 11 00 7c 7e   toggle light1
t= 91.92  7e 06 10 bf 20 43 27 7e      set temperature 0x43 = 33,5 °C
t= 92.62  7e 06 10 bf 20 44 32 7e      set temperature 0x44 = 34,0 °C
t=109.48  7e 06 10 bf 20 43 27 7e      set temperature 0x43 = 33,5 °C
t=110.80  7e 06 10 bf 20 42 20 7e      set temperature 0x42 = 33,0 °C
t=137.76  7e 07 10 bf 11 50 00 32 7e   toggle temperature_range
t=151.24  7e 07 10 bf 11 50 00 32 7e   toggle temperature_range
```

Damit liegen echte Befehlsframes als Referenz für die Serialisierungstests vor.
Solltemperatur wird in halben Grad übertragen (`0x43` = 67 = 33,5 °C), passend zur
Celsius-Skala.

### Die Anlage ist vollständig identifiziert

| Merkmal | Wert |
|---|---|
| Modell | **BP6013G3** |
| Softwarekennung | `64e2`, Version 43.0 |
| Pumpen | **3 Stück, alle einstufig** |
| Lichter | 1 |
| Gebläse | vorhanden, einstufig |
| Umwälzpumpe | vorhanden |
| Mister | nein |
| Aux | keine |

### Zwei Nachrichtentypen waren in meiner Tabelle falsch zugeordnet
`BF 23` ist **Filter Cycles**, nicht Control Configuration 2; `BF 2E` ist
**Control Configuration 2**, das ich als unbekannt geführt hatte. `BF 25` existiert nicht.
Im Aufzeichnungswerkzeug korrigiert.

## 3. Folgen für den Entwurf

### 3.1 Arbitrierung: `IMMEDIATE` ist der einzige v1-Modus

Der geplante `TOKEN`-Modus entfällt aus dem Erstumfang, samt des dafür vorgesehenen
Sicherheitsnetzes — dessen Logik („30 s kein `Ready` ⇒ Warnung") auf einem falschen
Modell beruhte: `Ready` kommt im Sekundentakt, es gehört nur einem anderen Teilnehmer.

Token-gebundenes Senden wäre nur nach einer **Kanalanmeldung** über
`New Client Clear To Send` (`BF 00`, alle ~1 s beobachtet) sinnvoll. Das ist ein
eigenständiges Vorhaben mit echtem Risiko — eine fehlerhafte Anmeldung könnte den
Panel-Kanal stören. Es wandert in die Ausbaustufen.

**Das vereinfacht die Architektur:** kein Sendepuffer, keine Token-Zustandsmaschine, keine
Sonderfallbehandlung. Schreiben geht direkt raus. Die `ArbitrationMode`-Abstraktion bleibt
als Ein-Wert-Aufzählung erhalten, damit die Erweiterung später keinen Umbau erfordert.

### 3.2 Ausfallerkennung enger stellen

| Schwelle | vorher geplant | jetzt |
|---|---|---|
| Entities auf *nicht verfügbar* | 15 s ohne Frame | **5 s** |
| Verbindung neu aufbauen | 60 s ohne Frame | **20 s** |

Bei 300 ms Takt und 2,0 s größter gemessener Lücke ist 5 s eine Sicherheitsmarge von
Faktor 2,5 gegenüber dem Worst Case und erkennt einen eingefrorenen EW11 dreimal schneller
als geplant.

### 3.3 Handshake ohne Modul-Identifikation — bestätigt

Pflicht für ein erfolgreiches Setup sind **Status**, **`BF 24`** und **`BF 2E`**; letzteres
liefert die Gerätekonfiguration, aus der die Entities entstehen. `BF 94` wird angefragt,
aber ein Ausbleiben ist ausdrücklich **kein** Fehler. Genau so war es entworfen.

### 3.4 Entities für diese Anlage

Aus der gemessenen Konfiguration ergibt sich konkret: 1 `climate`, 3 `switch` für die
einstufigen Pumpen (oder `fan`, je nach Option), 1 `light`, 1 `switch` für das Gebläse,
1 `binary_sensor` für die Umwälzpumpe, dazu Temperatur-, Status- und Filterzyklus-Entities.
**Kein** Mister, **keine** Aux — die werden nicht angelegt.

Die geplante Mehrstufen-Toggle-Logik (Risiko R3) ist für diese Anlage **nicht relevant**,
da alle drei Pumpen einstufig sind. Sie bleibt im Entwurf für fremde Installationen,
verliert aber ihre Dringlichkeit und kann nach Phase 3 entstehen.

## 4. Abbruchkriterien

Aus [08-validierung.md](08-validierung.md) §6:

| # | Kriterium | Ergebnis |
|---|---|---|
| 1 | Keine Control Configuration über EW11 | **widerlegt** — `BF 24` und `BF 2E` kommen zuverlässig |
| 2 | Befehle ohne Kanalanmeldung verworfen | **widerlegt** für Anfragen (gemessen), für Befehle durch den laufenden bwalink-Betrieb belegt |
| 3 | Aufwand nach Phase 1 über 22 PT | offen, entscheidet sich nach Phase 1 |

**Kein Abbruchkriterium ist eingetreten. Phase 1 kann beginnen.**

## 5. Was sich am Aufwand ändert

| Posten | Wirkung |
|---|---|
| `TOKEN`-Arbitrierung entfällt | −0,5 PT |
| Mehrstufen-Pumpenlogik nicht mehr dringlich | −0,5 PT aus Phase 3 |
| Fixtures liegen vor, echte Referenzframes für Serialisierungstests | −0,5 PT |

Neue Schätzung: **≈ 12 PT** statt 13,5, erster nutzbarer Stand bei **≈ 8 PT**.
