"""
update_weights.py
Laedt Laendergewichtungen direkt von iShares-DE und berechnet die portfolio-
gewichteten Anteile je Land. Aggregiert Laender direkt aus den Holdings-Rows
(kein dedizierter country-Tab im DE-Endpoint vorhanden).

Output: data/geo_weights.json (kompatibel zum Frontend-Schema mit
        land/iso_numeric/flag/pct_gesamt/via; regions-Block bleibt erhalten).
"""
import json
import os
import random
import re
import time
import requests
from datetime import datetime

PORTFOLIO = {
    "SXR8": {"isin": "IE00B5BMR087", "product_id": "253743", "pct": 0.200},
    "CPXJ": {"isin": "IE00B52MJY50", "product_id": "253735", "pct": 0.150},
    "CSKR": {"isin": "IE00B5W4TY14", "product_id": "253733", "pct": 0.026},
    "IJPA": {"isin": "IE00B4L5YX21", "product_id": "251867", "pct": 0.024},
    "WHCS": {"isin": "IE00BJ5JNZ06", "product_id": "308909", "pct": 0.140},
    "AGED": {"isin": "IE00BYZK4669", "product_id": "284218", "pct": 0.050},
    "EIMI": {"isin": "IE00BKM4GZ66", "product_id": "264659", "pct": 0.140},
    "PHAG": {"isin": "JE00B1VS3333", "product_id": None,     "pct": 0.060},
    "PHPT": {"isin": "JE00B1VS2W53", "product_id": None,     "pct": 0.046},
    "COPA": {"isin": "GB00B15KXQ89", "product_id": None,     "pct": 0.044},
    "ALV":  {"isin": "DE0008404005", "product_id": None,     "pct": 0.070},
    "ISF":  {"isin": "IE0005042456", "product_id": "251795", "pct": 0.050},
}

# Physisch hinterlegte Rohstoffe (Silber, Platin, Kupfer) — keine Aktien, keine
# Firmen, keine Länder. Werden den größten Förderländern zugeordnet (USGS Welt-
# anteile), nicht dem ETC-Sitz (WisdomTree Issuer plc, Jersey).
PHYSICAL_COMMODITY_TICKERS = {"PHAG", "PHPT", "COPA"}

# Top-Förderländer pro Metall (USGS Mineral Commodity Summaries).
# Format: [(canonical_country, welt_anteil_pct), ...] — relative Gewichte
# innerhalb des Metalls. Werden auf 100% normalisiert.
PHYSICAL_ATTRIBUTION = {
    "PHAG": [("Mexiko", 24.0), ("China", 14.0)],     # Silber: Top 2 Förderländer
    "PHPT": [("Südafrika", 73.0)],                   # Platin: dominiert Welt
    "COPA": [("Chile", 27.0), ("Peru", 14.0)],       # Kupfer: Top 2 Förderländer
}

EDELMETALL_FALLBACK = {
    "PHAG": {"Mexiko": 24.0, "Peru": 15.0, "China": 13.0, "Russland": 8.0,
             "Chile": 5.0, "Australien": 5.0, "Polen": 5.0, "Bolivien": 5.0,
             "Argentinien": 5.0, "Other": 15.0},
    "PHPT": {"Südafrika": 73.0, "Russland": 11.0, "Simbabwe": 8.0,
             "Kanada": 4.0, "USA": 2.0, "Other": 2.0},
    "COPA": {"Chile": 27.0, "Peru": 10.0, "DRK": 10.0,
             "China": 8.0, "USA": 6.0, "Australien": 5.0,
             "Sambia": 4.0, "Indonesien": 4.0, "Mexiko": 3.0, "Other": 23.0},
}
EINZELPOSITIONEN_FALLBACK = {"ALV": {"Deutschland": 100.0}}

# Bug 3 Fix: Erweiterte COUNTRY_MAP mit Edge-Cases die iShares liefern kann.
# Regel: alle Werte (canonical names) müssen in COUNTRY_META vorhanden sein.
COUNTRY_MAP = {
    # Nordamerika
    "Vereinigte Staaten": "USA", "United States": "USA", "USA": "USA",
    "Canada": "Kanada", "Kanada": "Kanada",
    "Bermuda": "Bermuda",                                 # Steuerdomizel vieler Firmen
    "Cayman Islands": "Cayman Islands",                   # Idem
    # Europa
    "Germany": "Deutschland", "Deutschland": "Deutschland",
    "Vereinigtes Königreich": "UK", "United Kingdom": "UK", "UK": "UK", "Great Britain": "UK",
    "France": "Frankreich", "Frankreich": "Frankreich",
    "Netherlands": "Niederlande", "Niederlande": "Niederlande",
    "Sweden": "Schweden", "Schweden": "Schweden",
    "Switzerland": "Schweiz", "Schweiz": "Schweiz",
    "Denmark": "Dänemark", "Dänemark": "Dänemark",
    "Belgium": "Belgien", "Belgien": "Belgien",
    "Italy": "Italien", "Italien": "Italien",
    "Spain": "Spanien", "Spanien": "Spanien",
    "Greece": "Griechenland", "Griechenland": "Griechenland",
    "Poland": "Polen", "Polen": "Polen",
    "Czech Republic": "Tschechien", "Czechia": "Tschechien", "Tschechien": "Tschechien",
    "Austria": "Österreich", "Österreich": "Österreich",
    "Portugal": "Portugal",
    "Finland": "Finnland", "Finnland": "Finnland",
    "Norway": "Norwegen", "Norwegen": "Norwegen",
    "Hungary": "Ungarn", "Ungarn": "Ungarn",
    "Ireland": "Irland", "Irland": "Irland",
    "Luxembourg": "Luxemburg", "Luxemburg": "Luxemburg",
    # Asien-Pazifik
    "Korea": "Südkorea", "South Korea": "Südkorea", "Südkorea": "Südkorea",
    "Republic of Korea": "Südkorea",
    "Japan": "Japan",
    "China": "China", "Taiwan": "Taiwan",
    "Hong Kong": "Hongkong", "Hongkong": "Hongkong",
    "Singapore": "Singapur", "Singapur": "Singapur",
    "India": "Indien", "Indien": "Indien",
    "Australia": "Australien", "Australien": "Australien",
    "New Zealand": "Neuseeland", "Neuseeland": "Neuseeland",
    "Malaysia": "Malaysia", "Thailand": "Thailand",
    "Indonesia": "Indonesien", "Indonesien": "Indonesien",
    "Philippines": "Philippinen", "Philippinen": "Philippinen",
    "Vietnam": "Vietnam",
    # Emerging Markets / MENA
    "Turkey": "Türkei", "Türkei": "Türkei",
    "Saudi Arabia": "Saudi-Arabien", "Saudi-Arabien": "Saudi-Arabien",
    "United Arab Emirates": "Ver. Arabische Emirate", "Ver. Arabische Emirate": "Ver. Arabische Emirate",
    "Qatar": "Qatar", "Kuwait": "Kuwait", "Israel": "Israel",
    "Egypt": "Ägypten", "Ägypten": "Ägypten",
    "Morocco": "Marokko", "Marokko": "Marokko",
    "Nigeria": "Nigeria",
    "South Africa": "Südafrika", "Südafrika": "Südafrika",
    "Republic of South Africa": "Südafrika",              # iShares-Variante
    # Latam
    "Brazil": "Brasilien", "Brasilien": "Brasilien",
    "Mexico": "Mexiko", "Mexiko": "Mexiko",
    "Argentina": "Argentinien", "Argentinien": "Argentinien",
    "Bolivia": "Bolivien", "Bolivien": "Bolivien",
    "Chile": "Chile", "Peru": "Peru",
    "Colombia": "Kolumbien", "Kolumbien": "Kolumbien",
    # Rohstoff-Länder
    "Russia": "Russland", "Russian Federation": "Russland", "Russland": "Russland",
    "Zambia": "Sambia", "Sambia": "Sambia",
    "Zimbabwe": "Simbabwe", "Simbabwe": "Simbabwe",
    "Congo, Dem. Rep.": "DRK", "DR Congo": "DRK", "DRK": "DRK",
    # Pakistan
    "Pakistan": "Pakistan",
}

# Bug 3 Fix: COUNTRY_META erweitert um alle neuen canonical names.
# Alle COUNTRY_MAP-Werte MÜSSEN hier einen Eintrag haben (validate_country_maps prüft das).
COUNTRY_META = {
    # Nordamerika
    "USA":            {"iso_numeric": 840, "flag": "🇺🇸"},
    "Kanada":         {"iso_numeric": 124, "flag": "🇨🇦"},
    "Bermuda":        {"iso_numeric":  60, "flag": "🇧🇲"},
    "Cayman Islands": {"iso_numeric": 136, "flag": "🇰🇾"},
    # Europa
    "Deutschland":    {"iso_numeric": 276, "flag": "🇩🇪"},
    "UK":             {"iso_numeric": 826, "flag": "🇬🇧"},
    "Frankreich":     {"iso_numeric": 250, "flag": "🇫🇷"},
    "Niederlande":    {"iso_numeric": 528, "flag": "🇳🇱"},
    "Schweden":       {"iso_numeric": 752, "flag": "🇸🇪"},
    "Schweiz":        {"iso_numeric": 756, "flag": "🇨🇭"},
    "Dänemark":       {"iso_numeric": 208, "flag": "🇩🇰"},
    "Belgien":        {"iso_numeric":  56, "flag": "🇧🇪"},
    "Italien":        {"iso_numeric": 380, "flag": "🇮🇹"},
    "Spanien":        {"iso_numeric": 724, "flag": "🇪🇸"},
    "Griechenland":   {"iso_numeric": 300, "flag": "🇬🇷"},
    "Polen":          {"iso_numeric": 616, "flag": "🇵🇱"},
    "Tschechien":     {"iso_numeric": 203, "flag": "🇨🇿"},
    "Österreich":     {"iso_numeric":  40, "flag": "🇦🇹"},
    "Portugal":       {"iso_numeric": 620, "flag": "🇵🇹"},
    "Finnland":       {"iso_numeric": 246, "flag": "🇫🇮"},
    "Norwegen":       {"iso_numeric": 578, "flag": "🇳🇴"},
    "Ungarn":         {"iso_numeric": 348, "flag": "🇭🇺"},
    "Irland":         {"iso_numeric": 372, "flag": "🇮🇪"},
    "Luxemburg":      {"iso_numeric": 442, "flag": "🇱🇺"},
    # Asien-Pazifik
    "Südkorea":       {"iso_numeric": 410, "flag": "🇰🇷"},
    "Japan":          {"iso_numeric": 392, "flag": "🇯🇵"},
    "Taiwan":         {"iso_numeric": 158, "flag": "🇹🇼"},
    "Australien":     {"iso_numeric":  36, "flag": "🇦🇺"},
    "China":          {"iso_numeric": 156, "flag": "🇨🇳"},
    "Hongkong":       {"iso_numeric": 344, "flag": "🇭🇰"},
    "Singapur":       {"iso_numeric": 702, "flag": "🇸🇬"},
    "Indien":         {"iso_numeric": 356, "flag": "🇮🇳"},
    "Neuseeland":     {"iso_numeric": 554, "flag": "🇳🇿"},
    "Malaysia":       {"iso_numeric": 458, "flag": "🇲🇾"},
    "Thailand":       {"iso_numeric": 764, "flag": "🇹🇭"},
    "Indonesien":     {"iso_numeric": 360, "flag": "🇮🇩"},
    "Philippinen":    {"iso_numeric": 608, "flag": "🇵🇭"},
    "Vietnam":        {"iso_numeric": 704, "flag": "🇻🇳"},
    # Emerging / MENA
    "Türkei":         {"iso_numeric": 792, "flag": "🇹🇷"},
    "Saudi-Arabien":  {"iso_numeric": 682, "flag": "🇸🇦"},
    "Ver. Arabische Emirate": {"iso_numeric": 784, "flag": "🇦🇪"},
    "Qatar":          {"iso_numeric": 634, "flag": "🇶🇦"},
    "Kuwait":         {"iso_numeric": 414, "flag": "🇰🇼"},
    "Israel":         {"iso_numeric": 376, "flag": "🇮🇱"},
    "Ägypten":        {"iso_numeric": 818, "flag": "🇪🇬"},
    "Marokko":        {"iso_numeric": 504, "flag": "🇲🇦"},
    "Nigeria":        {"iso_numeric": 566, "flag": "🇳🇬"},
    "Südafrika":      {"iso_numeric": 710, "flag": "🇿🇦"},
    # Latam
    "Brasilien":      {"iso_numeric":  76, "flag": "🇧🇷"},
    "Mexiko":         {"iso_numeric": 484, "flag": "🇲🇽"},
    "Argentinien":    {"iso_numeric":  32, "flag": "🇦🇷"},
    "Bolivien":       {"iso_numeric":  68, "flag": "🇧🇴"},
    "Peru":           {"iso_numeric": 604, "flag": "🇵🇪"},
    "Chile":          {"iso_numeric": 152, "flag": "🇨🇱"},
    "Kolumbien":      {"iso_numeric": 170, "flag": "🇨🇴"},
    # Rohstoff-Länder / Sonstige
    "Russland":       {"iso_numeric": 643, "flag": "🇷🇺"},
    "Sambia":         {"iso_numeric": 894, "flag": "🇿🇲"},
    "Simbabwe":       {"iso_numeric": 716, "flag": "🇿🇼"},
    "DRK":            {"iso_numeric": 180, "flag": "🇨🇩"},
    "Pakistan":       {"iso_numeric": 586, "flag": "🇵🇰"},
}

# Bug 1 + 3 Fix: REGION_MAP vollständig – alle COUNTRY_META-Länder zugeordnet.
# Cross-Check wird durch validate_country_maps() erzwungen.
REGION_MAP = {
    "Nordamerika":   ["USA", "Kanada"],
    "Europa":        ["Deutschland", "UK", "Schweiz", "Frankreich", "Niederlande",
                      "Schweden", "Dänemark", "Belgien", "Italien", "Spanien",
                      "Griechenland", "Polen", "Tschechien", "Österreich", "Portugal",
                      "Finnland", "Norwegen", "Ungarn", "Irland", "Luxemburg"],
    "Asien-Pazifik": ["Japan", "Südkorea", "Taiwan", "Hongkong", "China", "Singapur",
                      "Indien", "Australien", "Neuseeland", "Malaysia", "Thailand",
                      "Indonesien", "Philippinen", "Vietnam"],
    "Emerging Mkts": ["Brasilien", "Argentinien", "Bolivien", "Peru", "Chile", "Mexiko",
                      "Kolumbien", "Türkei", "Saudi-Arabien", "Ver. Arabische Emirate",
                      "Qatar", "Kuwait", "Israel", "Russland", "Südafrika",
                      "Ägypten", "Marokko", "Nigeria", "Pakistan",
                      "Simbabwe", "DRK", "Sambia"],
    "Offshore/Sonstige":  ["Bermuda", "Cayman Islands"],
}

ENDPOINT_TMPL = (
    "https://www.ishares.com/de/privatanleger/de/produkte/{pid}/fund/"
    "1478358465952.ajax?fileType=json&tab=all"
)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Chrome/120.0 Mobile",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
    "Referer": "https://www.ishares.com/",
}
ISIN_RX = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")
ASSET_CLASS_SKIP = {"geldmarkt", "cash und/oder derivate", "cash", "futures", "futures sell"}
NAME_SKIP = ("CASH", "FUTURES", "DERIVATIVE", "MARGIN")


def validate_country_maps():
    """Bug 3 Fix: Crash-früh-Validierung – verhindert stille Daten-Fragmentierung.
    Prüft zwei Invarianten:
      1. Alle COUNTRY_MAP-Werte (canonical names) sind in COUNTRY_META definiert.
      2. Alle COUNTRY_META-Länder sind in genau einer Region im REGION_MAP gelistet.
    Bei Verletzung: SystemExit mit Details – nie still fehlschlagen.
    """
    all_in_regions = set(c for countries in REGION_MAP.values() for c in countries)
    errors = []

    # Invariante 1: COUNTRY_MAP → COUNTRY_META
    for src, canonical in COUNTRY_MAP.items():
        if canonical not in COUNTRY_META:
            errors.append(f"COUNTRY_MAP['{src}'] → '{canonical}' fehlt in COUNTRY_META")

    # Invariante 2: COUNTRY_META → REGION_MAP
    for country in COUNTRY_META:
        if country not in all_in_regions:
            errors.append(f"COUNTRY_META['{country}'] hat keine Region in REGION_MAP")

    # Invariante 3: REGION_MAP → COUNTRY_META (umgekehrt, entdeckt Tippfehler)
    for region, countries in REGION_MAP.items():
        for country in countries:
            if country not in COUNTRY_META:
                errors.append(f"REGION_MAP['{region}'] enthält '{country}' – nicht in COUNTRY_META")

    if errors:
        raise SystemExit(
            "FEHLER: COUNTRY_MAP/META/REGION_MAP Inkonsistenz – bitte beheben:\n"
            + "\n".join(f"  ✗ {e}" for e in errors)
        )
    print(f"✓ validate_country_maps: {len(COUNTRY_META)} Länder, {len(REGION_MAP)} Regionen – OK")


def canon(name):
    return COUNTRY_MAP.get(name, name)

def fetch_country_weights(product_id, ticker, max_retries=3):
    """Holt iShares-Holdings mit Exponential-Backoff bei HTTP 429."""
    url = ENDPOINT_TMPL.format(pid=product_id)
    rows = None
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=20)
            if resp.status_code == 429:
                ra = resp.headers.get("Retry-After")
                wait = float(ra) if (ra and ra.isdigit()) else (2 ** attempt) + random.random()
                print(f"  [{ticker}] HTTP 429 - waiting {wait:.1f}s before retry ({attempt+1}/{max_retries})", flush=True)
                time.sleep(wait); continue
            if resp.status_code != 200:
                print(f"  [{ticker}] HTTP {resp.status_code}")
                return None
            data = json.loads(resp.content.decode("utf-8-sig"))
            rows = data.get("aaData", [])
            break
        except (requests.RequestException, json.JSONDecodeError) as e:
            wait = (2 ** attempt) + random.random()
            print(f"  [{ticker}] Fehler ({e.__class__.__name__}) - retry in {wait:.1f}s ({attempt+1}/{max_retries})", flush=True)
            if attempt < max_retries - 1:
                time.sleep(wait); continue
            print(f"  [{ticker}] Aufgegeben: {e}"); return None
    if rows is None:
        print(f"  [{ticker}] {max_retries} 429-Retries erschoepft - skip", flush=True)
        return None
    if not rows:
        return None
    try:
        country_sum = {}
        for row in rows:
            if not isinstance(row, list) or len(row) < 6: continue
            name = str(row[1]).strip() if len(row) > 1 else ""
            if not name: continue
            asset_class = ""
            for i in (3, 4):
                if i < len(row) and isinstance(row[i], str):
                    asset_class = row[i].strip().lower(); break
            if asset_class in ASSET_CLASS_SKIP: continue
            if any(p in name.upper() for p in NAME_SKIP): continue
            dicts = [v for v in row if isinstance(v, dict) and "raw" in v]
            if len(dicts) < 2: continue
            try: weight = float(dicts[1]["raw"])
            except (TypeError, ValueError): continue
            if weight <= 0 or weight > 100: continue
            country = None
            for i in range(9, min(len(row), 13)):
                v = row[i]
                if isinstance(v, str) and len(v) > 2 and "/" not in v:
                    if v in ("-", "USD", "EUR", "GBP", "JPY", "CHF", "HKD"): continue
                    if ISIN_RX.match(v): continue
                    country = v; break
            if not country: continue
            country = canon(country)
            country_sum[country] = country_sum.get(country, 0) + weight
        if not country_sum: return None
        print(f"  [{ticker}] OK - {len(country_sum)} Laender")
        return country_sum
    except (KeyError, ValueError, TypeError) as e:
        print(f"  [{ticker}] Parse-Fehler: {e}")
        return None

def calculate_portfolio_weights():
    global_weights = {}
    # Physische Rohstoffe: pro Land aufdröseln (statt eines einzigen Region-Topfs).
    # {country: {"pct": float, "via": [tickers]}}
    physical_by_country = {}
    for ticker, config in PORTFOLIO.items():
        portfolio_pct = config["pct"]
        if ticker in PHYSICAL_COMMODITY_TICKERS:
            # Auf Top-Förderländer (USGS) proportional zum Welt-Anteil verteilen.
            attribution = PHYSICAL_ATTRIBUTION.get(ticker, [])
            total_share = sum(s for _, s in attribution)
            for country, share in attribution:
                country_pct = portfolio_pct * (share / total_share) * 100
                if country not in physical_by_country:
                    physical_by_country[country] = {"pct": 0.0, "via": []}
                physical_by_country[country]["pct"] += country_pct
                physical_by_country[country]["via"].append(ticker)
            print(f"  [{ticker}] Physisch → {', '.join(c for c, _ in attribution)}")
            continue
        country_data = None
        if config.get("product_id"):
            print(f"Lade {ticker}...")
            country_data = fetch_country_weights(config["product_id"], ticker)
            time.sleep(1.5)
        if country_data is None:
            if ticker in EINZELPOSITIONEN_FALLBACK:
                country_data = EINZELPOSITIONEN_FALLBACK[ticker]
                print(f"  [{ticker}] Fallback")
            else: continue
        total_pct = sum(v for v in country_data.values() if v > 0)
        for country, etf_pct in country_data.items():
            if country.lower() in ("other", "sonstige", "-", ""): continue
            country = canon(country)
            normalized = (etf_pct / total_pct) * 100 if total_pct > 0 else etf_pct
            weighted   = (normalized / 100) * portfolio_pct * 100
            if country not in global_weights:
                global_weights[country] = {"pct_gesamt": 0.0, "via": []}
            global_weights[country]["pct_gesamt"] += weighted
            if ticker not in global_weights[country]["via"]:
                global_weights[country]["via"].append(ticker)

    # Merge-Regel: für jedes Förderland, vergleiche Aktien-Anteil vs Metall-Anteil.
    # Größerer Topf gewinnt — der kleinere wird absorbiert.
    physical_countries = set()  # Länder die zu Phys. Rohstoffe wandern
    for country, phys in physical_by_country.items():
        existing = global_weights.get(country, {"pct_gesamt": 0.0, "via": []})
        if existing["pct_gesamt"] > phys["pct"]:
            # Aktien-Region gewinnt → Metall-Anteil drauf, Land bleibt in alter Region
            global_weights.setdefault(country, {"pct_gesamt": 0.0, "via": []})
            global_weights[country]["pct_gesamt"] += phys["pct"]
            for t in phys["via"]:
                if t not in global_weights[country]["via"]:
                    global_weights[country]["via"].append(t)
        else:
            # Metall gewinnt → Aktien-Anteil ins Metall absorbieren, Land wandert
            absorbed_pct = existing["pct_gesamt"]
            absorbed_via = existing["via"]
            global_weights.pop(country, None)
            physical_by_country[country]["pct"] += absorbed_pct
            for t in absorbed_via:
                if t not in physical_by_country[country]["via"]:
                    physical_by_country[country]["via"].append(t)
            physical_countries.add(country)

    today = datetime.now().strftime("%Y-%m-%d")
    output = []
    for c, d in global_weights.items():
        if d["pct_gesamt"] < 0.05: continue
        meta = COUNTRY_META.get(c, {})
        output.append({
            "land": c, "iso_numeric": meta.get("iso_numeric"),
            "flag": meta.get("flag", "🏳"),
            "pct_gesamt": round(d["pct_gesamt"], 2),
            "via": d["via"], "last_updated": today,
        })
    # Phys.-Rohstoffe-Länder dazu (sortiert mit eigener Flag-Markierung im via)
    for c in physical_countries:
        d = physical_by_country[c]
        meta = COUNTRY_META.get(c, {})
        output.append({
            "land": c, "iso_numeric": meta.get("iso_numeric"),
            "flag": meta.get("flag", "🏳"),
            "pct_gesamt": round(d["pct"], 2),
            "via": d["via"], "last_updated": today,
        })
    output.sort(key=lambda x: x["pct_gesamt"], reverse=True)
    return output, physical_countries


def load_existing(path):
    try: return json.load(open(path, "r", encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError): return {}


if __name__ == "__main__":
    OUTPUT = "data/geo_weights.json"
    os.makedirs("data", exist_ok=True)
    print(f"=== Geo-Update gestartet ({datetime.now():%Y-%m-%d %H:%M}) ===")

    # Bug 3 Fix: Validierung vor jeder Ausführung – crash bei Inkonsistenz
    validate_country_maps()

    existing = load_existing(OUTPUT)
    new_weights, physical_countries = calculate_portfolio_weights()
    if not new_weights:
        print("WARNUNG: Keine Daten - behalte bestehende JSON.")
    else:
        # Wegen Merge-Regel können Förderländer dynamisch zu Phys. Rohstoffe wandern.
        # Damit regionOf() im Frontend sie nicht doppelt einer Aktien-Region zuordnet,
        # bauen wir per-Region-länder-Listen ohne die gewanderten Länder.
        regions_out = []
        for region_name, country_list in REGION_MAP.items():
            filtered_countries = [c for c in country_list if c not in physical_countries]
            total = sum(c["pct_gesamt"] for c in new_weights if c["land"] in filtered_countries)
            actual_countries = [c["land"] for c in new_weights if c["land"] in filtered_countries]
            regions_out.append({
                "region": region_name,
                "pct_gesamt": round(total, 2),
                "länder": filtered_countries,
                "aktuelle_länder": actual_countries,
            })
        # Physische Rohstoffe: Länder die gewonnen haben (Metall > Aktien)
        phys_countries_list = sorted(
            [c["land"] for c in new_weights if c["land"] in physical_countries],
            key=lambda land: next((c["pct_gesamt"] for c in new_weights if c["land"] == land), 0),
            reverse=True,
        )
        phys_pct_total = sum(c["pct_gesamt"] for c in new_weights if c["land"] in physical_countries)
        if phys_countries_list:
            regions_out.append({
                "region": "Physische Rohstoffe",
                "pct_gesamt": round(phys_pct_total, 2),
                "länder": phys_countries_list,
                "aktuelle_länder": phys_countries_list,
            })
        # Cash-Reserve = Differenz zu 100%
        country_sum = sum(c["pct_gesamt"] for c in new_weights)
        regions_out.append({
            "region": "ETF-Cash & Reserven",
            "pct_gesamt": round(max(0, 100 - country_sum), 2),
            "länder": [],
            "aktuelle_länder": [],
        })

        result = dict(existing) if existing else {}
        result["_meta"] = {
            "last_updated": datetime.now().strftime("%Y-%m-%d"),
            "total_positions": len(PORTFOLIO),
            "total_countries": len(new_weights),
            "source": "iShares-DE AJAX tab=all (Laender aus Holdings aggregiert + COUNTRY_MAP konsolidiert)",
            "note": "pct_gesamt = Anteil am Portfolio. EUR = currentTotal * pct_gesamt / 100",
        }
        result["countries"] = new_weights
        result["regions"] = regions_out
        with open(OUTPUT, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"=== Fertig: {len(new_weights)} Laender, {len(regions_out)} Regionen ===")
