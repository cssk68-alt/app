"""
update_performance.py
Holt taegliche Schlusskurse fuer alle Portfolio-Positionen + MSCI World seit
18. Mai 2026 und berechnet kumulative Returns. Yahoo Finance primaer,
Stooq als Fallback.

Wird Mo-Fr ~17:30 UTC (nach EU-Marktschluss) via GitHub Actions ausgefuehrt.

Output: data/performance.json mit Datums-Reihe, Portfolio-%-Return,
MSCI-World-%-Return und Wochenstats fuer aktuelle + letzte Woche.
"""
import calendar
import json
import os
import random
import time
from datetime import date, datetime, timedelta
import requests

BASELINE_DATE = date(2026, 5, 18)
MIN_SUCCESS_TICKERS = 10  # mind. 10 von 12 Portfolio-Tickern muessen klappen

# ticker -> (Yahoo-Symbol, Stooq-Symbol, Portfolio-Gewicht in %)
PORTFOLIO_TICKERS = {
    "SXR8": ("SXR8.DE", "sxr8.de", 20.0),
    "CPXJ": ("CPXJ.L",  "cpxj.uk", 15.0),
    "CSKR": ("CSKR.L",  "cskr.uk",  2.6),
    "IJPA": ("IJPA.L",  "ijpa.uk",  2.4),
    "WHCS": ("WHCS.L",  "whcs.uk", 14.0),
    "AGED": ("AGED.L",  "aged.uk",  5.0),
    "PHAG": ("PHAG.L",  "phag.uk",  6.0),
    "PHPT": ("PHPT.L",  "phpt.uk",  4.6),
    "COPA": ("COPA.L",  "copa.uk",  4.4),
    "EIMI": ("EIMI.L",  "eimi.uk", 14.0),
    "ALV":  ("ALV.DE",  "alv.de",   7.0),
    "ISF":  ("ISF.L",   "isf.uk",   5.0),
}
BENCHMARK = ("IWDA.AS", "iwda.nl")  # iShares Core MSCI World UCITS ETF

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
}


def _date_str(d):
    return d.strftime("%Y-%m-%d")


def fetch_yahoo(symbol, start_d, end_d):
    """Yahoo Finance v8 chart API. Returns dict {YYYY-MM-DD: close_price} or None."""
    start_ts = calendar.timegm(start_d.timetuple())
    end_ts = calendar.timegm((end_d + timedelta(days=1)).timetuple())
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
           f"?period1={start_ts}&period2={end_ts}&interval=1d")
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            return None
        data = r.json()
        if data.get("chart", {}).get("error"):
            return None
        result = (data.get("chart", {}).get("result") or [None])[0]
        if not result:
            return None
        timestamps = result.get("timestamp") or []
        quote = (result.get("indicators", {}).get("quote") or [{}])[0]
        closes = quote.get("close") or []
        prices = {}
        for ts, c in zip(timestamps, closes):
            if c is None:
                continue
            d = date.fromtimestamp(ts)
            prices[_date_str(d)] = float(c)
        return prices if prices else None
    except (requests.RequestException, ValueError, KeyError, IndexError):
        return None


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
                # Stooq liefert YYYY-MM-DD
                if len(d_str) != 10:
                    continue
                c = float(parts[i_close])
                prices[d_str] = c
            except ValueError:
                continue
        return prices if prices else None
    except requests.RequestException:
        return None


def fetch_ticker(name, yahoo_sym, stooq_sym, start_d, end_d):
    """Yahoo zuerst, dann Stooq als Fallback."""
    p = fetch_yahoo(yahoo_sym, start_d, end_d)
    if p and len(p) >= 2:
        print(f"  [{name}] Yahoo OK ({len(p)} Tage)", flush=True)
        return p
    if p:
        print(f"  [{name}] Yahoo zu wenig Daten ({len(p)}), versuche Stooq...", flush=True)
    else:
        print(f"  [{name}] Yahoo fehlgeschlagen, versuche Stooq...", flush=True)
    # kleine Pause, damit Stooq nicht im selben Burst kommt
    time.sleep(0.3 + random.random() * 0.3)
    p = fetch_stooq(stooq_sym, start_d, end_d)
    if p and len(p) >= 2:
        print(f"  [{name}] Stooq OK ({len(p)} Tage)", flush=True)
        return p
    print(f"  [{name}] FEHLGESCHLAGEN (Yahoo+Stooq)", flush=True)
    return None


def first_available(prices, baseline, lookforward=10):
    """Erster verfuegbarer Preis ab baseline (vorwaerts bis lookforward Tage)."""
    for i in range(lookforward):
        key = _date_str(baseline + timedelta(days=i))
        if key in prices:
            return prices[key]
    return None


def forward_fill(prices, all_dates):
    """Liefert Liste paralleler Preise zu all_dates, Wochenende/Feiertage vorwaerts-gefuellt."""
    out = []
    last = None
    for d_str in all_dates:
        if d_str in prices:
            last = prices[d_str]
        out.append(last)
    return out


def calc_week_return(monday, friday, dates, returns):
    """Wochenrendite = letztes Return im Zeitraum - letztes Return vor Wochenstart.
    Wenn Wochenstart vor Baseline liegt, gilt 0% als Startwert (Baseline-Tag).
    """
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
        start_pct = 0.0  # vor Baseline -> Start = 0%
    if end_pct is None:
        return None
    return round(end_pct - start_pct, 4)


def main():
    os.makedirs("data", exist_ok=True)
    today = date.today()
    start = BASELINE_DATE
    print(f"=== Performance Update gestartet ({datetime.now():%Y-%m-%d %H:%M}) ===", flush=True)
    print(f"Baseline: {_date_str(BASELINE_DATE)}  -> heute: {_date_str(today)}", flush=True)

    portfolio_prices = {}
    failed_tickers = []
    for ticker, (yh, st, _w) in PORTFOLIO_TICKERS.items():
        print(f"-> {ticker} (Yahoo: {yh}, Stooq: {st})", flush=True)
        p = fetch_ticker(ticker, yh, st, start, today)
        if p:
            portfolio_prices[ticker] = p
        else:
            failed_tickers.append(ticker)
        time.sleep(0.4 + random.random() * 0.3)

    print(f"\n-> MSCI World (Yahoo: {BENCHMARK[0]}, Stooq: {BENCHMARK[1]})", flush=True)
    msci_prices = fetch_ticker("MSCI", BENCHMARK[0], BENCHMARK[1], start, today)

    n_ok = len(portfolio_prices)
    print(f"\n=== Ergebnis: {n_ok}/{len(PORTFOLIO_TICKERS)} Portfolio-Ticker, "
          f"MSCI: {'OK' if msci_prices else 'FAIL'} ===", flush=True)

    if n_ok < MIN_SUCCESS_TICKERS or not msci_prices:
        print(f"Zu wenig Daten ({n_ok} < {MIN_SUCCESS_TICKERS} oder MSCI fehlt). "
              f"Bestehende performance.json bleibt unveraendert.", flush=True)
        return

    # alle Kalendertage von Baseline bis heute
    all_dates = []
    d = BASELINE_DATE
    while d <= today:
        all_dates.append(_date_str(d))
        d += timedelta(days=1)

    # Baseline-Preise + vorwaertsgefuellte Reihen
    ticker_baselines = {}
    ticker_series = {}
    for ticker, prices in portfolio_prices.items():
        baseline_px = first_available(prices, BASELINE_DATE)
        if not baseline_px or baseline_px <= 0:
            print(f"  [{ticker}] Kein Baseline-Preis", flush=True)
            if ticker not in failed_tickers:
                failed_tickers.append(ticker)
            continue
        ticker_baselines[ticker] = baseline_px
        ticker_series[ticker] = forward_fill(prices, all_dates)

    msci_baseline = first_available(msci_prices, BASELINE_DATE)
    if not msci_baseline or msci_baseline <= 0:
        print("MSCI: Kein Baseline-Preis -> Abbruch", flush=True)
        return
    msci_series = forward_fill(msci_prices, all_dates)

    # Tagesreturns in %
    portfolio_returns = []
    msci_returns = []
    for i in range(len(all_dates)):
        wsum = 0.0
        used = 0.0
        for ticker, series in ticker_series.items():
            px = series[i]
            if px is None:
                continue
            w = PORTFOLIO_TICKERS[ticker][2]
            wsum += w * (px / ticker_baselines[ticker] - 1)
            used += w
        portfolio_returns.append(round(wsum, 4) if used > 0 else None)
        msci_px = msci_series[i]
        msci_returns.append(round((msci_px / msci_baseline - 1) * 100, 4) if msci_px else None)

    # fuehrende None-Tage abschneiden (vor Markteroeffnung)
    first_valid = 0
    for i in range(len(all_dates)):
        if portfolio_returns[i] is not None and msci_returns[i] is not None:
            first_valid = i
            break
    dates_out = all_dates[first_valid:]
    portfolio_out = portfolio_returns[first_valid:]
    msci_out = msci_returns[first_valid:]

    # Wochenstats
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

    out = {
        "_meta": {
            "last_updated": _date_str(today),
            "baseline_date": _date_str(BASELINE_DATE),
            "update_success": True,
            "tickers_ok": len(ticker_series),
            "tickers_total": len(PORTFOLIO_TICKERS),
            "failed_tickers": failed_tickers,
            "source": "Yahoo Finance primaer, Stooq Fallback",
        },
        "dates": dates_out,
        "portfolio": portfolio_out,
        "msci_world": msci_out,
        "weekly": weekly,
    }

    with open("data/performance.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    last_p = portfolio_out[-1] if portfolio_out else 0
    last_m = msci_out[-1] if msci_out else 0
    print(f"\n=== Fertig: {len(dates_out)} Tage. "
          f"Portfolio: {last_p:+.2f}%, MSCI: {last_m:+.2f}% ===", flush=True)


if __name__ == "__main__":
    main()
