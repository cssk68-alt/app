# Änderungen 29.05.2026 – Slide 4: Auto-Refresh + robustere Daten-Updates

Kontext für künftige Sessions: Slide 4 (Portfolio vs. MSCI World) hing fest –
der angezeigte Stand blieb auf 14 Uhr stehen (grüner Haken, keine Fehlermeldung),
obwohl es schon nach 19 Uhr war. Hier steht, was kaputt war und was gefixt wurde.

## Symptom
- Stand der Daten fror bei `last_updated = 2026-05-29T12:02:26Z` (= 14:02 Berlin) ein.
- Trotzdem grüner Haken, keine Fehlermeldung.

## Root Cause (zwei Probleme)
1. **Frontend lud die Daten nur 1× pro Session.** `initPerformance()` war durch
   `_performanceInitialized` gesperrt; weitere Besuche von Slide 4 riefen nur
   `updatePerformanceEUR()` auf den *bereits geladenen* `_perfData` auf →
   `performance.json` wurde nie erneut gefetcht. Offene PWA = eingefroren auf den
   Stand vom App-Start. **(Hauptursache, warum sich nichts änderte.)**
2. **Backend brach still ab.** `update_performance.py` machte bei FX-Ausfall /
   Yahoo-Rate-Limit ein `return` *ohne* Datei-Write → alte „alles OK"-Datei blieb
   liegen → grüner Haken auf veralteten Daten. Der `*/30`-Cron produzierte seit
   12:02 UTC keine frischen Commits mehr.

## Fix (Commit `bc82b7b` auf `main`)
- **`index.html`**
  - `initPerformance()` aufgeteilt in Einmal-Setup + wiederverwendbares
    `refreshPerformance()` (holt `performance.json` neu + re-rendert).
  - `refreshPerformance()` triggert bei **jedem** Slide-4-Besuch, **alle 10 Min**
    (`setInterval`, nur wenn Tab sichtbar) und bei **`visibilitychange`/`focus`**.
  - Marktzeit-bewusster Veraltungs-Hinweis (`_isUpdateWindow`, Mo–Fr 07–22 UTC,
    `last_updated` > 90 Min): zeigt „wird aktualisiert…" statt falschem grünem
    Haken. Nachts/Wochenende kein Fehlalarm.
  - Footer-Version → `v23`.
- **`update_performance.py`**
  - **FX-Fallback**: schlägt EUR/USD bzw. EUR/GBP fehl, wird der letzte bekannte
    Kurs aus `_meta.fx_snapshot` (`USD_latest`/`GBP_latest`) genutzt statt
    abzubrechen. (FX bewegt sich intraday nur minimal.)
  - **Yahoo robuster**: Host-Fallback `query1` → `query2`, Retries 3 → 4.
- **`.github/workflows/update_data.yml`**
  - Performance-Cron `*/30 7-21 * * 1-5` → **`7,37 7-21 * * 1-5`** (2×/Std,
    Versatz von `:00`/`:30`, die GitHub unter Last häufiger überspringt).
- **`sw.js`**: `CACHE_NAME` → `sparplan-v26-20260529-v24` (Force-Reload bei
  Aktivierung).

## Verifiziert
- Python kompiliert; JS-Syntax valide (`node --check`).
- FX-Fallback-Erfolgspfad simuliert: FX-Live-Ausfall → 12/12 Ticker →
  `update_success: true`.
- Veraltungslogik gegen mehrere Zeitpunkte getestet (Fr 19 Uhr → stale=true;
  Wochenende/Nacht → false).
- **In Produktion bestätigt**: Push auf `main` triggerte den Workflow, Commit
  `dfb3d4d` schrieb `last_updated = 2026-05-29T17:45:17Z` (= 19:45 Berlin),
  12/12 Ticker, keine Fehler. Stale-14-Uhr-Daten waren damit abgelöst.

---

# Zusätzliche Änderungen (30.05.2026) – Designüberarbeitung + Fallback-Härtung

## Übersicht
Neben der Auto-Refresh-Lösung waren noch **13 Bugs** zu fixieren (Bug-Scan via CodeAI). Davon haben wir die **7 Top-Prioritäten** angegangen: 3 Design-Probleme (Modal-Bleed, fehlende Close-Button, doppelte Status-Boxen) + 4 Data-Pipeline-Probleme (UTC-Fehler, falsches Zeitfenster, unvollständige Fallbacks, stille Ausfälle ohne Einfrieren).

## 1. Design-System-Überhaul (`index.html`)

### Modales Design: Scoped CSS gegen Style-Bleed
- **Problem**: Modal-Regeln wie `select, input, button { border: ... }` bluteten in die
  Haupt-Seite zurück und beschädigten Inputfelder auf den Slides.
- **Lösung**: Alle Modal-Styles neu geschrieben unter `.modal *` Selektor, vollständig
  gekapselt. Test: Main-Page-Inputs unverändert ✓
- **Sticky Close-Button**: Neue Wrapper-Architektur mit `position: sticky; top: 0; height: 0;`
  + `pointer-events` Trick (Parent deaktiviert, Button selbst aktiv) → sticky-Close-Button
  funktioniert über beliebigen Scroll-Kontext hinweg, auch im Modal-Inneren.

### Vereinigte Status-Box statt zwei separater Divs
- **Problem**: `#perf-offhours` (oben) + `#perf-status-info` (unten, unterschiedliche Styles)
  → verwirrend, wartungsfeindlich, bei Partial-Failures unklar welche Box zeigen.
- **Lösung**: Neue einzelne Box `.perf-status-info-box` mit Modifier-Klassen:
  - `.msg` = 🌙 Off-Hours-Hinweis (Nachts/Wochenende)
  - `.warn` = Fehler/Stale-Hinweis (rote Warnung)
  - `.show` = Sichtbarkeit togglen
  - Gelöschte HTML-Knoten → Code-Reduktion + semantisches Clarity.

### Zeit-Quellen-Split + DST-sichere Anzeige
- **Problem**: Frontend zeigte `last_updated` als Uhrzeit, aber nur die aktuelle Daten-Reihe-Stempel, nicht wann "alles OK" war.
  Bei Partial-Failures (z. B. 1/12 Ticker ausfallen) würde Stunde springen.
- **Lösung**:
  - **Datum** = `last_updated` (zeigt: "heute geprüft")
  - **Uhrzeit** = `last_all_ok_timestamp` (gefriert, wenn <12 Ticker erfolgreich)
  - Neue Helper `_getBerlinWeekday(now)` via `Intl.DateTimeFormat` (DST-sicher)
  - Neue Helper `_nextUpdateStart(now)` rechnet nächste Handelstag 07:00 UTC (DST-aware)
  - Stunden-Format: `replace(/^0(?=\d)/, '')` → "09" → "9", "00" → "0" (führende Null weg)

### Update-Fenster-Timing: 07:10 UTC statt 07:00
- **Problem**: Um 07:00 UTC (exakt Cron-Start) zeigte das Frontend sofort "wird aktualisiert…",
  aber der Cron brauchte ~7 Min bis zum schreiben von `last_updated` → falscher "Updating"-Hinweis
  wenn man direkt nach 07:00 die App öffnete.
- **Lösung**: `_isUpdateWindow()` nun `hour >= 7 && min >= 10` (07:10 UTC buffer) statt >= 07:00.
  Verhindert Morning-False-Positives, Cron hat ausreichend Zeit.

---

## 2. Strikte All-Or-Nothing Freeze-Policy (`update_performance.py`)

### Grund für Freeze-Logik
Ein fehlgeschlagenes Ticker-Update sollte nicht zu renormalisiertem (verzerrt gewichteten)
Portfolio führen. Stattdessen: Partial-Failure → alte Daten einfrieren, nur Metadata
aktualisieren.

### Neue `write_frozen(existing_obj, failed_tickers, now_utc)` Funktion
```
- Eingang: bestehende performance.json, Liste fehlgeschlagener Tickers, aktueller UTC-Timestamp
- Erhält: dates[], portfolio[], msci_world[], weekly[], ticker_returns[] unverändert
- Updated: last_updated (aktuell), failed_tickers (neue Liste), tickers_ok (Count verfügbarer Tickers)
- Friert: last_all_ok_timestamp (bleibt bei letztem All-12-OK-Lauf)
- Rückgabe: True wenn geschrieben, False wenn keine Fallback-Datei existiert
```

Drei Call-Sites in `main()`:
1. Wenn `n_ok < 12` nach Fetches (nicht genug Tickers)
2. Wenn MSCI-Fetch fehlschlägt
3. Wenn EUR-Konversion fehlschlägt

### MIN_SUCCESS_TICKERS: 10 → 12
Nur alle 12 Tickers erfolgreich = "alles OK". Unter 12 = auto-Freeze. Keine Renormalisierung nötig.

---

## 3. Erweiterte FX- und Ticker-Fallback-Ketten

### FX-Fallback-Kette (vorher: Yahoo → Stooq)
**Neu (Commit 6de6c59)**:
1. Yahoo (primär, schnell, tägliche Ranges)
2. Stooq (sekundär, keine API-Keys nötig)
3. **Frankfurter/EZB** (`fetch_fx_frankfurter`) – keyless, offizielle EZB-Kurse, Ranges
4. **open.er-api** (`fetch_fx_erapi`) – keyless, Echtzeit-Kurse (nutzt heute für Rangenanfrage)
5. **AlphaVantage** (`fetch_fx_alphavantage`) – key-gated (inert ohne `ALPHAVANTAGE_KEY`)

Frankfurter/open.er-api sind öffentlich, keine API-Keys. Nur falls beide aus gehen:
→ AlphaVantage tries (wenn env-Var existiert).

### Ticker-Fallback-Kette (vorher: Yahoo → Stooq)
1. Yahoo (primär)
2. Stooq (sekundär)
3. **AlphaVantage** (`fetch_av`) – key-gated, Symbol-Map `{"SXR8": "SXR8.DEX", ...}`
   (Nur Tickers in der Map können AlphaVantage versuchen; bei Unbekanntem skipped es.)

### Implementation-Details
- `ALPHAVANTAGE_KEY = os.environ.get("ALPHAVANTAGE_KEY", "").strip()` (aus GitHub Secret)
- `ALPHAVANTAGE_SYMBOLS` statisches Dict für bekannte ETF-AV-Symbole
- Fehlerlogik: auf `None` prüfen, nicht mit Exception umgehen
- Conditional Logging: jede Quelle loggt `[FX EUR_USD] Yahoo OK` / `[SXR8] Stooq Fallback` etc.

---

## 4. UTC-Timezone Fix

### Problem
```python
# ALT (falsch bei DST):
date.fromtimestamp(ts)  # = lokale Systemzeit, kann DST-Sprünge haben
```

### Lösung
```python
# NEU (UTC-safe):
from datetime import datetime, timezone
datetime.fromtimestamp(ts, tz=timezone.utc).date()
```
Garantiert UTC-sichere Date-Berechnung ohne DST-Fehler. (Linie 132 in `update_performance.py`.)

---

## 5. Workflow-Integration (`update_data.yml`)

### Secrets-Übergabe an Performance-Step
```yaml
- name: Update Performance
  ...
  env:
    ALPHAVANTAGE_KEY: ${{ secrets.ALPHAVANTAGE_KEY }}
```
Falls Secret nicht gesetzt → Env-Var leer → AlphaVantage bleibt inert, kein Fehler.

### Cron-Comment Korrektur
Alte Doku war ungenau. Neu (Linie 5):
```
'7,37 7-21 * * 1-5'  # Mo-Fr, 2×/Std, :07 und :37 (Versatz von :00/:30)
```

---

## 6. Backend-Logging + Fehler-Transparenz

Jeder Fetch-Versuch loggt seinen Versuch + Ergebnis:
```
[FX EUR_USD] Yahoo OK (3 rates)
[FX EUR_GBP] Yahoo Fail (429) → Fallback: Stooq OK
[SXR8] Yahoo OK
[IWDA.AS] Yahoo OK → ... [ALV] Stooq Fail → Fallback: AlphaVantage (no mapping)
[MSCI] ...
```

Debugging: GitHub Actions → **Actions** → Run-Log → Suchtext `[FX `, `[MSCI `, `Fallback`, `frozen`.

---

## 7. Externe Tasks – delegiert an Coworker (cron-job.org + Secrets)

### AUFGABE 1: Externer Cron (cron-job.org) – GitHub-Scheduler-Zuverlässigkeit
GitHub-`schedule`-Crons sind "best effort" (10–30 Min Verzug, gelegentlich gedroppt).
→ Externe Trigger via **workflow_dispatch** + **cron-job.org** (kostenlosen Dienst).

**Schritte für Coworker**:
1. GitHub PAT (fine-grained) erstellen: Settings → Developer settings → Personal access tokens
   → Fine-grained tokens. Scope: `cssk68-alt/app`, Permissions: Actions (read+write).
2. cron-job.org registrieren, neue Job:
   - URL: `https://api.github.com/repos/cssk68-alt/app/actions/workflows/update_data.yml/dispatches`
   - Method: POST
   - Headers: `Accept: application/vnd.github+json`, `Authorization: Bearer <TOKEN>`,
     `X-GitHub-Api-Version: 2022-11-28`, `User-Agent: cronjob-sparplan`, `Content-Type: application/json`
   - Body: `{"ref":"main"}`
   - Schedule: Mo–Fr 07:15–21:45 UTC (:15, :45 Versatz gegen Lastspitzen)
3. Test-Run durchführen → erwartet HTTP 204.

**Verifikation**: `curl -X POST ... /dispatches -d '{"ref":"main"}'` lokal; GitHub Actions zeigt neuen Run mit Trigger `workflow_dispatch`.

### AUFGABE 2: AlphaVantage-Secret – optionaler 3. Fallback
1. API-Key kostenlos: https://www.alphavantage.co/support/#api-key
2. GitHub-Repo → Settings → Secrets and variables → Actions → New repository secret
   - Name: `ALPHAVANTAGE_KEY` (exakt!)
   - Wert: <key>
3. Workflow triggert darauf automatisch; AlphaVantage wird 3. Fallback.

**Hinweis**: AV kennt nicht alle UCITS-ETFs. Im Code sind nur SXR8, ALV, ISF mapped.
Falls weitere bekannt, dem Code hinzufügen (Linie ~50 in `update_performance.py`).

### AUFGABE 3: Keyless-API-Erreichbarkeit Test
Aus offener Netz-Umgebung (mit Internet):
```bash
curl -s -o /dev/null -w "frankfurter:  %{http_code}\n" \
  "https://api.frankfurter.app/2026-05-18..2026-05-29?base=EUR&symbols=USD,GBP"
curl -s -o /dev/null -w "open.er-api:  %{http_code}\n" \
  "https://open.er-api.com/v6/latest/EUR"
curl -s -o /dev/null -w "yahoo:        %{http_code}\n" -A "Mozilla/5.0" \
  "https://query1.finance.yahoo.com/v8/finance/chart/IWDA.AS?interval=1d&range=5d"
curl -s -o /dev/null -w "stooq:        %{http_code}\n" \
  "https://stooq.com/q/d/l/?s=iwda.nl&d1=20260518&d2=20260529&i=d"
```
Erwartet: 200 für alle vier. Falls einer ausfällt → Fallback-Priorität anpassen.

---

## Verifizierung

- ✓ Python-Syntax valide, Imports OK
- ✓ Mock-Tests für alle 4 Parser (Yahoo, Stooq, Frankfurter, EZB-Fallback)
- ✓ Freeze-Regression: 12/12-Fehler → `write_frozen` aufgerufen, alte Daten bleiben
- ✓ Git-Verifikation: 2 Commits (Design + Fallback) auf Feature-Branch, gemerged auf `main @ 6de6c59`
- ✓ Workflow-Lauf via `push`-Trigger erfolgreich (bestätigt von GitHub Actions)
- ✓ Modal-Scope-Isolation: Main-Page Inputfelder unbeeinträchtigt nach Style-Reorg

---

## Architektur-Merker (für den nächsten Chat)
- Statische GitHub-Pages-PWA: ein `index.html` (Vanilla JS) + Python-Scripts.
  Kein Server/DB. Daten liegen als committete JSON unter `data/`.
- `update_performance.py` läuft in GitHub Actions, committet `data/performance.json`,
  Pages deployed neu, Browser liest die JSON. Quellen: Yahoo (primär) + Stooq + Frankfurter/EZB
  + open.er-api + AlphaVantage (alle Fallbacks).
- Der Workflow-`push`-Trigger feuert nur bei Änderung der `update_*.py` /
  `update_data.yml` → Code-Push an diesen Dateien stößt sofort ein Daten-Update an.
- **GitHub-Cron ist „best effort"** → parallele Trigger via `workflow_dispatch` von externem
  cron-job.org erhöht Zuverlässigkeit.
- Frontend-Auto-Refresh ist der Hebel: sobald *irgendein* Lauf neue Daten liefert,
  holt die App sie selbsttätig (10-Min-Intervall + bei Focus/Visibility-Change).
- Status der Läufe prüfen: GitHub → **Actions** (Logs auf `[FX …]`, `[Ticker …]`, `Fallback`,
  `frozen`, `last_updated`).
