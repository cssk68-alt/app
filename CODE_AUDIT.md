# Code-Audit & Änderungs-Log: Sparplan-PWA

Stand: 2026-06-02 · Branch `claude/festive-mccarthy-Ebczj`

## Zuletzt umgesetzt (diese Session)

### 1. B1 – Service-Worker-Offline-Cache repariert (sw.js)
- Offline-Lookup für `/data/*` ignoriert jetzt den `?t=`-Cache-Buster und liefert
  die **neueste** gecachte Kopie (vorher: immer Miss → toter Offline-Pfad).
- **Rollende 3 Kopien** pro Daten-Datei; ältere werden nach jedem Schreiben gelöscht.
- `CACHE_NAME` → v30 (alte Müll-Kopien werden beim Aktivieren einmalig gelöscht).

### 2. A1 / 12-12-Politik – geklärt, KEIN Code nötig
- Renormieren (`wsum/used`) wurde **verworfen** (würde Werte erfinden).
- Bestätigt: Bei <12/12 friert die App den Kurs auf dem letzten kompletten Stand
  ein (`write_frozen`) und zeigt die Fehlermeldung – genau das gewünschte Verhalten.

### 3. B3 / EUR-Historie – bereits gefixt (Vorsession)
- `_meta.fx_history` + `_merge_fx()`: jeder Vergangenheitstag mit seinem echten
  Wechselkurs → keine rückwirkende EUR-Verzerrung.

### 4. Erste Seite: Holdings korrigiert (index.html GROUPS)
- **Befund:** die hardcodierten `details` waren **veraltete Platzhalter (~2023)**,
  online gegengeprüft (3 Quellen-Familien + holdings.json).
  Schwerster Fehler: CSKR „SK Hynix 9 %" → real ~19 % (AI-Memory-Boom; SK Hynix
  +274 % in 2025); „LG Energy Solution" gar nicht mehr in den Top-Holdings.
- **Umsetzung:** alle 8 betroffenen ETFs auf **verifizierte aktuelle Werte**
  gesetzt (SXR8, CPXJ, CSKR, IJPA, WHCS, AGED, EIMI, ISF).
- **Hinweis:** Echte 09.-Mai-Holdings sind öffentlich **nicht** rekonstruierbar
  (Emittenten 403, nur aktueller Stand publik). Eingetragen ist der verifizierte
  aktuelle Stand als bestmögliche Näherung.

### 5. Version v29 → v30 (Title + Footer Seite 1)

## Geplant / offen (besprochen, noch nicht gebaut)
- **Neue Slide „Veränderungen"** (nach Performance): Tab-UI „1/2…" pro
  **Kalenderquartal** (Q1=Jan–Mär …), erstes Quartal verkleinert (Einstieg 09.05.).
  Zeigt je ETF Deltas ≥ 0,5 % (Kurs / Positions-Gewichte / neu-raus / Sektor- &
  Länder-Shifts), kleinere Änderungen werden weggelassen.
- **Kurse 09. Mai:** sauber über die Pipeline (`BASELINE_DATE` → 09.05.), nicht
  hardcoden (nur ALV 369,10 € war hart belegbar).
- Display-Preise auf Seite 1 (gemischte Währungen/Stände) noch zu vereinheitlichen.

## Weiterhin offen (aus Erst-Audit)
- A2 12/12 entschärfen → **bewusst gelassen** (Nutzer will strikt 12/12).
- A8 (MSCI-Ausfall in tickers_ok), B2 (Gewichte zentralisieren), B4/B5 (Workflows),
  C1/C2 (toter Code), C4–C6 (Cache-/Doku-Aufräumen).
