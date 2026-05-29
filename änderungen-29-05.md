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

## Architektur-Merker (für den nächsten Chat)
- Statische GitHub-Pages-PWA: ein `index.html` (Vanilla JS) + Python-Scripts.
  Kein Server/DB. Daten liegen als committete JSON unter `data/`.
- `update_performance.py` läuft in GitHub Actions, committet `data/performance.json`,
  Pages deployed neu, Browser liest die JSON. Quelle: Yahoo (primär) + Stooq (Fallback).
- Der Workflow-`push`-Trigger feuert nur bei Änderung der `update_*.py` /
  `update_data.yml` → Code-Push an diesen Dateien stößt sofort ein Daten-Update an.
- **GitHub-Cron ist „best effort"** und kann Läufe überspringen – nicht zu 100 %
  erzwingbar. Deshalb ist der Frontend-Auto-Refresh der eigentliche Hebel:
  sobald *irgendein* Lauf neue Daten liefert, holt die App sie selbsttätig.
- Status der Läufe prüfen: GitHub → **Actions** (Logs auf `429`, `[FX …] Fallback`,
  „FX-Kurse unvollstaendig", „Zu wenig Daten").
