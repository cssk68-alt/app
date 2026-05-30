"""
update_performance.py
Holt taegliche Schlusskurse fuer alle Portfolio-Positionen + MSCI World seit
18. Mai 2026 und berechnet kumulative Returns in EUR.

Jeder Ticker wird in seiner Listing-Waehrung (USD/GBp/EUR) geholt und
ueber tagesgenaue EUR-Kurse (EUR/USD, EUR/GBP) in EUR umgerechnet, bevor
Returns berechnet werden -> faire Vergleichsbasis mit IWDA.AS in EUR
(deine Sparplan-Wallet-Sicht).

Yahoo Finance primaer (Host-Fallback query1/query2), Stooq als Fallback.
Wird Mo-Fr mehrmals pro Stunde (Cron '7,37 7-21 * * 1-5' UTC) via GitHub Actions
ausgefuehrt, damit die Werte mindestens stuendlich aktualisiert werden.
Faellt die FX-/Kursabfrage aus, werden die letzten bekannten Kurse genutzt
statt das Update komplett abzubrechen.
"""
import calendar
import json
import os
import random
import time
from datetime import date, datetime, timedelta, timezone
import requests

BASELINE_DATE = date(2026, 5, 18)
MIN_SUCCESS_TICKERS = 12  # strikt 12/12: bei weniger werden alte Kurse eingefroren, nie Teil-Updates geschrieben

# Optionale API-Keys via Env/GitHub-Secret. Ohne Key bleiben die jeweiligen
# Fallbacks komplett inert (return None) -> kein Verhalten aendert sich, keine
# Fehlversuche. Quell-Reihenfolge insgesamt:
#   Ticker: Yahoo -> Stooq -> AlphaVantage(key)
#   FX:     Yahoo -> Stooq -> Frankfurter/EZB -> open.er-api(keyless,nur aktuell) -> AlphaVantage(key)
ALPHAVANTAGE_KEY = os.environ.get("ALPHAVANTAGE_KEY", "").strip()

# ticker -> (Yahoo-Symbol, Stooq-Symbol, ISIN, Portfolio-Gewicht in %)
# WHCS: WHCS.L existiert nicht auf LSE; WHCS ist Amsterdam/Swiss ticker,
#       CBUF waere Xetra. WHCS.AS hat Yahoo-Coverage.
PORTFOLIO_TICKERS = {
    "SXR8": ("SXR8.DE", "sxr8.de", "IE00B5BMR087", 20.0),
    "CPXJ": ("CPXJ.L",  "cpxj.uk", "IE00B52MJY50", 15.0),
    "CSKR": ("CSKR.L",  "cskr.uk", "IE00B5W4TY14",  2.6),
    "IJPA": ("IJPA.L",  "ijpa.uk", "IE00B4L5YX21",  2.4),
    "WHCS": ("WHCS.AS", "whcs.nl", "IE00BJ5JNZ06", 14.0),
    "AGED": ("AGED.L",  "aged.uk", "IE00BYZK4669",  5.0),
    "PHAG": ("PHAG.L",  "phag.uk", "JE00B1VS3333",  6.0),
    "PHPT": ("PHPT.L",  "phpt.uk", "JE00B1VS2W53",  4.6),
    "COPA": ("COPA.L",  "copa.uk", "GB00B15KXQ89",  4.4),
    "EIMI": ("EIMI.L",  "eimi.uk", "IE00BKM4GZ66", 14.0),
    "ALV":  ("ALV.DE",  "alv.de",  "DE0008404005",  7.0),
    "ISF":  ("ISF.L",   "isf.uk",  "IE0005042456",  5.0),
}
# Lesbare Produktnamen pro Ticker (fuer die Warnanzeige auf Slide 4, falls
# ein Wert nicht gezogen werden konnte).
PORTFOLIO_NAMES = {
    "SXR8": "iShares Core S&P 500",
    "CPXJ": "iShares Core MSCI Pacific ex-Japan",
    "CSKR": "iShares MSCI Korea",
    "IJPA": "iShares Core MSCI Japan IMI",
    "WHCS": "iShares MSCI World Health Care Sector",
    "AGED": "iShares Ageing Population",
    "PHAG": "WisdomTree Physical Silver",
    "PHPT": "WisdomTree Physical Platinum",
    "COPA": "WisdomTree Copper",
    "EIMI": "iShares Core MSCI Emerging Markets IMI",
    "ALV":  "Allianz SE",
    "ISF":  "iShares Core FTSE 100",
    "MSCI": "iShares Core MSCI World (Benchmark)",
}
# Wenn Yahoo komplett fehlschlaegt und nur Stooq Daten liefert: bekannte
# Listing-Waehrung pro Ticker (Stooq exposes keine currency).
TICKER_CURRENCY_FALLBACK = {
    "SXR8": "EUR", "CPXJ": "USD", "CSKR": "USD", "IJPA": "USD",
    "WHCS": "USD", "AGED": "USD", "PHAG": "USD", "PHPT": "USD",
    "COPA": "USD", "EIMI": "USD", "ALV":  "EUR", "ISF":  "GBp",
}
BENCHMARK = ("IWDA.AS", "iwda.nl", "IE00B4L5Y983")  # iShares Core MSCI World EUR
BENCHMARK_CURRENCY_FALLBACK = "EUR"

# Alpha-Vantage-Symbole (nur genutzt, wenn ALPHAVANTAGE_KEY gesetzt ist).
# AV nutzt teils andere Suffixe als Yahoo (.DEX/.LON) bzw. listet manche UCITS-
# ETFs gar nicht -> nur eintragen, was AV wirklich kennt; fehlt ein Mapping,
# wird der AV-Fallback fuer diesen Ticker einfach uebersprungen.
ALPHAVANTAGE_SYMBOLS = {
    "SXR8": "SXR8.DEX",
    "ALV":  "ALV.DEX",
    "ISF":  "ISF.LON",
    # uebrige Ticker: AV-Coverage unsicher -> bewusst leer gelassen.
}

# FX-Paare die wir brauchen: EURUSD=X (Yahoo) bzw. eurusd (Stooq), EURGBP=X / eurgbp
FX_SYMBOLS = {
    "USD": ("EURUSD=X", "eurusd"),
    "GBP": ("EURGBP=X", "eurgbp"),
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
}


def _date_str(d):
    return d.strftime("%Y-%m-%d")


def _get_with_retry(url, headers, timeout=15, retries=4, backoff=2.0):
    """requests.get mit Wiederholung bei transienten Fehlern (429/Timeout/
    Verbindungsfehler) und exponentiellem Backoff. Returns Response oder None."""
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=headers, timeout=timeout)
            if r.status_code == 429:
                time.sleep(backoff * (2 ** attempt) + random.random())
                continue
            return r
        except requests.RequestException:
            time.sleep(backoff * (2 ** attempt) + random.random())
    return None


def fetch_yahoo(symbol, start_d, end_d):
    """Yahoo Finance v8 chart API. Returns (prices_dict, currency_str) or (None, None).
    Versucht query1 und faellt bei Fehler/Block auf query2 zurueck (Yahoo verteilt
    Last/Rate-Limits ueber mehrere Hosts)."""
    start_ts = calendar.timegm(start_d.timetuple())
    end_ts = calendar.timegm((end_d + timedelta(days=1)).timetuple())
    path = (f"/v8/finance/chart/{symbol}"
            f"?period1={start_ts}&period2={end_ts}&interval=1d")
    for host in ("query1.finance.yahoo.com", "query2.finance.yahoo.com"):
        try:
            r = _get_with_retry(f"https://{host}{path}", HEADERS)
            if r is None or r.status_code != 200:
                continue
            data = r.json()
            if data.get("chart", {}).get("error"):
                continue
            result = (data.get("chart", {}).get("result") or [None])[0]
            if not result:
                continue
            currency = (result.get("meta") or {}).get("currency")
            timestamps = result.get("timestamp") or []
            quote = (result.get("indicators", {}).get("quote") or [{}])[0]
            closes = quote.get("close") or []
            prices = {}
            for ts, c in zip(timestamps, closes):
                if c is None:
                    continue
                d = datetime.fromtimestamp(ts, tz=timezone.utc).date()
                prices[_date_str(d)] = float(c)
            if prices:
                return prices, currency
        except (requests.RequestException, ValueError, KeyError, IndexError):
            continue
    return None, None


def fetch_stooq(symbol, start_d, end_d):
    """Stooq CSV daily. Returns dict {YYYY-MM-DD: close_price} or None."""
    d1 = start_d.strftime("%Y%m%d")
    d2 = end_d.strftime("%Y%m%d")
    url = f"https://stooq.com/q/d/l/?s={symbol}&d1={d1}&d2={d2}&i=d"
    try:
        r = _get_with_retry(url, HEADERS)
        if r is None or r.status_code != 200:
            return None
        text = r.text.strip()
        if not text or "no data" in text.lower():
            return None
        lines = text.splitlines()
        if len(lines) < 2:
            return None
        header = [h.strip().lower() for h in lines[0].split(",")]
        try:
            i_date = header.index("date")
            i_close = header.index("close")
        except ValueError:
            return None
        prices = {}
        for line in lines[1:]:
            parts = line.split(",")
            if len(parts) <= max(i_date, i_close):
                continue
            try:
                d_str = parts[i_date].strip()
                if len(d_str) != 10:
                    continue
                c = float(parts[i_close])
                prices[d_str] = c
            except ValueError:
                continue
        return prices if prices else None
    except requests.RequestException:
        return None


def fetch_ticker(name, yahoo_sym, stooq_sym, fallback_currency, start_d, end_d):
    """Yahoo zuerst (liefert auch currency), dann Stooq mit fallback_currency.
    Returns (prices_dict, currency) or (None, None)."""
    prices, currency = fetch_yahoo(yahoo_sym, start_d, end_d)
    if prices and len(prices) >= 2:
        print(f"  [{name}] Yahoo OK ({len(prices)} Tage, currency={currency})", flush=True)
        return prices, currency or fallback_currency
    if prices:
        print(f"  [{name}] Yahoo zu wenig Daten ({len(prices)}), versuche Stooq...", flush=True)
    else:
        print(f"  [{name}] Yahoo fehlgeschlagen, versuche Stooq...", flush=True)
    time.sleep(0.3 + random.random() * 0.3)
    prices = fetch_stooq(stooq_sym, start_d, end_d)
    if prices and len(prices) >= 2:
        print(f"  [{name}] Stooq OK ({len(prices)} Tage, fallback currency={fallback_currency})", flush=True)
        return prices, fallback_currency
    av_sym = ALPHAVANTAGE_SYMBOLS.get(name)
    if ALPHAVANTAGE_KEY and av_sym:
        print(f"  [{name}] Yahoo+Stooq fehlgeschlagen, versuche AlphaVantage ({av_sym})...", flush=True)
        time.sleep(0.3)
        av_prices, _ = fetch_av(av_sym, start_d, end_d)
        if av_prices and len(av_prices) >= 2:
            print(f"  [{name}] AlphaVantage OK ({len(av_prices)} Tage, fallback currency={fallback_currency})", flush=True)
            return av_prices, fallback_currency
    print(f"  [{name}] FEHLGESCHLAGEN (Yahoo+Stooq" + ("+AV" if (ALPHAVANTAGE_KEY and av_sym) else "") + ")", flush=True)
    return None, None


def fetch_fx_frankfurter(pair_code, start_d, end_d):
    """FX-Fallback ueber frankfurter.app (offizielle EZB-Referenzkurse, kein
    API-Key, kein Scraping/Rate-Limit). Returns {YYYY-MM-DD: rate} (X pro 1 EUR)
    oder None. EZB liefert nur Bankarbeitstage -> forward_fill schliesst Luecken."""
    d1 = start_d.strftime("%Y-%m-%d")
    d2 = end_d.strftime("%Y-%m-%d")
    url = f"https://api.frankfurter.app/{d1}..{d2}?base=EUR&symbols={pair_code}"
    try:
        r = _get_with_retry(url, HEADERS)
        if r is None or r.status_code != 200:
            return None
        rates = (r.json() or {}).get("rates") or {}
        out = {}
        for d_str, day in rates.items():
            v = (day or {}).get(pair_code)
            if v:
                out[d_str] = float(v)
        return out if out else None
    except (requests.RequestException, ValueError, KeyError):
        return None


def fetch_fx_erapi(pair_code, start_d, end_d):
    """FX-Fallback ueber open.er-api.com (keyless). Liefert NUR den aktuellen
    Kurs (keine Historie) -> als ein-Tages-Snapshot {today: rate}; forward_fill
    breitet ihn auf die Achse aus. Returns {date: rate} (X pro 1 EUR) oder None."""
    try:
        r = _get_with_retry("https://open.er-api.com/v6/latest/EUR", HEADERS)
        if r is None or r.status_code != 200:
            return None
        data = r.json() or {}
        rate = (data.get("rates") or {}).get(pair_code)
        if not rate:
            return None
        return {_date_str(BASELINE_DATE): float(rate)}
    except (requests.RequestException, ValueError, KeyError):
        return None


def fetch_fx_alphavantage(pair_code, start_d, end_d):
    """FX-Fallback ueber Alpha Vantage FX_DAILY (benoetigt ALPHAVANTAGE_KEY).
    Ohne Key -> None (inert). Returns {YYYY-MM-DD: rate} (X pro 1 EUR) oder None."""
    if not ALPHAVANTAGE_KEY:
        return None
    url = ("https://www.alphavantage.co/query?function=FX_DAILY"
           f"&from_symbol=EUR&to_symbol={pair_code}&outputsize=full&apikey={ALPHAVANTAGE_KEY}")
    try:
        r = _get_with_retry(url, HEADERS)
        if r is None or r.status_code != 200:
            return None
        series = (r.json() or {}).get("Time Series FX (Daily)") or {}
        lo, hi = _date_str(start_d), _date_str(end_d)
        out = {}
        for d_str, row in series.items():
            if lo <= d_str <= hi:
                close = (row or {}).get("4. close")
                if close:
                    out[d_str] = float(close)
        return out if out else None
    except (requests.RequestException, ValueError, KeyError):
        return None


def fetch_av(symbol_av, start_d, end_d):
    """Ticker-Fallback ueber Alpha Vantage TIME_SERIES_DAILY (benoetigt
    ALPHAVANTAGE_KEY). Ohne Key -> (None, None). Returns (prices_dict, currency)
    -> currency ist None (AV liefert keine), Aufrufer nutzt fallback_currency."""
    if not ALPHAVANTAGE_KEY or not symbol_av:
        return None, None
    url = ("https://www.alphavantage.co/query?function=TIME_SERIES_DAILY"
           f"&symbol={symbol_av}&outputsize=full&apikey={ALPHAVANTAGE_KEY}")
    try:
        r = _get_with_retry(url, HEADERS)
        if r is None or r.status_code != 200:
            return None, None
        series = (r.json() or {}).get("Time Series (Daily)") or {}
        lo, hi = _date_str(start_d), _date_str(end_d)
        out = {}
        for d_str, row in series.items():
            if lo <= d_str <= hi:
                close = (row or {}).get("4. close")
                if close:
                    out[d_str] = float(close)
        return (out, None) if out else (None, None)
    except (requests.RequestException, ValueError, KeyError):
        return None, None


def fetch_fx(pair_code, start_d, end_d):
    """Holt EUR/X-Kurse (X = USD oder GBP). Returns dict {date: rate} oder None.
    Rate = wieviel X pro 1 EUR (Standard-Quotation EURUSD=1.16 -> 1 EUR = 1.16 USD).
    Reihenfolge: Yahoo -> Stooq -> Frankfurter/EZB."""
    yh, st = FX_SYMBOLS[pair_code]
    prices, _ = fetch_yahoo(yh, start_d, end_d)
    if prices and len(prices) >= 2:
        print(f"  [FX EUR{pair_code}] Yahoo OK ({len(prices)} Tage)", flush=True)
        return prices
    print(f"  [FX EUR{pair_code}] Yahoo fehlgeschlagen, versuche Stooq...", flush=True)
    time.sleep(0.3)
    prices = fetch_stooq(st, start_d, end_d)
    if prices and len(prices) >= 2:
        print(f"  [FX EUR{pair_code}] Stooq OK ({len(prices)} Tage)", flush=True)
        return prices
    print(f"  [FX EUR{pair_code}] Stooq fehlgeschlagen, versuche Frankfurter (EZB)...", flush=True)
    time.sleep(0.3)
    prices = fetch_fx_frankfurter(pair_code, start_d, end_d)
    if prices and len(prices) >= 1:
        print(f"  [FX EUR{pair_code}] Frankfurter/EZB OK ({len(prices)} Tage)", flush=True)
        return prices
    print(f"  [FX EUR{pair_code}] Frankfurter fehlgeschlagen, versuche open.er-api...", flush=True)
    time.sleep(0.3)
    prices = fetch_fx_erapi(pair_code, start_d, end_d)
    if prices and len(prices) >= 1:
        print(f"  [FX EUR{pair_code}] open.er-api OK (aktueller Kurs)", flush=True)
        return prices
    if ALPHAVANTAGE_KEY:
        print(f"  [FX EUR{pair_code}] open.er-api fehlgeschlagen, versuche AlphaVantage...", flush=True)
        time.sleep(0.3)
        prices = fetch_fx_alphavantage(pair_code, start_d, end_d)
        if prices and len(prices) >= 1:
            print(f"  [FX EUR{pair_code}] AlphaVantage OK ({len(prices)} Tage)", flush=True)
            return prices
    print(f"  [FX EUR{pair_code}] FEHLGESCHLAGEN", flush=True)
    return None


def first_available(prices, baseline, lookforward=10):
    if not prices:
        return None
    for i in range(lookforward):
        key = _date_str(baseline + timedelta(days=i))
        if key in prices:
            return prices[key]
    return None


def forward_fill(prices, all_dates):
    """Liste paralleler Preise zu all_dates, vorwaerts-gefuellt fuer Luecken (WE/Feiertage)."""
    out = []
    last = None
    for d_str in all_dates:
        if prices and d_str in prices:
            last = prices[d_str]
        out.append(last)
    return out


def to_eur(price_native, currency, fx_usd, fx_gbp):
    """Konvertiert einen Tagespreis von Listing-Currency nach EUR.
    fx_usd / fx_gbp = USD bzw. GBP pro 1 EUR (also "price / fx" -> EUR)."""
    if price_native is None:
        return None
    if currency == "EUR":
        return price_native
    if currency == "USD":
        return price_native / fx_usd if fx_usd else None
    if currency == "GBP":
        return price_native / fx_gbp if fx_gbp else None
    if currency in ("GBp", "GBX"):  # Pence = 1/100 GBP
        return (price_native / 100.0) / fx_gbp if fx_gbp else None
    # unbekannte Waehrung -> nicht konvertierbar
    return None


def convert_series_to_eur(native_series, currency, fx_usd_series, fx_gbp_series):
    """Wendet to_eur auf eine ganze Datums-parallele Reihe an."""
    return [to_eur(p, currency, u, g) for p, u, g in zip(native_series, fx_usd_series, fx_gbp_series)]


def calc_week_return(monday, friday, dates, returns):
    sunday = monday - timedelta(days=1)
    start_pct = None
    end_pct = None
    for d_str, r in zip(dates, returns):
        if r is None:
            continue
        d = datetime.strptime(d_str, "%Y-%m-%d").date()
        if d <= sunday:
            start_pct = r
        if d <= friday:
            end_pct = r
    if start_pct is None:
        start_pct = 0.0
    if end_pct is None:
        return None
    return round(end_pct - start_pct, 4)


def write_frozen(existing_obj, failed_tickers, now_utc):
    """Strikt-12/12-Politik: Bei unvollstaendigem Update KEINE neuen Kurse
    schreiben. Alte Kurs-Arrays (dates/portfolio/msci_world/weekly/ticker_returns)
    1:1 behalten, nur _meta.last_updated + failed_tickers + tickers_ok
    aktualisieren; last_all_ok_timestamp + alle Reihen bleiben eingefroren.
    -> Datum zeigt 'heute geprueft', Uhrzeit/Werte frieren auf letztem 12/12-Stand.
    Returns True wenn geschrieben."""
    if not existing_obj or "dates" not in existing_obj:
        print("  Kein bestehender Datensatz zum Einfrieren -> nichts geschrieben.", flush=True)
        return False
    meta = existing_obj.get("_meta") or {}
    total = len(PORTFOLIO_TICKERS)
    meta["last_updated"] = now_utc.strftime('%Y-%m-%dT%H:%M:%SZ')
    meta["update_success"] = True
    meta["tickers_total"] = total
    meta["tickers_ok"] = max(0, total - len([t for t in failed_tickers if t != "MSCI"]))
    meta["failed_tickers"] = [
        {"symbol": t, "name": PORTFOLIO_NAMES.get(t, t)} for t in failed_tickers
    ]
    existing_obj["_meta"] = meta
    with open("data/performance.json", "w", encoding="utf-8") as f:
        json.dump(existing_obj, f, ensure_ascii=False, indent=2)
    print(f"  Eingefroren: {meta['tickers_ok']}/{total} OK, alte Kurse beibehalten, "
          f"last_updated={meta['last_updated']}.", flush=True)
    return True


def main():
    os.makedirs("data", exist_ok=True)
    today = date.today()
    start = BASELINE_DATE
    now_utc = datetime.now(timezone.utc)
    print(f"=== Performance Update gestartet ({now_utc:%Y-%m-%d %H:%M} UTC) ===", flush=True)

    existing_obj = None
    existing_last_all_ok_ts = None
    existing_fx_snapshot = {}
    try:
        if os.path.exists("data/performance.json"):
            with open("data/performance.json", "r", encoding="utf-8") as f:
                existing_obj = json.load(f)
                _existing_meta = existing_obj.get("_meta", {})
                existing_last_all_ok_ts = _existing_meta.get("last_all_ok_timestamp")
                existing_fx_snapshot = _existing_meta.get("fx_snapshot") or {}
    except Exception:
        pass
    print(f"Baseline: {_date_str(BASELINE_DATE)}  -> heute: {_date_str(today)}", flush=True)

    # 1) FX-Kurse holen (kritisch fuer EUR-Normalisierung)
    print("\n--- FX-Kurse (EUR Basis) ---", flush=True)
    fx_usd = fetch_fx("USD", start, today)
    time.sleep(0.4)
    fx_gbp = fetch_fx("GBP", start, today)

    # FX-Fallback: bewegt sich intraday nur minimal. Statt das ganze Update
    # abzubrechen, den letzten bekannten Kurs aus der vorhandenen
    # performance.json (fx_snapshot) wiederverwenden -> Update laeuft weiter.
    if not fx_usd and existing_fx_snapshot.get("USD_latest"):
        fx_usd = {_date_str(BASELINE_DATE): existing_fx_snapshot["USD_latest"]}
        print(f"  [FX EURUSD] Fallback: letzter bekannter Kurs "
              f"{existing_fx_snapshot['USD_latest']:.5f}", flush=True)
    if not fx_gbp and existing_fx_snapshot.get("GBP_latest"):
        fx_gbp = {_date_str(BASELINE_DATE): existing_fx_snapshot["GBP_latest"]}
        print(f"  [FX EURGBP] Fallback: letzter bekannter Kurs "
              f"{existing_fx_snapshot['GBP_latest']:.5f}", flush=True)

    if not fx_usd or not fx_gbp:
        print("FX-Kurse unvollstaendig und kein Fallback vorhanden -> "
              "EUR-Normalisierung waere ungenau. performance.json bleibt unveraendert.",
              flush=True)
        return

    # 2) Portfolio-Ticker holen (native currency)
    print("\n--- Portfolio-Ticker ---", flush=True)
    portfolio_data = {}  # ticker -> (prices_dict, currency)
    failed_tickers = []
    for ticker, (yh, st, isin, _w) in PORTFOLIO_TICKERS.items():
        print(f"-> {ticker} (Yahoo: {yh}, Stooq: {st}, ISIN: {isin})", flush=True)
        prices, currency = fetch_ticker(
            ticker, yh, st, TICKER_CURRENCY_FALLBACK[ticker], start, today
        )
        if prices and currency:
            portfolio_data[ticker] = (prices, currency)
        else:
            failed_tickers.append(ticker)
        time.sleep(0.4 + random.random() * 0.3)

    print(f"\n--- Benchmark (MSCI World via IWDA.AS) ---", flush=True)
    msci_prices, msci_cur = fetch_ticker(
        "MSCI", BENCHMARK[0], BENCHMARK[1], BENCHMARK_CURRENCY_FALLBACK, start, today
    )

    n_ok = len(portfolio_data)
    print(f"\n=== Ergebnis: {n_ok}/{len(PORTFOLIO_TICKERS)} Portfolio, "
          f"MSCI: {'OK' if msci_prices else 'FAIL'} ===", flush=True)

    # Strikt 12/12: bei <12 erfolgreich geholten Tickern (oder fehlendem MSCI)
    # KEINE neuen Kurse schreiben. Alte Arrays einfrieren, nur last_updated +
    # failed_tickers aktualisieren (last_all_ok_timestamp bleibt eingefroren).
    if n_ok < MIN_SUCCESS_TICKERS or not msci_prices:
        frozen_failed = [t for t in PORTFOLIO_TICKERS if t not in portfolio_data]
        if not msci_prices:
            frozen_failed.append("MSCI")
        print(f"Nur {n_ok}/{len(PORTFOLIO_TICKERS)} Ticker"
              f"{' + MSCI fehlt' if not msci_prices else ''} -> alte Kurse einfrieren.", flush=True)
        write_frozen(existing_obj, frozen_failed, now_utc)
        return

    # 3) Datums-Achse
    all_dates = []
    d = BASELINE_DATE
    while d <= today:
        all_dates.append(_date_str(d))
        d += timedelta(days=1)

    # 4) FX-Series vorwaerts-fuellen
    fx_usd_series = forward_fill(fx_usd, all_dates)
    fx_gbp_series = forward_fill(fx_gbp, all_dates)

    # 5) Portfolio-Ticker auf EUR normalisieren
    ticker_series_eur = {}
    ticker_baselines_eur = {}
    print("\n--- EUR-Konvertierung ---", flush=True)
    for ticker, (prices, currency) in portfolio_data.items():
        native_series = forward_fill(prices, all_dates)
        eur_series = convert_series_to_eur(native_series, currency, fx_usd_series, fx_gbp_series)
        baseline_eur = next((p for p in eur_series if p is not None), None)
        if not baseline_eur or baseline_eur <= 0:
            print(f"  [{ticker}] Kein EUR-Baseline (currency={currency}) -> skip", flush=True)
            if ticker not in failed_tickers:
                failed_tickers.append(ticker)
            continue
        ticker_series_eur[ticker] = eur_series
        ticker_baselines_eur[ticker] = baseline_eur
        last = next((p for p in reversed(eur_series) if p is not None), None)
        ret_total = ((last / baseline_eur - 1) * 100) if (last and baseline_eur) else 0.0
        print(f"  [{ticker}] currency={currency}, baseline={baseline_eur:.4f} EUR, "
              f"latest={last:.4f} EUR, return={ret_total:+.3f}%", flush=True)

    # Strikt 12/12 auch nach EUR-Konvertierung: wenn ein Ticker keine EUR-Reihe
    # bekommen hat (z.B. unbekannte Waehrung / kein Baseline) -> einfrieren statt
    # einen verzerrten (untergewichteten) Verlauf zu schreiben.
    if len(ticker_series_eur) < len(PORTFOLIO_TICKERS):
        eur_failed = [t for t in PORTFOLIO_TICKERS if t not in ticker_series_eur]
        print(f"Nur {len(ticker_series_eur)}/{len(PORTFOLIO_TICKERS)} EUR-konvertierbar "
              f"({', '.join(eur_failed)}) -> alte Kurse einfrieren.", flush=True)
        write_frozen(existing_obj, eur_failed, now_utc)
        return

    # 6) MSCI EUR-konvertieren (IWDA.AS ist typ. EUR -> identity)
    msci_native = forward_fill(msci_prices, all_dates)
    msci_eur = convert_series_to_eur(msci_native, msci_cur or "EUR", fx_usd_series, fx_gbp_series)
    msci_baseline_eur = next((p for p in msci_eur if p is not None), None)
    if not msci_baseline_eur or msci_baseline_eur <= 0:
        print("MSCI: Kein EUR-Baseline -> alte Kurse einfrieren.", flush=True)
        write_frozen(existing_obj, ["MSCI"], now_utc)
        return
    print(f"  [MSCI] currency={msci_cur}, baseline={msci_baseline_eur:.4f} EUR", flush=True)

    # 7) Tagesreturns in % (EUR-basiert)
    portfolio_returns = []
    msci_returns = []
    for i in range(len(all_dates)):
        wsum = 0.0
        used = 0.0
        for ticker, series in ticker_series_eur.items():
            px = series[i]
            if px is None:
                continue
            w = PORTFOLIO_TICKERS[ticker][3]
            wsum += w * (px / ticker_baselines_eur[ticker] - 1)
            used += w
        portfolio_returns.append(round(wsum, 4) if used > 0 else None)
        m_px = msci_eur[i]
        msci_returns.append(round((m_px / msci_baseline_eur - 1) * 100, 4) if m_px else None)

    # Per-Ticker kumulative EUR-Returns (fuer Bucket-Analyse im Frontend)
    ticker_returns = {}
    for ticker, series in ticker_series_eur.items():
        last_px = next((p for p in reversed(series) if p is not None), None)
        base_px = ticker_baselines_eur[ticker]
        if last_px and base_px:
            ticker_returns[ticker] = round((last_px / base_px - 1) * 100, 4)

    # 8) Fuehrende None-Tage trimmen
    first_valid = 0
    for i in range(len(all_dates)):
        if portfolio_returns[i] is not None and msci_returns[i] is not None:
            first_valid = i
            break
    dates_out = all_dates[first_valid:]
    portfolio_out = portfolio_returns[first_valid:]
    msci_out = msci_returns[first_valid:]

    # 9) Wochenstats
    cur_mon = today - timedelta(days=today.weekday())
    cur_fri = cur_mon + timedelta(days=4)
    prev_mon = cur_mon - timedelta(weeks=1)
    prev_fri = prev_mon + timedelta(days=4)

    weekly = {
        "current": {
            "start": _date_str(cur_mon),
            "portfolio": calc_week_return(cur_mon, cur_fri, dates_out, portfolio_out),
            "msci": calc_week_return(cur_mon, cur_fri, dates_out, msci_out),
        },
        "previous": {
            "start": _date_str(prev_mon),
            "portfolio": calc_week_return(prev_mon, prev_fri, dates_out, portfolio_out),
            "msci": calc_week_return(prev_mon, prev_fri, dates_out, msci_out),
        },
    }

    # FX Snapshot fuer Debugging/Transparenz
    fx_snap = {
        "USD_baseline": next((v for v in fx_usd_series if v is not None), None),
        "USD_latest":   next((v for v in reversed(fx_usd_series) if v is not None), None),
        "GBP_baseline": next((v for v in fx_gbp_series if v is not None), None),
        "GBP_latest":   next((v for v in reversed(fx_gbp_series) if v is not None), None),
    }

    all_ok_now = len(ticker_series_eur) == len(PORTFOLIO_TICKERS)
    ts_str = now_utc.strftime('%Y-%m-%dT%H:%M:%SZ')
    out = {
        "_meta": {
            "last_updated": ts_str,
            "last_all_ok_timestamp": ts_str if all_ok_now else existing_last_all_ok_ts,
            "baseline_date": _date_str(BASELINE_DATE),
            "update_success": True,
            "tickers_ok": len(ticker_series_eur),
            "tickers_total": len(PORTFOLIO_TICKERS),
            "failed_tickers": [
                {"symbol": t, "name": PORTFOLIO_NAMES.get(t, t)}
                for t in failed_tickers
            ],
            "currency": "EUR",
            "normalization": "Alle Ticker tagesgenau via EURUSD=X / EURGBP=X auf EUR umgerechnet",
            "fx_snapshot": fx_snap,
            "source": "Yahoo Finance primaer, Stooq Fallback",
        },
        "dates": dates_out,
        "portfolio": portfolio_out,
        "msci_world": msci_out,
        "weekly": weekly,
        "ticker_returns": ticker_returns,
    }

    with open("data/performance.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    last_p = portfolio_out[-1] if portfolio_out else 0
    last_m = msci_out[-1] if msci_out else 0
    print(f"\n=== Fertig: {len(dates_out)} Tage EUR-normalisiert. "
          f"Portfolio: {last_p:+.2f}%, MSCI: {last_m:+.2f}% ===", flush=True)


if __name__ == "__main__":
    main()
