# Status-Bericht 19.05.2026 — Verifikation der Pushes

Stand: 19.05.2026, 07:30 — **alles live und sauber**.

## ✅ Vollständig live (10 / 10 Dateien)

| Datei | Größe | SHA | Status |
|---|---:|---|---|
| `index.html` | 64.153 B | `083ba9b9` | ✅ volle Version mit Features A/B/D + Geo-Slide |
| `sw.js` | 1.384 B | `5c513a87` | ✅ Cache-Bump v6 |
| `update_weights.py` | 12.882 B | `17efcbc7` | ✅ DE-Endpoint + 3 ID-Fixes + COUNTRY_MAP |
| `update_holdings_sectors.py` | 7.266 B | `21f732a0` | ✅ Holdings/Sektoren-Pipeline neu |
| `data/holdings.json` | 11.607 B | `48df1e7b` | ✅ Top-Holdings 8 ETFs aktuell |
| `data/sectors.json` | 8.051 B | `78687db3` | ✅ Sektor-Splits 8 ETFs aktuell |
| `data/static_meta.json` | 2.278 B | `028263dd` | ✅ ETCs + Allianz statisch |
| `data/geo_weights.json` | 10.748 B | `780d52e4` | ✅ 43 Länder live (USA 32,51 %) |
| `.github/workflows/update_data.yml` | 1.201 B | `bcb07375` | ✅ 2 Scripts + 3 JSONs Commit |
| `änderungen-19-05.md` | 4.811 B | `cf018f2a` | ✅ Changelog dokumentiert |

GitHub Pages liefert die volle 64.153-B-Version mit allen Markern (`slide-sectors`, `clusterCard`, `loadAnalytics`, `computeOverlap`, `renderSectorSlide`, `geoSvg` — alle vorhanden). Alle vier `data/*.json` antworten unter `cssk68-alt.github.io/sparplan/data/*` mit HTTP 200.

## Was zwischendurch passiert ist

Commit `777c9d73` *("FIX 1 LIVE: Single Source of Truth")* war kein User-Commit, sondern ein Artifact aus einem Cowork-Push, der wegen Token-Limit eine gekürzte index.html (17.864 B) auf `main` geschoben hatte. Features A/B/D + Geo-Slide waren dadurch temporär weg.

Behoben mit Commit `75a05a0b`: index.html aus Commit `83dced25` (volle 64.153-B-Version) restauriert. sw.js auf v6 gebumpt, damit Service-Worker bei Stammnutzern die neue Version lädt statt aus dem alten Cache zu servieren.

## Was Sonntag automatisch passiert

Workflow `update_data.yml` triggert um 02:00 UTC:
1. `update_weights.py` → frische `data/geo_weights.json` (Länder)
2. `update_holdings_sectors.py` → frische `data/holdings.json` + `data/sectors.json`
3. Commit + Push → triggert auto-deploy auf GitHub Pages

Verschiebt iShares im Hintergrund ein Holding-Gewicht von 8,2 % auf 7,9 %, sieht der nächste Reload der Webapp den neuen Wert. Kein Hardcoding mehr.

## Commits dieser Session

```
75a05a0b  Restore index.html with full A/B/D analytics + Geo-Slide
a6667a7b  Status-Bericht 19.05: Verifikation aller Pushes
af520d14  Geo-pipeline fix + Changelog 19.05
83dced25  Add A/B/D analytics features + fix iShares product IDs
```

Alle Pages-Builds für die Commits sind grün durchgelaufen.
