"""
universe_builder.py - Cache-aware raw NSE universe discovery.

Refresh policy:
- NSE_ALL stock list is fetched weekly, or if the local file is missing.
- Daily runs reuse nse_all_symbols.csv to avoid unnecessary NSE downloads.
- stocks.txt is always rewritten so legacy modules read the current raw universe.
- rejected_universe.csv always records symbols rejected at the raw-universe stage.
"""

from __future__ import annotations

import csv
import os
import re
from typing import Dict, Iterable, List, Tuple

import requests

from cache_policy import mark_universe_refreshed, should_refresh_universe
from config import (
    ALLOWED_NSE_SERIES,
    CACHE_DIR,
    CUSTOM_UNIVERSE_FILE,
    EXCLUDED_NAME_KEYWORDS,
    EXCLUDED_SYMBOL_KEYWORDS,
    NIFTY_500_FILE,
    NSE_ALL_SYMBOLS_FILE,
    NSE_EQUITY_LIST_URL,
    REJECTED_UNIVERSE_FILE,
    SECTOR_MAP,
    STOCKS_FILE,
    UNIVERSE_MODE,
)

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "text/csv,application/csv,text/plain,*/*",
}


def _norm_symbol(raw: str) -> str:
    s = (raw or "").strip().upper()
    s = s.replace(" ", "").replace("&", "-")

    if not s:
        return ""

    if s.startswith("^") or s.endswith(".NS") or s.endswith(".BO"):
        return s

    return f"{s}.NS"


def _base_symbol(symbol: str) -> str:
    return symbol.upper().replace(".NS", "").replace(".BO", "")


def _read_simple_file(path: str, source: str) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []

    if not os.path.exists(path):
        return rows

    with open(path, "r", newline="", encoding="utf-8", errors="ignore") as f:
        sample = f.read(2048)
        f.seek(0)

        if "," in sample and "SYMBOL" in sample.upper():
            reader = csv.DictReader(f)

            for r in reader:
                sym = _norm_symbol(
                    r.get("SYMBOL")
                    or r.get("symbol")
                    or r.get("Ticker")
                    or r.get("ticker")
                    or ""
                )

                if sym:
                    rows.append(
                        {
                            "symbol": sym,
                            "company_name": r.get(
                                "NAME OF COMPANY",
                                r.get("COMPANY_NAME", r.get("company_name", "")),
                            ),
                            "series": r.get("SERIES", r.get("series", "")),
                            "source": source,
                        }
                    )
        else:
            for line in f:
                sym = _norm_symbol(line.strip().split(",")[0])

                if sym:
                    rows.append(
                        {
                            "symbol": sym,
                            "company_name": "",
                            "series": "",
                            "source": source,
                        }
                    )

    return rows


def _fetch_nse_equity_list() -> List[Dict[str, str]]:
    try:
        resp = requests.get(NSE_EQUITY_LIST_URL, headers=HEADERS, timeout=30)
        resp.raise_for_status()

        reader = csv.DictReader(resp.text.splitlines())
        rows: List[Dict[str, str]] = []

        for r in reader:
            sym = _norm_symbol(r.get("SYMBOL", ""))

            if not sym:
                continue

            rows.append(
                {
                    "symbol": sym,
                    "company_name": r.get("NAME OF COMPANY", ""),
                    "series": r.get(" SERIES", r.get("SERIES", "")).strip(),
                    "source": "NSE_EQUITY_LIST",
                }
            )

        return rows

    except Exception as exc:
        print(f"[WARN] NSE equity list fetch failed: {exc}")
        return []


def _cache_symbols() -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []

    if not os.path.isdir(CACHE_DIR):
        return rows

    for name in os.listdir(CACHE_DIR):
        if not name.endswith(".json"):
            continue

        sym = _norm_symbol(name[:-5])

        if sym and not sym.startswith("^"):
            rows.append(
                {
                    "symbol": sym,
                    "company_name": "",
                    "series": "",
                    "source": "CACHE",
                }
            )

    return rows


def _sector_map_symbols() -> List[Dict[str, str]]:
    seen = set()
    rows: List[Dict[str, str]] = []

    for symbols in SECTOR_MAP.values():
        for sym in symbols:
            ns = _norm_symbol(sym)

            if ns and ns not in seen:
                rows.append(
                    {
                        "symbol": ns,
                        "company_name": "",
                        "series": "",
                        "source": "SECTOR_MAP",
                    }
                )
                seen.add(ns)

    return rows


def _is_excluded(row: Dict[str, str]) -> Tuple[bool, str]:
    sym = row.get("symbol", "")
    base = _base_symbol(sym)
    name = (row.get("company_name") or "").upper()
    series = (row.get("series") or "").strip().upper()

    if not sym or sym.startswith("^"):
        return True, "invalid_or_index_symbol"

    if series and series not in ALLOWED_NSE_SERIES:
        return True, f"excluded_series_{series}"

    if any(k in base for k in EXCLUDED_SYMBOL_KEYWORDS):
        return True, "excluded_symbol_keyword"

    if any(k in name for k in EXCLUDED_NAME_KEYWORDS):
        return True, "excluded_name_keyword"

    if not re.match(r"^[A-Z0-9][A-Z0-9\-_.]*\.NS$", sym):
        return True, "suspicious_symbol_format"

    return False, ""


def _dedupe(rows: Iterable[Dict[str, str]]) -> List[Dict[str, str]]:
    out: Dict[str, Dict[str, str]] = {}

    for row in rows:
        sym = _norm_symbol(row.get("symbol", ""))

        if not sym:
            continue

        existing = out.get(sym)

        if existing is None or (not existing.get("company_name") and row.get("company_name")):
            out[sym] = {
                "symbol": sym,
                "company_name": row.get("company_name", ""),
                "series": row.get("series", ""),
                "source": row.get("source", "LOCAL"),
            }

    return sorted(out.values(), key=lambda x: x["symbol"])


def _load_cached_nse_all() -> List[Dict[str, str]]:
    rows = _read_simple_file(NSE_ALL_SYMBOLS_FILE, "CACHED_NSE_ALL")

    if rows:
        print(f"Using cached universe file: {NSE_ALL_SYMBOLS_FILE} ({len(rows)} rows)")

    return rows


def build_universe() -> Tuple[List[Dict[str, str]], List[Dict[str, str]], str]:
    mode = UNIVERSE_MODE.upper()
    raw: List[Dict[str, str]] = []
    source_used = "UNKNOWN"

    if mode == "CUSTOM_LIST":
        raw = _read_simple_file(CUSTOM_UNIVERSE_FILE, "CUSTOM_LIST")
        source_used = "CUSTOM_LIST"

    elif mode == "NIFTY_500":
        raw = _read_simple_file(NIFTY_500_FILE, "NIFTY_500")
        source_used = "NIFTY_500_LOCAL"

    elif mode == "NSE_ALL":
        refresh = should_refresh_universe()

        if refresh:
            print("Universe refresh policy: fetching latest NSE equity list")
            raw = _fetch_nse_equity_list()
            source_used = "NSE_EQUITY_LIST" if raw else ""

        else:
            print("Universe refresh policy: using cached weekly universe")
            raw = _load_cached_nse_all()
            source_used = "CACHED_NSE_ALL" if raw else ""

        if not raw:
            raw = _load_cached_nse_all()
            source_used = "CACHED_NSE_ALL" if raw else source_used

        if not raw:
            raw = _read_simple_file(STOCKS_FILE, "STOCKS_FILE")
            source_used = "STOCKS_FILE" if raw else source_used

        if not raw:
            raw = _cache_symbols()
            source_used = "CACHE" if raw else source_used

        raw.extend(_sector_map_symbols())

    else:
        raw = _read_simple_file(STOCKS_FILE, "STOCKS_FILE")
        source_used = "STOCKS_FILE"

    accepted: List[Dict[str, str]] = []
    rejected: List[Dict[str, str]] = []

    for row in _dedupe(raw):
        excluded, reason = _is_excluded(row)

        if excluded:
            rejected.append(
                {
                    "symbol": row.get("symbol", ""),
                    "reason": reason,
                    "failed_stage": "RAW_UNIVERSE",
                    "missing_metric": "",
                    "source": row.get("source", ""),
                }
            )
        else:
            accepted.append(row)

    return accepted, rejected, source_used or mode


def write_outputs(
    accepted: List[Dict[str, str]],
    rejected: List[Dict[str, str]],
    source_used: str,
) -> None:
    with open(NSE_ALL_SYMBOLS_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["SYMBOL", "COMPANY_NAME", "SERIES", "SOURCE"],
        )
        writer.writeheader()

        for row in accepted:
            writer.writerow(
                {
                    "SYMBOL": row["symbol"],
                    "COMPANY_NAME": row.get("company_name", ""),
                    "SERIES": row.get("series", ""),
                    "SOURCE": row.get("source", ""),
                }
            )

    with open(STOCKS_FILE, "w", encoding="utf-8") as f:
        for row in accepted:
            f.write(row["symbol"] + "\n")

    with open(REJECTED_UNIVERSE_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["symbol", "reason", "failed_stage", "missing_metric", "source"],
        )
        writer.writeheader()

        for row in rejected:
            writer.writerow(row)

    mark_universe_refreshed(len(accepted), source_used)


def main() -> None:
    accepted, rejected, source_used = build_universe()
    write_outputs(accepted, rejected, source_used)

    print("\nUNIVERSE BUILDER")
    print("=" * 80)
    print(f"Mode          : {UNIVERSE_MODE}")
    print(f"Source used   : {source_used}")
    print(f"Accepted      : {len(accepted)}")
    print(f"Rejected      : {len(rejected)}")
    print(f"Saved         : {NSE_ALL_SYMBOLS_FILE}, {STOCKS_FILE}, {REJECTED_UNIVERSE_FILE}")


if __name__ == "__main__":
    main()
