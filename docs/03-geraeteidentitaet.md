# 03 — Geräteidentität

Das ist die Stelle, an der alle drei bestehenden Lösungen Schwächen haben. Sie bekommt
deshalb ein eigenes Dokument.

## 1. Die Anforderungen

Eine Identität muss vier Eigenschaften gleichzeitig erfüllen:

| # | Anforderung | Warum |
|---|---|---|
| A1 | **Eindeutig** über beliebig viele Instanzen | Pool und Whirlpool am selben HA |
| A2 | **Stabil** über Neustarts, Updates, IP-Wechsel | sonst verwaisen Entities |
| A3 | **Unabhängig vom Anzeigenamen** | Umbenennen muss folgenlos bleiben |
| A4 | **Verfügbar in jedem Aufbau** | auch ohne Balboa-WLAN-Modul |

## 2. Warum die bestehenden Ansätze scheitern

| Ansatz | A1 | A2 | A3 | A4 | Bruchstelle |
|---|:--:|:--:|:--:|:--:|---|
| Homie-`device_id` (bwalink) | ⚠️ | ✅ | ❌ | ✅ | Nutzer wählt ihn — Umbenennen verwaist alles, Tippfehler kollidiert |
| MAC (pybalboa, HA-Core) | ✅ | ✅ | ✅ | ❌ | ohne WLAN-Modul evtl. nicht verfügbar |
| MAC (smartspaclient) | ❌ | ✅ | ✅ | ❌ | fällt auf `"Unknown"` zurück → **zwei Spas kollidieren** |
| IP-Adresse | ✅ | ❌ | ✅ | ✅ | DHCP-Wechsel bricht alles |

Der Fall `"Unknown"` bei smartspaclient ist besonders tückisch: Es *scheint* zu
funktionieren, solange nur ein Spa angebunden ist, und bricht erst beim zweiten — also
genau dann, wenn es niemand mehr erwartet.

## 3. Der gewählte Ansatz: Zwei-Ebenen-Identität

Der entscheidende Gedanke: **Die Identität muss nicht aus dem Gerät kommen.**
Home Assistant erzeugt beim Anlegen eines Config Entry eine `entry_id` — eine UUID, die
für die Lebensdauer des Eintrags stabil, prozessweit eindeutig und vom Nutzer nicht
beeinflussbar ist. Sie erfüllt A1–A4 bedingungslos.

```python
def device_key(entry: ConfigEntry) -> str:
    """Stabiler Schlüssel für Geräte- und Entity-Identität."""
    if mac := entry.data.get(CONF_MAC):
        return format_mac(mac)          # bevorzugt: hardwaregebunden
    return entry.entry_id               # Rückfall: immer verfügbar
```

- **`unique_id` des Config Entry:** die MAC, sofern bekannt. Sonst **keine** — Duplikate
  werden stattdessen über `_async_abort_entries_match({host, port})` bzw. `{device}`
  verhindert. HA erlaubt Einträge ohne `unique_id` ausdrücklich.
- **`DeviceInfo.identifiers`:** `{(DOMAIN, device_key)}`
- **`DeviceInfo.connections`:** `{(CONNECTION_NETWORK_MAC, mac)}` — nur wenn MAC bekannt.
  Dadurch verknüpft HA das Gerät automatisch mit dem DHCP-Eintrag.
- **`unique_id` der Entity:** `f"{device_key}_{entity_key}"`, z. B.
  `001527aabbcc_pump_1` oder `01JB3K…_pump_1`.

### Warum nicht Host+Port als Schlüssel?

Verletzt A2: Ein DHCP-Wechsel oder das Umkonfigurieren des EW11-Ports würde alle Entities
neu anlegen. Host und Port sind Verbindungsparameter, keine Identität — sie gehören in
`entry.data` und dürfen sich beim Rekonfigurieren ändern, ohne Wirkung auf die Identität.

## 4. Nachträgliche MAC-Ermittlung

Wird ein Aufbau ohne MAC angelegt und die Steuerung liefert später doch eine
Configuration Response (`0A BF 94`), soll die Identität **nicht** wechseln — das würde
genau die Verwaisung auslösen, die vermieden werden soll.

Verhalten:
1. Die MAC wird in `entry.data["mac"]` **nachgetragen** (informativ, für die Diagnose und
   die Geräteseite).
2. `device_key` bleibt bei der `entry_id`, sobald einmal Entities damit angelegt wurden.
   Umgesetzt über ein Feld `entry.data["identity_source"]` (`"mac"` | `"entry_id"`), das
   beim ersten erfolgreichen Setup festgeschrieben und danach nie geändert wird.
3. `connections={(CONNECTION_NETWORK_MAC, mac)}` wird trotzdem gesetzt — die
   Netzwerkverknüpfung funktioniert damit auch nachträglich.

Das kostet einen minimalen Schönheitsfehler (der Schlüssel ist dann eine UUID statt der
MAC) und erkauft dafür absolute Stabilität. Der Handel ist eindeutig richtig.

## 5. Migration bestehender Aufbauten

Für Umsteiger von `bwalink`/MQTT oder von der Core-Integration lassen sich Entities nicht
automatisch übernehmen — die `unique_id`-Schemata sind unvereinbar
(`bwa2_spa_pump1` bzw. `model-key-aabbcc` gegen `<key>_pump_1`).

Der ehrliche Umgang damit:
- Die Dokumentation weist ausdrücklich darauf hin, dass Entities neu angelegt werden.
- Ein Abschnitt „Umstieg" beschreibt, wie man alte Entity-IDs freigibt und die neuen per
  *Einstellungen → Entitäten → Umbenennen* auf die gewohnten IDs zieht, damit Automationen
  und Dashboards weiterlaufen.
- Kein automatischer Migrationspfad — er wäre gegenüber drei verschiedenen Vorgänger-
  schemata fehleranfällig, und ein falsch migrierter Bestand ist schlimmer als ein
  bewusst neu aufgebauter.

## 6. Prüfkriterien

Diese Fälle müssen im Test abgedeckt sein:

| Fall | Erwartung |
|---|---|
| Zwei Spas, beide mit MAC | zwei Geräte, keine Kollision |
| Zwei Spas, **keiner** mit MAC | zwei Geräte, keine Kollision (unterschiedliche `entry_id`) |
| Zwei Spas, einer mit, einer ohne MAC | zwei Geräte, keine Kollision |
| Spa wechselt die IP | Entities unverändert, `entry.data["host"]` aktualisiert |
| Nutzer benennt Gerät um | Entities unverändert |
| MAC taucht nachträglich auf | Entities unverändert, `connections` ergänzt |
| Derselbe Host zweimal hinzugefügt | zweiter Versuch bricht mit `already_configured` ab |
