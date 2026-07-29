# 08 — Validierung des Konzepts

Kritische Selbstprüfung. Was hält, was wackelt, was ist ungeprüft.

## 1. Erfüllt der Entwurf die gestellten Ziele?

| Ziel | Erfüllt | Wodurch |
|---|:--:|---|
| Vorteile beider Vorbilder kombinieren | ✅ | Transportvielfalt + Arbitrierung vom Gem, natives HA-Modell von pybalboa, Entity-Abdeckung und Namensabfrage von smartspaclient |
| Originales Balboa-WLAN-Modul | ⚠️ | `TcpTransport` Port 4257 — derselbe Code wie beim EW11, aber **mangels Hardware nicht verifizierbar** (§7) |
| EW11-Lösung | ✅ | `TcpTransport` mit freiem Port — der Pfad, der tatsächlich getestet wird |
| Per HACS installierbar | ✅ | Standard-Repo-Layout, `hacs.json`, Validierungs-Workflow |
| Konfigurierbar per Oberfläche | ✅ | Config Flow mit drei Anschlussarten, Optionen, Rekonfiguration |
| Zwei Instanzen | ✅ | Config Entries, strukturell unbegrenzt |
| Architektonisch state of the art | ✅ | Quality-Scale-Platinum als Zielbild, typisiert, asynchron, geschichtet |
| Einfach wartbar | ⚠️ | siehe Risiko R1 — die eigene Protokollbibliothek ist der teuerste Teil |
| Stabil | ✅ | Reconnect mit Backoff, Stale-Erkennung, defensiver Parser |
| Benutzerfreundlich | ✅ | Alltagssprache statt Protokollbegriffen, Klartextfehler, Discovery |

## 2. Die offene Kernfrage

**Liefert ein Aufbau ohne Balboa-WLAN-Modul eine Configuration Response (`0A BF 94`) mit
MAC-Adresse?**

Das ließ sich aus den Quellen nicht klären. Die Konsequenzen wären:

| Antwort | Folge für den Entwurf |
|---|---|
| ja | MAC ist überall verfügbar, `entry_id`-Rückfall wird selten gebraucht |
| nein | `entry_id`-Rückfall greift — **der Entwurf funktioniert unverändert** |

**Das ist der wichtigste Validierungspunkt: Die Frage muss nicht vorab beantwortet werden.**
Die Zwei-Ebenen-Identität ist gegen beide Ausgänge robust. Genau daran scheitern
`pybalboa` und `smartspaclient`, die die MAC als gegeben voraussetzen.

Phase 0 beantwortet die Frage nebenbei durch die Aufzeichnung.

## 3. Risiken

| # | Risiko | Schwere | Gegenmaßnahme |
|---|---|---|---|
| **R1** | **Eigene Protokollbibliothek** statt `pybalboa` — mehr Code in eigener Verantwortung, entgegen dem Ziel „einfach wartbar" | hoch | Das Protokoll ist eingefroren (Hardware erhält keine Updates), vollständig dokumentiert und wird gegen echte Aufzeichnungen getestet. Die Schnittstelle zu `balboa/client.py` ist schmal genug, um später doch auf `pybalboa` zu wechseln. **Ehrlich bleibt: das ist ein bewusster Tausch von Abhängigkeit gegen Kontrolle, kein kostenloser Gewinn.** |
| **R2** | **Kanalkonflikt**: Der Client sendet mit Quelladresse `0x0A`. Ist gleichzeitig ein echtes Balboa-WLAN-Modul am Bus, könnten beide denselben Kanal beanspruchen | ~~mittel~~ **entfällt** | Im hiesigen Aufbau ist **kein WLAN-Modul vorhanden** — Kanal `0x0A` ist frei und kann gefahrlos belegt werden. Das Risiko bleibt nur für fremde Installationen, die beides parallel betreiben; dafür ist die Kanalverhandlung über `New Client Clear To Send` als Ausbaustufe vorgemerkt |
| **R3** | **Mehrstufige Pumpen** werden per Toggle-Schleife gesetzt — anfällig für verlorene Frames und Rennbedingungen | mittel | Obergrenze für Toggles, Timeout, `assumed_state` während des Vorgangs, Abbruch bei Zielerreichung. Fixtures mit Pumpenschaltvorgängen aus Phase 0 |
| **R4** | **`TOKEN`-Arbitrierung** ist nur aus dem Gem abgeleitet, nicht selbst erprobt | mittel | Sicherheitsnetz: 30 s ohne `Ready` erzeugt einen Reparaturhinweis statt stiller Funkstille. Vorgabe für TCP bleibt `IMMEDIATE`, also der belegte Pfad |
| **R5** | **Aufwandsschätzung** 14,5 PT ist für eine erstmalige Protokollimplementierung optimistisch | mittel | Phase 0 und 1 sind die Unsicherheit; nach Phase 1 ist der Rest gut kalkulierbar. Realistischer Korridor: 14–22 PT |
| **R6** | **Serieller Port in HA OS** erfordert Gerätedurchreichung und kollidiert mit anderen Integrationen am selben Adapter | niedrig | `/dev/serial/by-id`-Auswahl, `port_busy`-Fehlermeldung im Klartext |
| **R7** | **HACS-Default-Aufnahme** verlangt zusätzlich einen Eintrag im `home-assistant/brands`-Repository für Logo und Icon | niedrig | Teil von Phase 6, kein technisches Risiko — nur ein zusätzlicher PR |
| **R8** | **Umstieg verliert Entity-Historie** — die `unique_id`-Schemata sind zu allen drei Vorgängern unvereinbar | mittel | Bewusst kein automatischer Migrationspfad; stattdessen dokumentierte Anleitung. Ein falsch migrierter Bestand wäre schlimmer als ein bewusst neu aufgebauter |

## 4. Gegengeprüfte Entwurfsentscheidungen

Wo ich zunächst anders entscheiden wollte und es nach Prüfung verworfen habe:

**Kein `DataUpdateCoordinator`.** Naheliegend, weil er der HA-Standardbaustein ist — aber
falsch. Die Steuerung pusht sekündlich; ein Coordinator würde ein Abfrageintervall
simulieren, das es nicht gibt. Die Core-Integration verzichtet aus demselben Grund darauf
und nutzt einen Event-Callback. Übernommen.

**Kein `water_heater`, sondern `climate`.** Das Gem-Vorbild erzeugt über Homie eine
`water_heater`-Entität. `climate` bildet Solltemperatur, Ist-Temperatur, Heizzustand und
Temperaturbereich in einer Karte ab und ist die vertrautere Bedienoberfläche.

**Heizmodus-Abbildung von der Core-Integration übernommen**, nicht selbst erfunden:
`READY → HVACMode.HEAT`, `REST → HVACMode.OFF`, `READY_IN_REST → HVACMode.AUTO`, wobei nur
`HEAT` und `OFF` setzbar sind und `AUTO` ein reiner Anzeigezustand ist. Der
Temperaturbereich läuft über `preset_mode`. Diese Abbildung ist in Core erprobt — sie neu
zu erfinden hätte nur Verwirrung erzeugt.

**Kein Abfrageintervall in den Optionen.** Wäre eine Scheinoption ohne Wirkung.

**Identität nicht aus Host+Port.** Verletzt Stabilität bei DHCP-Wechsel. Host und Port sind
Verbindungs-, keine Identitätsmerkmale.

## 5. Vergleich zum Bestand

| Kriterium | bwalink (heute) | smartspaclient | HA-Core `balboa` | **dieser Entwurf** |
|---|:--:|:--:|:--:|:--:|
| Balboa-WLAN-Modul | ✅ | ✅ | ✅ | ✅ |
| EW11 / serieller Gateway | ✅ | ❌ (Port fest) | ❌ (Port fest) | ✅ |
| Lokaler serieller Adapter | ✅ | ❌ | ❌ | ✅ |
| RS-485-Arbitrierung | ✅ | ❌ | ❌ | ✅ (umschaltbar) |
| Ohne MQTT-Broker | ❌ | ✅ | ✅ | ✅ |
| Mehrere Instanzen | ⚠️ (Slug-Kopien) | ✅ | ✅ | ✅ |
| Identität ohne MAC belastbar | ⚠️ | ❌ | ❌ | ✅ |
| Umbenennen gefahrlos | ❌ | ✅ | ✅ | ✅ |
| Discovery | ❌ | ❌ | ✅ | ✅ |
| Per HACS installierbar | ❌ (Add-on) | ✅ | n/a (Core) | ✅ |
| Klimaentität | ⚠️ | ✅ | ✅ | ✅ |
| Lizenz geklärt | ✅ | ❌ | ✅ | ✅ |

Die entscheidende Spalte ist **„Identität ohne MAC belastbar"** — dort ist dieser Entwurf
als einziger uneingeschränkt einsatzfähig, und genau das ist die Voraussetzung dafür, zwei
Spas über einen EW11 zu betreiben.

## 6. Wann das Konzept scheitern würde

Ehrliche Abbruchkriterien:

1. **Wenn über den EW11 keine Control Configuration (`0A BF 24`) eintrifft.** Dann wüsste
   die Integration nicht, welche Pumpen und Lichter existieren, und könnte keine Entities
   anlegen. Der Handshake macht diese Nachricht zur Pflicht. *Unwahrscheinlich* — das Gem
   benötigt sie ebenfalls und funktioniert nachweislich über EW11.
2. **Wenn Schreibbefehle ohne Kanalverhandlung grundsätzlich verworfen werden.** Dann wäre
   R2 kein Randfall, sondern zentral, und die Kanalverhandlung müsste in Phase 1 statt als
   Nachbesserung entstehen. Issue #73 („full reporting and control") spricht dagegen.
3. **Wenn der Aufwand nach Phase 1 deutlich über 22 PT läuft.** Dann wäre der Wechsel auf
   `pybalboa` mit einem Upstream-Beitrag für die Transport-Abstraktion die günstigere Route.

Alle drei sind nach **Phase 0 und 1** entscheidbar — also nach etwa 4,5 Personentagen und
vor der eigentlichen Investition. Das ist der wesentliche Punkt: Der Plan legt die
Unsicherheit an den Anfang, nicht ans Ende.

## 7. Verfügbare Hardware und ihre Folgen

Zur Verfügung stehen **zwei Balboa-Anlagen, beide über einen Elfin EW11** angebunden.
Ein originales Balboa-WLAN-Modul gibt es nicht. Das hat vier Konsequenzen:

**1. Der wichtigste Pfad ist der testbare.** Der EW11 ist genau der Aufbau, den keine der
bestehenden Python-Lösungen bedient — und er wird auf echter Hardware verifiziert,
einschließlich zweier gleichzeitiger Instanzen. Das ist die günstige Verteilung: getestet
wird dort, wo Neuland ist.

**2. Das WLAN-Modul bleibt unverifiziert — mit geringem Risiko.** Beide Anschlussarten
nutzen **denselben** `TcpTransport` mit demselben Framing und demselben Parser; sie
unterscheiden sich nur in der Portvorgabe und im voreingestellten Sendeverfahren. Der Code
wird also durch die EW11-Tests weitgehend mit abgedeckt. Ungetestet bleiben genau zwei
Dinge: die Portvorgabe 4257 und die Annahme, dass das Modul dieselben Frames liefert —
Letzteres ist durch `pybalboa` und die HA-Core-Integration unabhängig belegt.
→ Im README wird das WLAN-Modul als **„unterstützt laut Entwurf, nicht auf Hardware
verifiziert"** ausgewiesen, nicht als getestet.

**3. Discovery fliegt aus dem Erstumfang.** UDP-30303- und DHCP-Discovery funktionieren
ausschließlich mit dem WLAN-Modul. Nicht verifizierbarer Code, der in fremden
Installationen ungefragt Einrichtungsvorschläge erzeugt, ist ein schlechter Tausch für
einen Punkt auf der Qualitätsskala. Verschoben in die Ausbaustufen, Voraussetzung: ein
Tester mit passender Hardware.

**4. Risiko R2 entfällt.** Ohne WLAN-Modul am Bus ist Kanal `0x0A` unbesetzt, ein
Kanalkonflikt kann im eigenen Aufbau nicht auftreten. Die Kanalverhandlung wird damit von
einer möglichen Pflichtaufgabe zu einer optionalen Ausbaustufe für Fremdinstallationen.

**Was dadurch nicht kleiner wird:** Die offene MAC-Frage aus §2 betrifft ausschließlich den
EW11-Pfad — sie wird also vollständig beantwortet. Und da im eigenen Aufbau ohnehin kein
WLAN-Modul existiert, ist die Wahrscheinlichkeit hoch, dass der `entry_id`-Rückfall der
Normalfall wird. Genau dafür wurde er entworfen.

## 8. Nächste Schritte

1. **Phase 0 durchführen** — zwei Aufzeichnungen über den EW11 (Ruhezustand und Bedienung
   am Panel). Beantwortet die MAC-Frage, liefert die Fixtures für die Toggle-Logik
   mehrstufiger Pumpen (R3) und alle Parsertests.
2. Ergebnis gegen dieses Dokument halten und die drei Abbruchkriterien aus §6 prüfen.
3. Erst dann mit Phase 1 beginnen.
