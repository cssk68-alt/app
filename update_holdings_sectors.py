"""
update_holdings_sectors.py
Holt Holdings + Sektoren fuer alle iShares-ETFs des Sparplans direkt vom
offiziellen iShares-DE-AJAX-Endpoint und schreibt zwei JSON-Dateien:

  data/holdings.json   - Top-N Holdings je ETF
  data/sectors.json    - aggregierte Sektor-Verteilung je ETF

Strategie: pro ETF wird nur EIN Request gemacht (tab=all). Die Sektor-
Aggregation passiert lokal aus den Holdings - das ist immer konsistent
und spart Rate-Limit.

Wird woechentlich via GitHub Actions ausgefuehrt.
"""
import json
import os
import re
import time
import requests
from datetime import datetime

PORTFOLIO_ETFS = {
    "SXR8": {"product_id": "253743", "isin": "IE00B5BMR087"},
    "CPXJ": {"product_id": "253735", "isin": "IE00B52MJY50"},
    "CSKR": {"product_id": "253733", "isin": "IE00B5W4TY14"},
    "IJPA": {"product_id": "251867", "isin": "IE00B4L5YX21"},
    "WHCS": {"product_id": "308909", "isin": "IE00BJ5JNZ06"},
    "AGED": {"product_id": "284218", "isin": "IE00BYZK4669"},
    "EIMI": {"product_id": "264659", "isin": "IE00BKM4GZ66"},
    "ISF":  {"product_id": "251795", "isin": "IE0005042456"},
}

TOP_N_HOLDINGS = 10

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

ASSET_CLASS_SKIP = {"geldmarkt", "cash und/oder derivate", "cash", "futures", "futures sell"}
NAME_SKIP_PATTERNS = ("CASH", "USD CASH", "EUR CASH", "GBP CASH", "FUTURES", "DERIVATIVE", "MARGIN")
ISIN_RX = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")


def parse_row(row):
    if not isinstance(row, list) or len(row) < 6:
        return None
    name = str(row[1]).strip() if len(row) > 1 else ""
    if not name:
        return None
    asset_class = ""
    for i in (3, 4):
        if i < len(row) and isinstance(row[i], str):
            asset_class = row[i].strip().lower()
            break
    if asset_class in ASSET_CLASS_SKIP:
        return None
    name_upper = name.upper()
    if any(p in name_upper for p in NAME_SKIP_PATTERNS):
        return None
    isin = None
    for v in row:
        if isinstance(v, str) and ISIN_RX.match(v):
            isin = v
            break
    # Weight % ist konsistent der ZWEITE Dict in der Row.
    # Dict 1 = Marktwert (USD), Dict 2 = Weight %, Dict 3 = Marktwert (Fund-CCY).
    # Diese Reihenfolge ist robust ueber 13-col- und 14-col-Strukturen.
    dicts_with_raw = [v for v in row if isinstance(v, dict) and "raw" in v]
    weight = None
    if len(dicts_with_raw) >= 2:
        try:
            weight = float(dicts_with_raw[1]["raw"])
        except (TypeError, ValueError):
            weight = None
    if weight is None or weight <= 0 or weight > 100:
        return None
    sector = None
    for i in (2, 3):
        if i < len(row) and isinstance(row[i], str):
            s = row[i].strip()
            if s and s.lower() not in ASSET_CLASS_SKIP and s.lower() not in ("aktien", "equity", "anleihen", "bond"):
                sector = s
                break
    country = None
    for i in range(9, min(len(row), 13)):
        v = row[i]
        if isinstance(v, str) and len(v) > 2 and not ISIN_RX.match(v):
            if "/" not in v and v not in ("-", "USD", "EUR", "GBP", "JPY"):
                country = v
                break
    return {"name": name, "isin": isin, "weight_pct": round(weight, 4), "sector": sector, "country": country}


def fetch_holdings_raw(pid, ticker):
    url = ENDPOINT_TMPL.format(pid=pid)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        if resp.status_code != 200:
            print(f"  [{ticker}] HTTP {resp.status_code} (pid={pid})", flush=True)
            return None
        text = resp.content.decode("utf-8-sig")
        data = json.loads(text)
        return data.get("aaData", [])
    except (requests.RequestException, json.JSONDecodeError) as e:
        print(f"  [{ticker}] Fehler: {e}", flush=True)
        return None


def load_existing(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def process_etf(ticker, pid):
    raw_rows = fetch_holdings_raw(pid, ticker)
    if not raw_rows:
        return None, None
    parsed = []
    for row in raw_rows:
        p = parse_row(row)
        if p:
            parsed.append(p)
    if not parsed:
        print(f"  [{ticker}] Keine parsebaren Rows", flush=True)
        return None, None
    parsed.sort(key=lambda x: x["weight_pct"], reverse=True)
    top = [{"name": p["name"], "isin": p["isin"], "weight_pct": p["weight_pct"]} for p in parsed[:TOP_N_HOLDINGS]]
    sector_sums = {}
    for p in parsed:
        s = p["sector"] or "Sonstige"
        sector_sums[s] = sector_sums.get(s, 0) + p["weight_pct"]
    sectors = [{"sector": s, "weight_pct": round(w, 4)} for s, w in sorted(sector_sums.items(), key=lambda x: -x[1])]
    today = datetime.now().strftime("%Y-%m-%d")
    h_block = {"product_id": pid, "last_updated": today, "holdings_count": len(parsed), "top_holdings": top}
    s_block = {"product_id": pid, "last_updated": today, "sectors": sectors}
    print(f"  [{ticker}] OK - {len(parsed)} Holdings, {len(sectors)} Sektoren", flush=True)
    return h_block, s_block


def main():
    os.makedirs("data", exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    holdings_out = {"_meta": {"last_updated": today, "source": "iShares-DE AJAX tab=all", "endpoint": ENDPOINT_TMPL.format(pid="{ID}")}, "etfs": {}}
    sectors_out = {"_meta": {"last_updated": today, "source": "Aggregiert aus iShares Holdings", "note": "Sektor-Namen wie von iShares-DE geliefert (DE/EN gemischt)"}, "etfs": {}}
    existing_h = load_existing("data/holdings.json").get("etfs", {})
    existing_s = load_existing("data/sectors.json").get("etfs", {})
    print(f"=== Holdings/Sectors Update gestartet ({datetime.now():%Y-%m-%d %H:%M}) ===", flush=True)
    for ticker, cfg in PORTFOLIO_ETFS.items():
        print(f"\n-> {ticker} (pid={cfg['product_id']}, isin={cfg['isin']})", flush=True)
        h, s = process_etf(ticker, cfg["product_id"])
        if h:
            holdings_out["etfs"][ticker] = h
        elif ticker in existing_h:
            print(f"  [{ticker}] FALLBACK Holdings -> bestehende Daten", flush=True)
            holdings_out["etfs"][ticker] = existing_h[ticker]
        if s:
            sectors_out["etfs"][ticker] = s
        elif ticker in existing_s:
            print(f"  [{ticker}] FALLBACK Sectors -> bestehende Daten", flush=True)
            sectors_out["etfs"][ticker] = existing_s[ticker]
        time.sleep(1.5)
    with open("data/holdings.json", "w", encoding="utf-8") as f:
        json.dump(holdings_out, f, ensure_ascii=False, indent=2)
    with open("data/sectors.json", "w", encoding="utf-8") as f:
        json.dump(sectors_out, f, ensure_ascii=False, indent=2)
    print(f"\n=== Fertig: {len(holdings_out['etfs'])} ETFs ===", flush=True)


if __name__ == "__main__":
    main()
