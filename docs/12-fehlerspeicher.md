# 12 — Fehlerspeicher

Der Fehlerspeicher war der einzige Nachrichtentyp, der in den bisherigen
40 000 Frames nie aufgetaucht ist — er antwortet nur auf Anfrage. Deshalb wurde er
**nicht auf Verdacht implementiert**, sondern erst nach einer Aufzeichnung.

## Die Anfrage

Es ist eine weitere Variante der Konfigurationsanfrage `0A BF 22`:

```
7e 08 0a bf 22 20 <Eintrag> 00 <crc> 7e
                  ^^         ^^
                  Selektor   Eintragsnummer
```

**Das erste Nutzlastbyte ist ein Selektor, keine Nummer.** Diese Unterscheidung
ist der Kern der Sache:

| Erstes Byte | Antwort |
|---|---|
| `0x02` | Control Configuration (`BF 24`) — Modell, Version |
| `0x01` | Filterzyklen (`BF 23`) |
| `0x00` (mit `01` im dritten Byte) | Control Configuration 2 (`BF 2E`) |
| **`0x20`** | **Fehlerspeicher (`BF 28`)** |

Hätte man das Schema eines anderen Projekts ungeprüft übernommen und „Eintrag 1"
mit `01 00 00` angefragt, wäre stattdessen die Filterzyklus-Antwort gekommen —
ein Fehler, der sich als merkwürdiger Fehlerspeicher-Inhalt getarnt hätte.

## Die Messung

Drei Anfragen, drei Antworten, in einem Durchlauf:

```
gesendet  7e 08 0a bf 22 20 00 00 ...   ->  98 00 13 ff 0c 00 18 42 43 43
gesendet  7e 08 0a bf 22 20 01 00 ...   ->  98 01 13 ff 0c 00 18 42 43 43
gesendet  7e 08 0a bf 22 20 00 01 ...   ->  98 00 13 ff 0c 00 18 42 43 43
```

Damit ist belegt:

- Die **Eintragsnummer steht im zweiten Nutzlastbyte** (`00` → Eintrag 0, `01` → Eintrag 1).
- Das **dritte Byte ist wirkungslos** — dieselbe Antwort wie ohne.
- Die Steuerung **spiegelt die angefragte Nummer** in Byte 1 der Antwort zurück.

## Die Antwort

| Byte | Inhalt |
|---|---|
| 0 | Zähler (siehe unten) |
| 1 | Eintragsnummer, gespiegelt |
| 2 | Fehlercode |
| 3 | „vor X Tagen" |
| 4, 5 | Stunde, Minute |
| 6 | Flags |
| 7 | Solltemperatur, roh |
| 8, 9 | Sensor A und B, roh |

**Die Temperaturen bestätigen die Dekodierung.** Der aufgezeichnete Eintrag meldet
`42 43 43` = 66/67/67. Mit der Celsius-Halbierung sind das 33,0 / 33,5 / 33,5 °C —
exakt Soll- und Wassertemperatur, auf der die Anlage im selben Moment stand.
Ein Zufall ist bei drei übereinstimmenden Werten auszuschließen.

## Zwei Dinge, die bewusst offenbleiben

**Byte 0 heißt nicht „Anzahl der Einträge".** Fremde Dokumentation nennt es
„Total Entries (0–24)", die Steuerung meldet aber **152**. Entweder ist es ein
Lebenszähler, oder die Bedeutung ist eine andere. Das Feld heißt deshalb schlicht
`counter` und wird als Attribut durchgereicht, statt eine Bedeutung zu behaupten,
die nicht gemessen wurde.

**Es wird nur der neueste Eintrag gelesen.** Der Speicher enthält mehr, aber ohne
verlässliche Tiefenangabe wäre jede Schleife über die Einträge geraten. Der
Zugriff auf ältere Einträge ist implementiert (`request_fault_log(n)`), wird aber
von der Integration nicht von selbst genutzt.

## Umsetzung in Home Assistant

Ein Diagnose-Sensor **Letzte Störung** mit dem Fehlercode als Zustand und Details
als Attribute: Code, „vor X Tagen", Uhrzeit, die drei Temperaturen und der
Zähler. Abgefragt wird beim Verbindungsaufbau und danach alle fünf Minuten —
Störungen sind selten, häufiges Nachfragen brächte nichts und belastete nur den Bus.

Die Formulierungen der Fehlercodes stammen aus Balboas Servicedokumentation und
sind eigenständig formuliert. Unbekannte Codes werden als `code_<n>` durchgereicht
und im Sensor als `unknown` angezeigt, statt sie zu verstecken.

## Nebenbefund

Im selben Mitschnitt blieb die **Filterzyklus-Antwort aus**, obwohl sie angefragt
wurde — verlorengegangen im Busverkehr. Das bestätigt nachträglich die Entscheidung
aus v0.4.0, die Filterzyklus-Entitäten unabhängig vom Eintreffen des Frames
anzulegen. Wäre sie noch an die Antwort gekoppelt, hätte dieser Aufbau keine
Filterzyklus-Entitäten bekommen.
