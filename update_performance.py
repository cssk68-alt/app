"""
update_performance.py
Holt taegliche Schlusskurse fuer alle Portfolio-Positionen + MSCI World seit
18. Mai 2026 und berechnet kumulative Returns in EUR.

Jeder Ticker wird in seiner Listing-Waehrung (USD/GBp/EUR) geholt und
ueber tagesgenaue EUR-Kurse (EUR/USD, EUR/GBP) in EUR umgerechnet, bevor
Returns berechnet werden -> faire Vergleichsbasis mit IWDA.AS in EUR
(deine Sparplan-Wallet-Sicht).

Yahoo Finance primaer, Stooq als Fallback.
Wird Mo-Fr ~17:30 UTC (nach EU-Marktschluss) via GitHub Actions ausgefuehrt.
"""
import calendar
import json
import os
import random
import time
from datetime import date, datetime, timedelta
import requests

BASELINE_DATE = date(2026, 5, 18)
MIN_SUCCESS_TICKERS = 10

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
# Wenn Yahoo komplett fehlschlaegt und nur Stooq Daten liefert: bekannte
# Listing-Waehrung pro Ticker (Stooq exposes keine currency).
TICKER_CURRENCY_FALLBACK = {
    "SXR8": "EUR", "CPXJ": "USD", "CSKR": "USD", "IJPA": "USD",
    "WHCS": "USD", "AGED": "USD", "PHAG": "USD", "PHPT": "USD",
    "COPA": "USD", "EIMI": "USD", "ALV":  "EUR", "ISF":  "GBp",
}
BENCHMARK = ("IWDA.AS", "iwda.nl", "IE00B4L5Y983")  # iShares Core MSCI World EUR
BENCHMARK_CURRENCY_FALLBACK = "EUR"

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


def fetch_yahoo(symbol, start_d, end_d):
    """Yahoo Finance v8 chart API. Returns (prices_dict, currency_str) or (None, None)."""
    start_ts = calendar.timegm(start_d.timetuple())
    end_ts = calendar.timegm((end_d + timedelta(days=1)).timetuple())
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
           f"?period1={start_ts}&period2={end_ts}&interval=1d")
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            return None, None
        data = r.json()
        if data.get("chart", {}).get("error"):
            return None, None
        result = (data.get("chart", {}).get("result") or [None])[0]
        if not result:
            return None, None
        currency = (result.get("meta") or {}).get("currency")
        timestamps = result.get("timestamp") or []
        quote = (result.get("indicators", {}).get("quote") or [{}])[0]
        closes = quote.get("close") or []
        prices = {}
        for ts, c in zip(timestamps, closes):
            if c is None:
                continue
            d = date.fromtimestamp(ts)
            prices[_date_str(d)] = float(c)
        return (prices if prices else None), currency
    except (requests.RequestException, ValueError, KeyError, IndexError):
        return None, None


def fetch_stooq(symbol, start_d, end_d):
    """Stooq CSV daily. Returns dict {YYYY-MM-DD: close_price} or None."""
    d1 = start_d.strftime("%Y%m%d")
    d2 = end_d.strftime("%Y%m%d")
    url = f"https://stooq.com/q/d/l/?s={symbol}&d1={d1}&d2={d2}&i=d"
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code != 200:
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
    print(f"  [{name}] FEHLGESCHLAGEN (Yahoo+Stooq)", flush=True)
    return None, None


def fetch_fx(pair_code, start_d, end_d):
    """Holt EUR/X-Kurse (X = USD oder GBP). Returns dict {date: rate} oder None.
    Rate = wieviel X pro 1 EUR (Standard-Quotation EURUSD=1.16 -> 1 EUR = 1.16 USD)."""
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


def main():
    os.makedirs("data", exist_ok=True)
    today = date.today()
    start = BASELINE_DATE
    print(f"=== Performance Update gestartet ({datetime.now():%Y-%m-%d %H:%M}) ===", flush=True)
    print(f"Baseline: {_date_str(BASELINE_DATE)}  -> heute: {_date_str(today)}", flush=True)

    # 1) FX-Kurse holen (kritisch fuer EUR-Normalisierung)
    print("\n--- FX-Kurse (EUR Basis) ---", flush=True)
    fx_usd = fetch_fx("USD", start, today)
    time.sleep(0.4)
    fx_gbp = fetch_fx("GBP", start, today)

    if not fx_usd or not fx_gbp:
        print("FX-Kurse unvollstaendig -> EUR-Normalisierung waere ungenau. "
              "Bestehende performance.json bleibt unveraendert.", flush=True)
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

    if n_ok < MIN_SUCCESS_TICKERS or not msci_prices:
        print(f"Zu wenig Daten -> bestehende performance.json bleibt unveraendert.", flush=True)
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

    # 6) MSCI EUR-konvertieren (IWDA.AS ist typ. EUR -> identity)
    msci_native = forward_fill(msci_prices, all_dates)
    msci_eur = convert_series_to_eur(msci_native, msci_cur or "EUR", fx_usd_series, fx_gbp_series)
    msci_baseline_eur = next((p for p in msci_eur if p is not None), None)
    if not msci_baseline_eur or msci_baseline_eur <= 0:
        print("MSCI: Kein EUR-Baseline -> Abbruch", flush=True)
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

    out = {
        "_meta": {
            "last_updated": _date_str(today),
            "baseline_date": _date_str(BASELINE_DATE),
            "update_success": True,
            "tickers_ok": len(ticker_series_eur),
            "tickers_total": len(PORTFOLIO_TICKERS),
            "failed_tickers": failed_tickers,
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
