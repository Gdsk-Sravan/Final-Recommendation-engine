"""
news_fetcher_v2.py - Fast, cached, candidate-limited RSS news fetcher.

Why this exists
---------------
After expanding to NSE_ALL, fetching news for every qualified stock can take
20-40 minutes. This fetcher only fetches news for the symbols written by
pre_news_selector.py:

  news_fetch_universe.txt

That file normally contains:
  - active holdings, always
  - top deterministic candidates only, usually 30-40 names

Features
--------
- Uses local per-symbol cache in news_cache/.
- Skips network calls if news cache is fresh.
- Parallel fetch with ThreadPoolExecutor.
- Falls back to stale cache when Google RSS fails, if enabled.
- Writes news_headlines.csv in the existing format used by news_engine_v2.py.
"""

from __future__ import annotations

import csv
import json
import os
import re
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Dict, Iterable, List, Tuple
from urllib.parse import quote

import requests

from config import (
    NEWS_ALLOW_STALE_CACHE_ON_FAILURE,
    NEWS_CACHE_DIR,
    NEWS_CACHE_TTL_HOURS,
    NEWS_FETCH_MAX_WORKERS,
    NEWS_FETCH_REPORT_FILE,
    NEWS_FETCH_SUMMARY_FILE,
    NEWS_FETCH_TIMEOUT_SECONDS,
    NEWS_FETCH_TOP_N,
    NEWS_FETCH_UNIVERSE_FILE,
    NEWS_HEADLINES_FILE,
    NEWS_MAX_HEADLINES_PER_SYMBOL,
    QUALIFIED_FILE,
)

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/rss+xml,application/xml,text/xml,*/*",
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_str() -> str:
    return _utc_now().strftime("%Y-%m-%d %H:%M:%S")


def _norm_symbol(raw: str) -> str:
    s = (raw or "").strip().upper()
    if not s:
        return ""
    if s.startswith("^") or s.endswith(".NS") or s.endswith(".BO"):
        return s
    return f"{s}.NS"


def _base_symbol(symbol: str) -> str:
    return symbol.upper().replace(".NS", "").replace(".BO", "")


def _dedupe(symbols: Iterable[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for raw in symbols:
        sym = _norm_symbol(str(raw))
        if not sym or sym in seen:
            continue
        seen.add(sym)
        out.append(sym)
    return out


def _read_symbols(path: str) -> List[str]:
    if not os.path.exists(path):
        return []
    symbols: List[str] = []
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            symbols.append(line.split(",")[0].strip())
    return _dedupe(symbols)


def _load_fetch_universe() -> List[str]:
    symbols = _read_symbols(NEWS_FETCH_UNIVERSE_FILE)
    source = NEWS_FETCH_UNIVERSE_FILE

    if not symbols:
        symbols = _read_symbols(QUALIFIED_FILE)[:NEWS_FETCH_TOP_N]
        source = f"{QUALIFIED_FILE} fallback"

    symbols = _dedupe(symbols)[:NEWS_FETCH_TOP_N]
    print(f"News universe source: {source} | symbols={len(symbols)}")
    return symbols


def _parse_date(raw: str) -> str:
    try:
        dt = parsedate_to_datetime(raw)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        pass

    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%d %b %Y %H:%M:%S %z"):
        try:
            dt = datetime.strptime(raw.strip(), fmt)
            return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            continue

    return _utc_now_str()


def _clean_title(title: str) -> str:
    return re.sub(r"\s+", " ", title or "").strip()


def _cache_path(symbol: str) -> str:
    os.makedirs(NEWS_CACHE_DIR, exist_ok=True)
    safe = symbol.replace("/", "_").replace("\\", "_")
    return os.path.join(NEWS_CACHE_DIR, f"{safe}.json")


def _load_cache(symbol: str) -> Tuple[bool, List[Dict[str, str]], str]:
    path = _cache_path(symbol)
    if not os.path.exists(path):
        return False, [], "missing"

    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)

        fetched_at_raw = payload.get("fetched_at", "")
        fetched_at = datetime.fromisoformat(fetched_at_raw.replace("Z", "+00:00"))
        if fetched_at.tzinfo is None:
            fetched_at = fetched_at.replace(tzinfo=timezone.utc)

        age_hours = (_utc_now() - fetched_at.astimezone(timezone.utc)).total_seconds() / 3600.0
        rows = payload.get("rows", []) if isinstance(payload.get("rows"), list) else []
        fresh = age_hours <= NEWS_CACHE_TTL_HOURS
        return fresh, rows, f"age_hours={age_hours:.2f}"

    except Exception as exc:
        return False, [], f"cache_error={exc}"


def _write_cache(symbol: str, rows: List[Dict[str, str]], status: str) -> None:
    payload = {
        "symbol": symbol,
        "fetched_at": _utc_now().isoformat(),
        "status": status,
        "rows": rows,
    }
    with open(_cache_path(symbol), "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def _fetch_google_rss(symbol: str) -> List[Dict[str, str]]:
    search_term = _base_symbol(symbol)
    query = quote(f"{search_term} NSE India stock")
    url = f"https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en"

    response = requests.get(url, headers=HEADERS, timeout=NEWS_FETCH_TIMEOUT_SECONDS)
    response.raise_for_status()

    root = ET.fromstring(response.text)
    seen = set()
    rows: List[Dict[str, str]] = []

    for item in root.findall(".//item"):
        if len(rows) >= NEWS_MAX_HEADLINES_PER_SYMBOL:
            break

        title_el = item.find("title")
        date_el = item.find("pubDate")

        if title_el is None or not title_el.text:
            continue

        headline = _clean_title(title_el.text)
        if not headline:
            continue

        key = headline.lower()
        if key in seen:
            continue
        seen.add(key)

        date_str = _parse_date(date_el.text) if date_el is not None and date_el.text else _utc_now_str()
        rows.append(
            {
                "Symbol": symbol,
                "Date": date_str,
                "Headline": headline,
                "Source": "GoogleNewsRSS",
                "FetchStatus": "NETWORK",
            }
        )

    return rows


def _fetch_or_cache(symbol: str) -> Tuple[str, List[Dict[str, str]], str, str]:
    fresh, cached_rows, cache_detail = _load_cache(symbol)
    if fresh:
        rows = []
        for row in cached_rows:
            r = dict(row)
            r["FetchStatus"] = "CACHE_FRESH"
            rows.append(r)
        return symbol, rows, "CACHE_FRESH", cache_detail

    try:
        rows = _fetch_google_rss(symbol)
        _write_cache(symbol, rows, "OK")
        return symbol, rows, "NETWORK_OK", f"rows={len(rows)}"

    except Exception as exc:
        if NEWS_ALLOW_STALE_CACHE_ON_FAILURE and cached_rows:
            rows = []
            for row in cached_rows:
                r = dict(row)
                r["FetchStatus"] = "CACHE_STALE_FALLBACK"
                rows.append(r)
            return symbol, rows, "STALE_CACHE_USED", str(exc)

        return symbol, [], "FAILED", str(exc)


def _write_outputs(all_rows: List[Dict[str, str]], report_rows: List[Dict[str, str]]) -> None:
    with open(NEWS_HEADLINES_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["Symbol", "Date", "Headline", "Source", "FetchStatus"])
        writer.writeheader()
        for row in all_rows:
            writer.writerow({
                "Symbol": row.get("Symbol", ""),
                "Date": row.get("Date", ""),
                "Headline": row.get("Headline", ""),
                "Source": row.get("Source", ""),
                "FetchStatus": row.get("FetchStatus", ""),
            })

    with open(NEWS_FETCH_REPORT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["symbol", "status", "headline_count", "detail"])
        writer.writeheader()
        writer.writerows(report_rows)


def main() -> None:
    started = time.time()
    symbols = _load_fetch_universe()

    print("\nNEWS FETCHER V2 - CANDIDATE LIMITED")
    print("=" * 80)
    print(f"Max symbols       : {NEWS_FETCH_TOP_N}")
    print(f"Symbols selected  : {len(symbols)}")
    print(f"Cache TTL hours   : {NEWS_CACHE_TTL_HOURS}")
    print(f"Workers           : {NEWS_FETCH_MAX_WORKERS}")

    all_rows: List[Dict[str, str]] = []
    report_rows: List[Dict[str, str]] = []

    if not symbols:
        _write_outputs([], [])
        print("[WARN] No symbols selected for news fetch.")
        return

    workers = max(1, min(NEWS_FETCH_MAX_WORKERS, len(symbols)))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_fetch_or_cache, symbol): symbol for symbol in symbols}
        for future in as_completed(futures):
            symbol = futures[future]
            try:
                sym, rows, status, detail = future.result()
            except Exception as exc:
                sym, rows, status, detail = symbol, [], "FAILED", str(exc)

            all_rows.extend(rows)
            report_rows.append(
                {
                    "symbol": sym,
                    "status": status,
                    "headline_count": len(rows),
                    "detail": detail,
                }
            )
            print(f"  {sym:<24} {status:<20} headlines={len(rows):>2}  {detail}")

    # Keep output deterministic by symbol order from the selector.
    order = {sym: i for i, sym in enumerate(symbols)}
    all_rows.sort(key=lambda r: (order.get(r.get("Symbol", ""), 10_000), r.get("Date", "")), reverse=False)
    report_rows.sort(key=lambda r: order.get(r.get("symbol", ""), 10_000))

    _write_outputs(all_rows, report_rows)

    elapsed = time.time() - started
    ok_count = sum(1 for r in report_rows if r["status"] in ("NETWORK_OK", "CACHE_FRESH", "STALE_CACHE_USED"))
    fail_count = sum(1 for r in report_rows if r["status"] == "FAILED")

    summary = [
        "NEWS FETCH SUMMARY",
        "=" * 80,
        f"Symbols selected: {len(symbols)}",
        f"Headline rows: {len(all_rows)}",
        f"OK symbols: {ok_count}",
        f"Failed symbols: {fail_count}",
        f"Elapsed seconds: {elapsed:.1f}",
        f"Output: {NEWS_HEADLINES_FILE}",
        f"Report: {NEWS_FETCH_REPORT_FILE}",
    ]
    with open(NEWS_FETCH_SUMMARY_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(summary) + "\n")

    print("\n" + "\n".join(summary))


if __name__ == "__main__":
    main()
