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

COUNTRY_MAP = {
    "Vereinigte Staaten": "USA", "United States": "USA", "USA": "USA",
    "Germany": "Deutschland", "Deutschland": "Deutschland",
    "Vereinigtes Königreich": "UK", "United Kingdom": "UK", "UK": "UK",
    "Korea": "Südkorea", "South Korea": "Südkorea", "Südkorea": "Südkorea", "Republic of Korea": "Südkorea",
    "South Africa": "Südafrika", "Südafrika": "Südafrika",
    "Mexico": "Mexiko", "Mexiko": "Mexiko",
    "Russia": "Russland", "Russian Federation": "Russland", "Russland": "Russland",
    "Brazil": "Brasilien", "Brasilien": "Brasilien",
    "Canada": "Kanada", "Kanada": "Kanada",
    "Australia": "Australien", "Australien": "Australien",
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
    "Turkey": "Türkei", "Türkei": "Türkei",
    "Indonesia": "Indonesien", "Indonesien": "Indonesien",
    "Philippines": "Philippinen", "Philippinen": "Philippinen",
    "Saudi Arabia": "Saudi-Arabien", "Saudi-Arabien": "Saudi-Arabien",
    "United Arab Emirates": "Ver. Arabische Emirate", "Ver. Arabische Emirate": "Ver. Arabische Emirate",
    "Argentina": "Argentinien", "Argentinien": "Argentinien",
    "Bolivia": "Bolivien", "Bolivien": "Bolivien",
    "Zambia": "Sambia", "Sambia": "Sambia",
    "Zimbabwe": "Simbabwe", "Simbabwe": "Simbabwe",
    "Congo, Dem. Rep.": "DRK", "DR Congo": "DRK", "DRK": "DRK",
    "New Zealand": "Neuseeland", "Neuseeland": "Neuseeland",
    "Hong Kong": "Hongkong", "Hongkong": "Hongkong",
    "Singapore": "Singapur", "Singapur": "Singapur",
    "India": "Indien", "Indien": "Indien",
    "China": "China", "Taiwan": "Taiwan", "Japan": "Japan",
    "Israel": "Israel", "Chile": "Chile", "Peru": "Peru",
    "Malaysia": "Malaysia", "Thailand": "Thailand", "Qatar": "Qatar", "Kuwait": "Kuwait",
}

COUNTRY_META = {
    "USA":            {"iso_numeric": 840, "flag": "🇺🇸"},
    "Deutschland":    {"iso_numeric": 276, "flag": "🇩🇪"},
    "UK":             {"iso_numeric": 826, "flag": "🇬🇧"},
    "Südkorea":       {"iso_numeric": 410, "flag": "🇰🇷"},
    "Japan":          {"iso_numeric": 392, "flag": "🇯🇵"},
    "Südafrika":      {"iso_numeric": 710, "flag": "🇿🇦"},
    "Taiwan":         {"iso_numeric": 158, "flag": "🇹🇼"},
    "Australien":     {"iso_numeric":  36, "flag": "🇦🇺"},
    "China":          {"iso_numeric": 156, "flag": "🇨🇳"},
    "Hongkong":       {"iso_numeric": 344, "flag": "🇭🇰"},
    "Singapur":       {"iso_numeric": 702, "flag": "🇸🇬"},
    "Indien":         {"iso_numeric": 356, "flag": "🇮🇳"},
    "Schweiz":        {"iso_numeric": 756, "flag": "🇨🇭"},
    "Frankreich":     {"iso_numeric": 250, "flag": "🇫🇷"},
    "Niederlande":    {"iso_numeric": 528, "flag": "🇳🇱"},
    "Schweden":       {"iso_numeric": 752, "flag": "🇸🇪"},
    "Dänemark":       {"iso_numeric": 208, "flag": "🇩🇰"},
    "Belgien":        {"iso_numeric":  56, "flag": "🇧🇪"},
    "Italien":        {"iso_numeric": 380, "flag": "🇮🇹"},
    "Spanien":        {"iso_numeric": 724, "flag": "🇪🇸"},
    "Griechenland":   {"iso_numeric": 300, "flag": "🇬🇷"},
    "Polen":          {"iso_numeric": 616, "flag": "🇵🇱"},
    "Türkei":         {"iso_numeric": 792, "flag": "🇹🇷"},
    "Brasilien":      {"iso_numeric":  76, "flag": "🇧🇷"},
    "Mexiko":         {"iso_numeric": 484, "flag": "🇲🇽"},
    "Kanada":         {"iso_numeric": 124, "flag": "🇨🇦"},
    "Russland":       {"iso_numeric": 643, "flag": "🇷🇺"},
    "Indonesien":     {"iso_numeric": 360, "flag": "🇮🇩"},
    "Philippinen":    {"iso_numeric": 608, "flag": "🇵🇭"},
    "Argentinien":    {"iso_numeric":  32, "flag": "🇦🇷"},
    "Bolivien":       {"iso_numeric":  68, "flag": "🇧🇴"},
    "Peru":           {"iso_numeric": 604, "flag": "🇵🇪"},
    "Chile":          {"iso_numeric": 152, "flag": "🇨🇱"},
    "Sambia":         {"iso_numeric": 894, "flag": "🇿🇲"},
    "Simbabwe":       {"iso_numeric": 716, "flag": "🇿🇼"},
    "DRK":            {"iso_numeric": 180, "flag": "🇨🇩"},
    "Neuseeland":     {"iso_numeric": 554, "flag": "🇳🇿"},
    "Israel":         {"iso_numeric": 376, "flag": "🇮🇱"},
    "Saudi-Arabien":  {"iso_numeric": 682, "flag": "🇸🇦"},
    "Ver. Arabische Emirate": {"iso_numeric": 784, "flag": "🇦🇪"},
    "Malaysia":       {"iso_numeric": 458, "flag": "🇲🇾"},
    "Thailand":       {"iso_numeric": 764, "flag": "🇹🇭"},
    "Qatar":          {"iso_numeric": 634, "flag": "🇶🇦"},
    "Kuwait":         {"iso_numeric": 414, "flag": "🇰🇼"},
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

def canon(name):
    return COUNTRY_MAP.get(name, name)

def fetch_country_weights(product_id, ticker):
    url = ENDPOINT_TMPL.format(pid=product_id)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        if resp.status_code != 200:
            print(f"  [{ticker}] HTTP {resp.status_code}")
            return None
        data = json.loads(resp.content.decode("utf-8-sig"))
        rows = data.get("aaData", [])
        if not rows:
            return None
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
    except (requests.RequestException, json.JSONDecodeError) as e:
        print(f"  [{ticker}] Fehler: {e}"); return None


def calculate_portfolio_weights():
    global_weights = {}
    for ticker, config in PORTFOLIO.items():
        portfolio_pct = config["pct"]
        country_data = None
        if config.get("product_id"):
            print(f"Lade {ticker}...")
            country_data = fetch_country_weights(config["product_id"], ticker)
            time.sleep(1.5)
        if country_data is None:
            if ticker in EDELMETALL_FALLBACK:
                country_data = EDELMETALL_FALLBACK[ticker]
                print(f"  [{ticker}] Fallback (USGS)")
            elif ticker in EINZELPOSITIONEN_FALLBACK:
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
    today = datetime.now().strftime("%Y-%m-%d")
    output = []
    for c, d in global_weights.items():
        if d["pct_gesamt"] < 0.05: continue
        meta = COUNTRY_META.get(c, {})
        output.append({
            "land": c,
            "iso_numeric": meta.get("iso_numeric"),
            "flag": meta.get("flag", "🏳"),
            "pct_gesamt": round(d["pct_gesamt"], 2),
            "via": d["via"],
            "last_updated": today,
        })
    output.sort(key=lambda x: x["pct_gesamt"], reverse=True)
    return output


def load_existing(path):
    try: return json.load(open(path, "r", encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError): return {}


if __name__ == "__main__":
    OUTPUT = "data/geo_weights.json"
    os.makedirs("data", exist_ok=True)
    print(f"=== Geo-Update gestartet ({datetime.now():%Y-%m-%d %H:%M}) ===")
    existing = load_existing(OUTPUT)
    new_weights = calculate_portfolio_weights()
    if not new_weights:
        print("WARNUNG: Keine Daten - behalte bestehende JSON.")
    else:
        result = dict(existing) if existing else {}
        result["_meta"] = {
            "last_updated": datetime.now().strftime("%Y-%m-%d"),
            "total_positions": len(PORTFOLIO),
            "total_countries": len(new_weights),
            "source": "iShares-DE AJAX tab=all (Laender aus Holdings aggregiert + COUNTRY_MAP konsolidiert)",
            "note": "pct_gesamt = Anteil am Portfolio. EUR = currentTotal * pct_gesamt / 100",
        }
        result["countries"] = new_weights
        with open(OUTPUT, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"=== Fertig: {len(new_weights)} Laender ===")
