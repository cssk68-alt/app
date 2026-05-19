# Änderungen 19.05.2026

Zusammenfassung der Arbeit aus der Cowork-Session vom 18./19. Mai 2026.

## TL;DR

Drei neue Analyse-Features ins Sparplan-Dashboard eingebaut und zwei Bugs in der bestehenden Datenpipeline behoben. Alle Werte (Holdings, Sektoren, Länder) werden jetzt wöchentlich automatisch von iShares-DE gezogen — kein Hardcoding mehr.

## Neue Features

### Feature D — Klumpenrisiko-Card (Slide 1)
Zeigt oben auf der Sparplan-Slide die drei größten effektiven Einzelpositionen über alle ETFs hinweg. Beispiel: wenn Samsung in CSKR mit 27% und in EIMI mit 6% läuft, zeigt die Card die kombinierte Gewichtung im Sparplan. Klick auf die Card → öffnet die neue Sektor-Slide mit der vollen Detailliste.

### Feature A — Overlap-Analyse (Modal)
Wenn man auf eine Themengruppe tippt, wird im Modal unten eine neue Sektion „Überschneidungen mit anderen ETFs" gezeigt. Berechnet paarweise den Anteil identischer Holdings (per ISIN-Match, `Σ min(w_a, w_b)`). Beispiel: CSKR ↔ EIMI 11,4 %.

### Feature B — Echte Sektor-Verteilung (neue Slide 3)
Eigene Slide mit der echten GICS-Sektor-Exposure über alle ETFs hinweg, gewichtet nach Portfolio-Anteilen. Plus eine ausführliche Klumpenrisiko-Detailliste (alle Aktien ab 0,3 % effektiver Sparplan-Gewichtung). Pfeil-Navigation jetzt 3-stufig: Sparplan → Sektoren → Geo.

## Bug-Fixes

### Fix 1 — drei falsche iShares-Product-IDs in `update_weights.py`
Die alten IDs lieferten falsche ETFs zurück:

| Ticker | Alt (falsch) | Neu (korrekt) | Was die alte ID lieferte |
|---|---|---|---|
| CSKR | 253742 | **253733** | japanische Aktien statt Korea |
| IJPA | 251929 | **251867** | europäische Aktien statt Japan IMI |
| WHCS | 251882 | **308909** | 1332 Holdings (NVIDIA top) statt 115 Health-Care-Aktien |

→ Dadurch waren auch die Länder-Anteile in der Geo-Slide schon vorher falsch.

### Fix 2 — `update_weights.py` auf DE-Endpoint umgestellt
Der alte UK-AJAX-Endpoint (`/uk/individual/en/.../1467271812596.ajax`) liefert seit einiger Zeit HTTP 404. Pipeline läuft jetzt gegen `de/privatanleger/de/.../1478358465952.ajax?fileType=json&tab=all` und aggregiert die Länder direkt aus den Holdings-Rows (`aaData`-Format mit Country in Spalte 10/11). Zusätzlich `COUNTRY_MAP` eingebaut, die EN/DE-Varianten (z. B. „Germany" / „Deutschland", „Mexico" / „Mexiko") konsolidiert — sonst hätte ein Land doppelt im Output gestanden.

## Neue Auto-Update-Pipeline

`update_holdings_sectors.py` — analog zu `update_weights.py`, holt einmal pro Sonntag um 02:00 UTC für alle 8 iShares-ETFs:

- Top-10 Holdings (Name, ISIN, Gewichtung) → `data/holdings.json`
- Aggregierte Sektor-Splits (über alle Holdings, nicht nur Top-10) → `data/sectors.json`

Beide Files werden vom Workflow `update_data.yml` mitgecommittet. Verschiebt iShares ein Holding-Gewicht von 8,2 % auf 7,9 %, zieht das Frontend das beim nächsten Reload automatisch.

`data/static_meta.json` — einmalige Datei für Dinge die sich praktisch nie ändern: ETC-Underlyings (PHAG/PHPT physisch, COPA Futures front-month) und Sektor-Zuordnung der Allianz-Aktie. Manuell editierbar.

## Architektur-Prinzip

Python liefert nur Roh-Daten von iShares. Alle abgeleiteten Werte (Overlap-Paarungen, Klumpenrisiko-Aggregation, Portfolio-Sektor-Gewichtung) werden **live im Frontend** aus `data/*.json` + aktuellem `currentTotal` berechnet. Vorteile:

- Ändert man den Sparplan-Betrag in der App, sind alle Risiko-Anzeigen sofort neu
- Keine Re-Compute-Logik im Python-Script nötig
- Bei Portfolio-Anpassungen (Position-Gewichte) muss nur das Frontend angepasst werden

## Geänderte / neue Dateien

- `index.html` — 3-Slide-Nav, Cluster-Card, Modal-Overlap-Sektion, Sektor-Slide, Analytics-Loader (lazy)
- `sw.js` — Cache-Bump auf v5, neue data-Files im Pre-Cache
- `update_weights.py` — DE-Endpoint, 3 ID-Fixes, COUNTRY_MAP, ISO/Flag-Lookup
- `update_holdings_sectors.py` (neu) — Holdings + Sektoren Pipeline
- `data/holdings.json` (neu) — Top-10 Holdings je ETF, auto-aktualisiert
- `data/sectors.json` (neu) — Sektor-Splits je ETF, auto-aktualisiert
- `data/static_meta.json` (neu) — ETCs + Aktie (statisch)
- `.github/workflows/update_data.yml` — zweites Script + 2 weitere JSONs committen

## Was bewusst nicht gemacht wurde

- **Feature C (Länder-Heatmap pro Einzelland):** Die bestehende Geo-Slide aggregiert nach 6 Custom-Regionen. Eine Choropleth pro Einzelland würde die Karte USA-dominiert machen (32 % vs. alle anderen < 11 %). Kann später als Toggle nachgereicht werden.
- **iShares-Product-ID-Resolver:** Die Product-IDs sind weiterhin in den Python-Scripts hardcoded, weil iShares keine öffentliche ISIN→ID-Such-API hat. Bei Drift einfach Ticker auf ishares.com suchen, ID aus URL nehmen, in `PORTFOLIO_ETFS` ersetzen.
