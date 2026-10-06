"""
Mine to Model: daily stock update.

Runs every morning (GitHub Actions) and:
  1. Fetches price, previous close and analyst targets for every ticker in data/tickers.json
  2. Writes data/stocks.json (what the website reads) and a dated copy in data/history/
  3. Notes which analyst targets and ratings changed since the last update
  4. (Optional) Sends Telegram alerts for watchlist stocks at or below your buy price

Data source: Yahoo Finance via the free `yfinance` library (no API key).
Optional backup: set FMP_API_KEY to use Financial Modeling Prep for US tickers instead.

Environment variables (set as GitHub Actions secrets; all optional):
  FMP_API_KEY                 use Financial Modeling Prep for US tickers
  SUPABASE_URL                your Supabase project URL (for watchlist alerts)
  SUPABASE_SERVICE_ROLE_KEY   Supabase service role key (server-side only, never in the website)
  TELEGRAM_BOT_TOKEN          bot token from @BotFather
  TELEGRAM_CHAT_ID            your chat id with that bot
  MTM_FORCE=1                 run even if it's not 6am Pacific (manual runs set this automatically)
  MTM_MOCK=1                  don't call any data source; nudge the existing numbers (for testing)
"""

import datetime as dt
import json
import os
import random
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
PACIFIC = ZoneInfo("America/Los_Angeles")
RUN_HOUR_PACIFIC = 6

RATINGS = {
    "strong_buy": "Strong Buy",
    "buy": "Buy",
    "hold": "Hold",
    "underperform": "Underperform",
    "sell": "Sell",
    "strong_sell": "Strong Sell",
}


def log(*args):
    print(*args, flush=True)


def num(v):
    """Return a positive float, or None for missing/zero/garbage values."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f or f <= 0:  # NaN or not positive
        return None
    return round(f, 4)


# ---------------------------------------------------------------- schedule guard

def should_run(now_pacific, previous):
    """GitHub cron runs in UTC, so the workflow fires at 13:00 and 14:00 UTC.
    Only the run that lands in the 6am Pacific hour does the work (PDT or PST),
    and never twice on the same Pacific date."""
    if os.environ.get("MTM_FORCE") == "1" or os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch":
        return True
    if now_pacific.hour != RUN_HOUR_PACIFIC:
        log(f"It's {now_pacific:%H:%M} Pacific, not the 6am hour. Skipping this run.")
        return False
    if previous and previous.get("asof") == now_pacific.date().isoformat() and previous.get("source", "").startswith(("Yahoo", "Financial")):
        log("Already updated today. Skipping.")
        return False
    return True


# ---------------------------------------------------------------- data sources

def fetch_yahoo(symbol):
    import yfinance as yf  # imported here so mock runs don't need it

    info = None
    for attempt in range(3):
        try:
            info = yf.Ticker(symbol).info or {}
            if info:
                break
        except Exception as e:  # network hiccups, rate limits
            log(f"  {symbol}: attempt {attempt + 1} failed ({e})")
        time.sleep(2 * (attempt + 1))
    if not info:
        return None
    px = num(info.get("regularMarketPrice")) or num(info.get("currentPrice"))
    prev = num(info.get("regularMarketPreviousClose")) or num(info.get("previousClose"))
    if not px:
        return None
    return {
        "px": px,
        "prev": prev,
        "avg": num(info.get("targetMeanPrice")),
        "lo": num(info.get("targetLowPrice")),
        "hi": num(info.get("targetHighPrice")),
        "n": int(info["numberOfAnalystOpinions"]) if info.get("numberOfAnalystOpinions") else None,
        "rating": RATINGS.get(str(info.get("recommendationKey") or "").lower()),
        "fpe": num(info.get("forwardPE")),
        "currency": info.get("currency") or "USD",
    }


def http_json(url, data=None, headers=None, method=None):
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read().decode("utf-8")
        return json.loads(body) if body else None


def fetch_fmp(symbol, key):
    base = "https://financialmodelingprep.com/stable/"
    q = urllib.parse.urlencode({"symbol": symbol, "apikey": key})
    quote = http_json(f"{base}quote?{q}") or []
    if not quote:
        return None
    quote = quote[0]
    tgt = (http_json(f"{base}price-target-consensus?{q}") or [{}])
    tgt = tgt[0] if tgt else {}
    grades = (http_json(f"{base}grades-consensus?{q}") or [{}])
    grades = grades[0] if grades else {}
    n = sum(int(grades.get(k) or 0) for k in ("strongBuy", "buy", "hold", "sell", "strongSell")) or None
    px = num(quote.get("price"))
    if not px:
        return None
    return {
        "px": px,
        "prev": num(quote.get("previousClose")),
        "avg": num(tgt.get("targetConsensus")),
        "lo": num(tgt.get("targetLow")),
        "hi": num(tgt.get("targetHigh")),
        "n": n,
        "rating": grades.get("consensus"),
        "fpe": None,
        "currency": "USD",
    }


def fetch_mock(old):
    """Testing only: move the last known numbers a little."""
    if not old or not old.get("px"):
        return None
    move = random.uniform(-0.06, 0.06)
    px = round(old["px"] * (1 + move), 2)
    out = {k: old.get(k) for k in ("avg", "lo", "hi", "n", "rating", "fpe", "currency")}
    out.update({"px": px, "prev": old["px"]})
    if old.get("avg") and random.random() < 0.15:
        out["avg"] = round(old["avg"] * random.uniform(0.95, 1.07), 2)
    return out


# ---------------------------------------------------------------- watchlist alerts

def send_telegram(text):
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not (token and chat):
        log("Telegram not set up; skipping message.")
        return False
    body = json.dumps({"chat_id": chat, "text": text, "disable_web_page_preview": True}).encode()
    http_json(f"{os.environ.get('TELEGRAM_API', 'https://api.telegram.org')}/bot{token}/sendMessage", data=body,
              headers={"Content-Type": "application/json"}, method="POST")
    return True


def check_alerts(stocks, today_iso, names):
    url, key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not (url and key):
        log("Supabase not set up; skipping watchlist alerts.")
        return
    headers = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    rows = http_json(f"{url}/rest/v1/watchlist?select=user_id,company_id,ticker,buy_price,alerted_on&buy_price=not.is.null",
                     headers=headers) or []
    hits = []
    for r in rows:
        q = stocks.get(r["company_id"]) or next((v for v in stocks.values() if v.get("symbol") == r.get("ticker")), None)
        if not q or not q.get("px") or q.get("stale"):
            continue
        buy = float(r["buy_price"])
        where = f"user_id=eq.{r['user_id']}&company_id=eq.{urllib.parse.quote(r['company_id'])}"
        if q["px"] <= buy and not r.get("alerted_on"):
            hits.append((r, q, buy))
            http_json(f"{url}/rest/v1/watchlist?{where}", data=json.dumps({"alerted_on": today_iso}).encode(),
                      headers=headers, method="PATCH")
        elif q["px"] > buy and r.get("alerted_on"):
            # price recovered above the buy price: re-arm the alert
            http_json(f"{url}/rest/v1/watchlist?{where}", data=json.dumps({"alerted_on": None}).encode(),
                      headers=headers, method="PATCH")
    if not hits:
        log("No watchlist alerts today.")
        return
    lines = ["Mine to Model: price alerts"]
    for r, q, buy in hits:
        name = names.get(r["company_id"], r["company_id"])
        up = f", analyst avg target {q['avg']:.2f} ({(q['avg'] / q['px'] - 1) * 100:+.0f}%)" if q.get("avg") else ""
        lines.append(f"• {name} ({q['symbol']}) is {q['px']:.2f}, at or below your {buy:.2f} buy price{up}")
    if send_telegram("\n".join(lines)):
        log(f"Sent {len(hits)} alert(s).")


# ---------------------------------------------------------------- main

def main():
    now = dt.datetime.now(PACIFIC)
    prev_path = DATA / "stocks.json"
    previous = json.loads(prev_path.read_text()) if prev_path.exists() else None
    if not should_run(now, previous):
        return 0

    tickers = json.loads((DATA / "tickers.json").read_text())
    names = json.loads((DATA / "names.json").read_text()) if (DATA / "names.json").exists() else {}
    old_stocks = (previous or {}).get("stocks", {})
    mock = os.environ.get("MTM_MOCK") == "1"
    fmp_key = os.environ.get("FMP_API_KEY")

    stocks, failed = {}, []
    for cid, t in tickers.items():
        sym = t.get("yahoo") or t["symbol"]
        old = old_stocks.get(cid)
        try:
            if mock:
                q = fetch_mock(old)
            elif fmp_key and "." not in t["symbol"]:
                q = fetch_fmp(t["symbol"], fmp_key)
            else:
                q = fetch_yahoo(sym)
        except Exception as e:
            log(f"  {sym}: error {e}")
            q = None
        if not q:
            failed.append(sym)
            if old:  # keep yesterday's numbers, marked as not updated
                stocks[cid] = dict(old, stale=True)
            continue
        # sanity check: a target far from the price usually means the source mixed up
        # share classes or currencies on foreign listings (e.g. a London GDR vs the home listing). Drop it.
        if q.get("avg") and "." in sym and not (0.4 <= q["avg"] / q["px"] <= 2.5):
            log(f"  {sym}: ignoring analyst targets ({q['avg']} vs price {q['px']}) as implausible")
            q["avg"] = q["lo"] = q["hi"] = None
            q["n"] = None
        chg = round((q["px"] / q["prev"] - 1) * 100, 2) if q.get("prev") else None
        # keep old target numbers if the source didn't return any today
        for k in ("avg", "lo", "hi", "n", "rating"):
            if q.get(k) in (None, "") and old and old.get(k) and not ("." in sym and k in ("avg", "lo", "hi", "n")):
                q[k] = old[k]
        stocks[cid] = {
            "symbol": t["symbol"], "px": q["px"], "chg1d": chg,
            "avg": q.get("avg"), "lo": q.get("lo"), "hi": q.get("hi"), "n": q.get("n"),
            "rating": q.get("rating"), "fpe": q.get("fpe"), "currency": q.get("currency") or "USD",
            "stale": False, "date_short": f"{now:%b} {now.day}",
        }
        if not mock and not fmp_key:
            time.sleep(0.4)  # be polite to the free data source

    if not stocks:
        log("No data at all; leaving the site unchanged.")
        return 1
    if len(failed) > len(tickers) * 0.5 and not mock:
        log(f"More than half the tickers failed ({len(failed)}). Keeping yesterday's file so the site doesn't go blank.")
        return 1

    # what changed since the last update
    targets, ratings = [], []
    for cid, q in stocks.items():
        o = old_stocks.get(cid)
        if not o or q.get("stale"):
            continue
        if o.get("avg") and q.get("avg") and abs(q["avg"] / o["avg"] - 1) >= 0.01:
            targets.append({"id": cid, "symbol": q["symbol"], "old": o["avg"], "new": q["avg"],
                            "pct": round((q["avg"] / o["avg"] - 1) * 100, 1), "currency": q.get("currency")})
        if o.get("rating") and q.get("rating") and o["rating"] != q["rating"]:
            ratings.append({"id": cid, "symbol": q["symbol"], "old": o["rating"], "new": q["rating"]})
    targets.sort(key=lambda t: -abs(t["pct"]))

    out = {
        "asof": now.date().isoformat(),
        "asof_label": f"{now:%b} {now.day}, {now:%Y}, {now:%-I}:{now:%M}{now:%p}".replace("AM", "am").replace("PM", "pm") + " Pacific",
        "asof_short": f"{now:%b} {now.day}",
        "source": "mock data (test run)" if mock else ("Financial Modeling Prep + Yahoo Finance" if fmp_key else "Yahoo Finance"),
        "stocks": stocks,
        "changes": {
            "prev_asof": (previous or {}).get("asof"),
            "prev_asof_label": (previous or {}).get("asof_label"),
            "targets": targets,
            "ratings": ratings,
        },
        "failed": failed,
    }
    prev_path.write_text(json.dumps(out, indent=1))
    hist = DATA / "history"
    hist.mkdir(exist_ok=True)
    (hist / f"{out['asof']}.json").write_text(json.dumps({k: out[k] for k in ("asof", "stocks")}))
    log(f"Updated {len(stocks) - len(failed)} of {len(tickers)} tickers. "
        f"{len(targets)} target changes, {len(ratings)} rating changes. Failed: {', '.join(failed) or 'none'}")

    if not mock or os.environ.get("MTM_TEST_ALERTS") == "1":
        try:
            check_alerts(stocks, out["asof"], names)
        except Exception as e:  # alerts should never break the daily update
            log(f"Alert check failed: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
