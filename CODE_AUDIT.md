# Code-Audit: Sparplan-PWA (ETF-Portfolio-Tracker)

Stand der Analyse: 2026-06-02
Geprüfte Dateien: index.html (2316 Z.), update_performance.py, update_weights.py,
update_holdings_sectors.py, .github/workflows/{update_data,deploy}.yml, sw.js
Hinweis: Reine Analyse. Vier Punkte wurden auf Wunsch direkt umgesetzt (siehe
Status-Spalte), der Rest ist nur dokumentiert.

## Architektur-Kurzbeschreibung
- Statische PWA auf GitHub Pages. Frontend = index.html (Daten + Logik inline).
- 3 Python-Updater laufen via GitHub Actions, committen JSON nach /data/, was
  Pages neu deployt.
- Zyklen: Performance intraday (Mo–Fr, Cron '7,37 7-21 * * 1-5'),
  Geo/Holdings/Sektoren wöchentlich (Cron '0 2 * * 0').
- Externe Quellen: Yahoo Finance, Stooq, AlphaVantage (Kurse/FX), iShares-DE-AJAX
  (Holdings/Länder).

## Status-Legende
- ✅ ERLEDIGT – in diesem Durchgang gefixt
- ➖ BEWUSST GELASSEN – nach Absprache nicht geändert
- ⬜ OFFEN – nur dokumentiert, nicht angefasst

---

## A. Bugs & Logikfehler

| # | Status | Datei / Zeile | Fehler | Ursache | Lösungsvorschlag / Umsetzung |
|---|--------|---------------|--------|---------|------------------------------|
| A1 | ⬜ OFFEN | update_performance.py (Tagesreturn-Schleife) | Portfolio-Tagesrendite wird bei fehlendem Ticker unterschätzt. `wsum` wird direkt angehängt, **nicht** durch `used` (Summe der tatsächlich vorhandenen Gewichte) geteilt. | Funktioniert nur exakt, solange an JEDEM Tag alle Gewichte = 100 ergeben. Fehlt ein Ticker an einem Tag, bleibt `used < 100` und die Rendite wird gegen 0 verzerrt statt renormalisiert. | An Tagen mit `used > 0` durch das genutzte Gewicht normieren (`wsum * 100 / used`). |
| A2 | ⬜ OFFEN | update_performance.py 26, `MIN_SUCCESS_TICKERS` | „Strikt 12/12": ein einzelner fehlgeschlagener Ticker friert das gesamte Performance-Update ein. | `MIN_SUCCESS_TICKERS = 12` bei exakt 12 Tickern → alles-oder-nichts. Ein illiquider Ticker (CSKR/IJPA) blockiert alle anderen. | Schwelle entkoppeln (z. B. ≥10/12) und fehlende Ticker per `forward_fill` weiterführen, statt den ganzen Lauf zu verwerfen. Sonst als Designentscheidung dokumentieren. |
| A3 | ⬜ OFFEN | index.html GROUPS `details` vs. Modal-Render vs. data/holdings.json | Zwei Wahrheiten für Holdings: Modal zeigt hardcodierte Holdings (z. B. „Nvidia 8,2 %"), Sektor-/Risiko-/Overlap-Analyse nutzt live `holdings.json`. | Inline-Beispiel-Holdings wurden nie an den Live-Pfad angebunden. | Modal-Holdings aus `holdings.json` (`top_holdings`) speisen; `details` nur als Fallback. |
| A4 | ⬜ OFFEN | index.html Footer („Stand 09. Mai 2026"), Modal („Kurs (09.05)") | Hardcodierte Datums-/Kursstände driften gegen Live-Daten; Baseline ist 18. Mai. | Statische Strings ohne Bezug zu `_meta.last_updated`. | Datum dynamisch aus den JSON-`last_updated`-Feldern ziehen. |
| A5 | ✅ ERLEDIGT | update_performance.py | `weekly`-Block wurde berechnet und in performance.json geschrieben, im Frontend aber nie gelesen (tote Daten). | Backend-Feature, im Frontend durch „Delta vs. MSCI"/„Top-Bucket" ersetzt. | **`weekly`-Dict + `calc_week_return()` entfernt.** Frontend-UI unberührt (nutzt nur `portfolio`/`msci_world`/`ticker_returns`). |
| A6 | ✅ ERLEDIGT | update_performance.py (`calc_week_return`) | Wochenrendite als arithmetische Differenz kumulativer %-Werte statt Verkettung. | Differenz von Prozentwerten ≠ Periodenrendite. | Mit A5 zusammen **entfernt** (war ohnehin ungenutzt). |
| A7 | ➖ BEWUSST GELASSEN | update_weights.py (Cash-/Länder-Normierung) | „Other"/„Sonstige"-Anteil eines ETF geht in den Nenner (`total_pct`) ein, wird aber keinem Land zugeordnet → stiller Schwund, Regionssummen < Portfolioanteil. | iShares liefert „Other" als opaken Restposten **ohne Länderaufschlüsselung**. | Eine korrekte Aufteilung auf die richtigen Länder ist mangels Quelldaten nicht möglich → auf Absprache unverändert gelassen. Optional behebbar, indem man „Other" als eigenen sichtbaren Eimer ausweist (keine erfundene Länderzuordnung). |
| A8 | ⬜ OFFEN | update_performance.py (`write_frozen`) | Bei reinem MSCI-Ausfall zeigt `tickers_ok` „12/12 ok", obwohl der Chart eingefroren ist. | Kennzahl ignoriert MSCI als 13. Quelle. | MSCI-Ausfall in `tickers_ok`/Status mitzählen oder separat ausweisen. (Icon warnt korrekt, nur die Zahl ist inkonsistent.) |

---

## B. Externe Daten / Asynchronität / Fehlerbehandlung

| # | Status | Datei / Zeile | Fehler | Ursache | Lösungsvorschlag / Umsetzung |
|---|--------|---------------|--------|---------|------------------------------|
| B1 | ⬜ OFFEN | sw.js (Fetch-Handler); index.html (Fetches mit `?t=`) | Service-Worker-Daten-Cache faktisch tot: Offline-Fallback für `/data/*` greift nie. | Fetches hängen `?t=Date.now()` an (+ teils `cache:'no-store'`). SW cached unter Unique-URL; `caches.match` ohne `ignoreSearch:true` sucht beim nächsten Timestamp → immer Miss. Doppeltes Busting. | `caches.match(request, {ignoreSearch:true})` nutzen ODER `?t=`-Busting weglassen und allein auf Network-First + `no-store` setzen. |
| B3 | ✅ ERLEDIGT | update_performance.py (FX-Abruf + `fetch_fx_erapi`) | FX-Notnagel verzerrte rückwirkend den EUR-Kurs: ein einzelner Spot-Kurs wurde auf die Baseline datiert und per `forward_fill` über die **gesamte Historie** gelegt → alle vergangenen EUR-Werte änderten sich run-to-run und die FX-Komponente verschwand. | Spot-Quelle (`open.er-api`) liefert nur den aktuellen Kurs; keine persistierte FX-Historie. | **Behoben:** echte FX-Tageshistorie wird jetzt in `_meta.fx_history` persistiert; neues `_merge_fx()` führt frischen Abruf mit der Historie zusammen (frische Tage haben Vorrang, alte Tage behalten ihren echten Kurs). Der er-api-Spot ist auf **heute** statt Baseline datiert → füllt nur noch den neuesten Tag. Kaltstart-Notnagel (alter Snapshot) bleibt als letzte Reserve. |
| B2 | ⬜ OFFEN | index.html GROUPS / update_performance.py PORTFOLIO_TICKERS / update_weights.py PORTFOLIO | Portfolio-Gewichte an 3 Stellen dupliziert (aktuell konsistent). | Drei unabhängige Quellen ohne gemeinsame Definition. | Single Source of Truth (z. B. data/portfolio.json) oder CI-Konsistenzcheck der drei Listen. |
| B4 | ⬜ OFFEN | .github/workflows/deploy.yml | Deploy-Workflow triggert auch auf `pull_request`; `actions/deploy-pages` schlägt auf PRs i. d. R. fehl. | Pages deployt nur vom Default-Branch. | `pull_request`-Trigger entfernen oder Deploy auf `github.ref == 'refs/heads/main'` einschränken. |
| B5 | ⬜ OFFEN | .github/workflows/update_data.yml | Performance-Step hat keine Schedule-Bedingung → läuft auch im Sonntags-Geo-Cron mit. | Bedingung nur an Geo/Holdings. | Harmlos (Extra-Lauf); für Klarheit ggf. analog bedingen. |
| B6 | ✅ POSITIV | index.html (`loadAnalytics`) | Single-Flight-Promise mit Cache + Error-Recovery sauber gelöst; Geo/Perf-Fehlerpfade behalten letzten guten Stand. | — | Kein Handlungsbedarf; als Referenzmuster nutzen. |

---

## C. Redundanz / „komische" Stellen / KI-Artefakte

| # | Status | Datei / Zeile | Befund | Lösungsvorschlag / Umsetzung |
|---|--------|---------------|--------|------------------------------|
| C1 | ⬜ OFFEN | update_performance.py (`first_available`) | Funktion definiert, nie aufgerufen. Toter Code. | Entfernen. |
| C2 | ⬜ OFFEN | update_weights.py (`EDELMETALL_FALLBACK`) | Definiert, nie genutzt (Attribution läuft über `PHYSICAL_ATTRIBUTION`). | Entfernen oder als echten Fallback verdrahten. |
| C3 | ✅ ERLEDIGT | index.html (`initSectors` / `_setSlide`) | `renderSectorSlide()` lief beim ersten Besuch von Slide 1 doppelt. | **Behoben:** Render-Aufruf aus `initSectors()` entfernt; `_setSlide()` rendert genau einmal. |
| C4 | ⬜ OFFEN | index.html (meta no-store) + sw.js + `?t=`/`no-store` | Vier überlappende Cache-Steuerungen. | Auf SW Network-First + ein Busting-Mechanismus reduzieren (siehe B1). |
| C5 | ⬜ OFFEN | index.html (Geo-Tabelle) | `c.land`/`c.via` via innerHTML ohne `safeText()` — inkonsistent zur sonstigen Disziplin. | Niedriges Risiko (kontrollierte Quelle); zur Konsistenz `safeText()` anwenden. |
| C6 | ⬜ OFFEN | Repo-Root | Viele „Bug N Fix"-Kommentare + datierte Status-/Änderungs-MD-Dateien. | Indikator iterativen KI-Patchens; Doku in /docs verschieben, Kommentare entschlacken. |

---

## D. In diesem Durchgang umgesetzt (Zusammenfassung)
1. **B3 – FX-Verzerrung behoben:** persistierte `fx_history` + `_merge_fx()`, er-api-Spot auf heute datiert. Keine rückwirkende EUR-Verzerrung mehr.
2. **A5/A6 – `weekly` entfernt:** ungenutzter `weekly`-Block und `calc_week_return()` raus.
3. **C3 – Sektor-Render-Dedupe:** `renderSectorSlide()` läuft beim ersten Slide-Besuch nur noch einmal.
4. **A7 – Geo „Other":** geprüft, mangels Quelldaten nicht sauber aufteilbar → bewusst unverändert.

## E. Priorisierte Resterledigung (offen)
1. B1 (SW-Daten-Cache / Offline-Pfad reparieren).
2. A1 (Tagesrendite renormalisieren) + A2 (12/12-Politik entschärfen).
3. A3 + A4 (eine Holdings-/Datums-Quelle statt hardcodierter Werte).
4. B2 (Gewichte zentralisieren, CI-Konsistenzcheck).
5. A8, B4, B5, C1, C2, C4–C6 (Aufräum-/Härtungsarbeiten).
