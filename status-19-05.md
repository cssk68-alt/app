# Status-Bericht 19.05.2026 — Verifikation der Pushes

Geprüft am 19.05.2026, gegen `main` HEAD.

## ✅ Was sauber live ist (9 von 10 Dateien)

| Datei | Größe | SHA | Status |
|---|---:|---|---|
| `sw.js` | 1.386 B | `300e4de4` | ✅ Cache-Bump v5 live |
| `update_weights.py` | 12.882 B | `17efcbc7` | ✅ DE-Endpoint + 3 ID-Fixes + COUNTRY_MAP |
| `update_holdings_sectors.py` | 7.266 B | `21f732a0` | ✅ Holdings/Sektoren-Pipeline neu |
| `data/holdings.json` | 11.607 B | `48df1e7b` | ✅ Top-Holdings 8 ETFs aktuell |
| `data/sectors.json` | 8.051 B | `78687db3` | ✅ Sektor-Splits 8 ETFs aktuell |
| `data/static_meta.json` | 2.278 B | `028263dd` | ✅ ETCs + Allianz statisch |
| `data/geo_weights.json` | 10.748 B | `780d52e4` | ✅ 43 Länder live (USA 32,51 %) |
| `.github/workflows/update_data.yml` | 1.201 B | `bcb07375` | ✅ 2 Scripts + 3 JSONs Commit |
| `änderungen-19-05.md` | 4.811 B | `cf018f2a` | ✅ Changelog dokumentiert |

Workflows „Deploy to GitHub Pages" + „pages build and deployment" haben für beide Commits (`83dced25` und `af520d14`) grün abgeschlossen. Die JSON-Endpoints unter `cssk68-alt.github.io/sparplan/data/*.json` antworten alle mit HTTP 200.

## ⚠ index.html: nach meinem Push überschrieben

Zeitstrahl:

```
23:33  Commit 83dced25  – mein Push: index.html 64.153 B mit Features A/B/D + Geo-Slide
23:50  Commit 777c9d73  – User-Commit: index.html ↓ auf 17.864 B (+94 Zeilen, -1.198 Zeilen)
05:17  Commit af520d14  – mein 2. Push: nur update_weights.py / geo_weights.json / Changelog
```

Der User-Commit `777c9d73` mit Message *„FIX 1 LIVE: Single Source of Truth — Pop-ups laden Länder dynamisch aus geo_weights.json"* hat die index.html komplett ersetzt. Aktueller Stand der Datei:

| Marker | Status |
|---|---|
| Slide 1 (Sparplan-Pie) | vorhanden |
| Slide 2 (Geo-Slide mit D3-Karte) | **entfernt** |
| Slide 3 (Sektoren + Klumpenrisiko) | **nie reingekommen** |
| `clusterCard` (Top-Konzentrationen-Card) | **entfernt** |
| `loadAnalytics`-Loader | **entfernt** |
| `computeOverlap`, `computeClusterRisk`, `renderSectorSlide` | **entfernt** |
| Modal-Overlap-Sektion | **entfernt** |
| 3-Slide-Pfeil-Navigation | **entfernt** |

Konsequenz: Die Pipeline produziert frische Daten in `data/holdings.json` + `data/sectors.json`, aber **das Frontend lädt diese Dateien nicht mehr** — die Daten landen also tot im Repo. Auch die Geo-Slide ist weg, obwohl `data/geo_weights.json` weiter wöchentlich aktualisiert wird.

Title-Bar der aktuellen Version: *„Mein Sparplan - v20260518t2345 FIX1"* — der User hat seine FIX1-Änderung bewusst über meine Version gelegt.

## Empfehlung

Zwei Wege, je nachdem was beabsichtigt war:

**A) Wenn FIX1 wichtiger war, Features A/B/D sollen aber zurück:**
→ Ich rebase Features A/B/D auf die aktuelle 17.864-B-Version (FIX1 bleibt erhalten, A/B/D + Geo-Slide kommen wieder rein). Größerer Aufwand, weil ich nicht weiß was FIX1 inhaltlich genau geändert hat.

**B) Wenn die Features A/B/D + Geo-Slide nie hätten verloren gehen sollen:**
→ Ich stelle die index.html aus Commit `83dced25` wieder her und integriere FIX1 (Single-Source-of-Truth-Pop-ups) on top. Schneller, sauberer.

**C) FIX1 reicht dir, A/B/D nicht mehr nötig:**
→ Dann sollte ich noch `data/holdings.json`, `data/sectors.json`, `data/static_meta.json` und `update_holdings_sectors.py` aus dem Repo entfernen, plus den Workflow zurückbauen — sonst läuft Sonntagnacht ein Script das für Dinge Daten zieht, die niemand mehr nutzt.

Bitte gib mir kurz Bescheid welcher Weg — dann ziehe ich es durch.
