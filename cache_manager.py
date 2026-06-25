"""
cache_manager.py - Smart cache-aware Yahoo Finance OHLCV refresh.

This version is compatible with the current cache_policy.py used by the
manual-portfolio/report-cleanup build.

Refresh policy:
- Daily: indices, manual active holdings, previously tradable universe,
  and high-quality candidates.
- Weekly: full NSE_ALL universe refresh when the cache policy says it is due.
- Smart skip: if an existing Yahoo cache already contains the latest expected
  completed NSE daily candle, do not download that symbol again on repeated
  manual/GitHub runs.
"""

from __future__ import annotations

import csv
import json
import os
import time
from typing import Any, Dict, List, Tuple
from urllib.parse import quote

import requests

from cache_policy import (
    cache_file,
    dedupe_symbols,
    expected_latest_trading_date,
    extract_latest_candle_info_from_data,
    load_cache_manifest,
    mark_full_cache_refresh,
    mark_symbol_cached,
    read_active_holdings,
    read_high_quality_symbols,
    read_previously_tradable_symbols,
    read_symbols_auto,
    save_cache_manifest,
    should_refresh_price_cache,
    should_run_full_cache_refresh,
    today_ist_str,
)
from config import (
    ACTIVE_HOLDING_CACHE_MAX_AGE_HOURS,
    CACHE_DAILY_TRADABLE_LIMIT,
    CACHE_DIR,
    CACHE_HIGH_QUALITY_LIMIT,
    CACHE_INDICES,
    CACHE_MAX_FAILURES,
    CACHE_PRICE_INTERVAL,
    CACHE_PRICE_RANGE,
    CACHE_REFRESH_REPORT_FILE,
    CACHE_REFRESH_SUMMARY_FILE,
    CACHE_REQUEST_SLEEP_SECONDS,
    CACHE_REQUEST_TIMEOUT,
    CANDIDATE_CACHE_MAX_AGE_HOURS,
    FORCE_PRICE_REFRESH,
    INDEX_CACHE_MAX_AGE_HOURS,
    NSE_ALL_SYMBOLS_FILE,
    PRICE_CACHE_MAX_AGE_HOURS,
    STOCKS_FILE,
)

HEADERS = {"User-Agent": "Mozilla/5.0"}


def _valid_chart(data: Dict[str, Any]) -> bool:
    """Return True when Yahoo chart payload has usable daily bars."""
    try:
        result = data.get("chart", {}).get("result")
        if not result:
            return False

        timestamps = result[0].get("timestamp") or []
        quote_data = result[0].get("indicators", {}).get("quote", [{}])[0]
        closes = quote_data.get("close") or []

        return bool(timestamps and closes and any(x is not None for x in closes))
    except Exception:
        return False


def _download_symbol(symbol: str) -> Tuple[bool, str, Any, str]:
    """Download one Yahoo chart payload.

    Returns:
        (ok, detail, latest_timestamp, latest_candle_date)
    """
    safe_symbol = quote(symbol, safe="")
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{safe_symbol}"
        f"?range={CACHE_PRICE_RANGE}&interval={CACHE_PRICE_INTERVAL}"
    )

    try:
        response = requests.get(url, headers=HEADERS, timeout=CACHE_REQUEST_TIMEOUT)
        if response.status_code != 200:
            return False, f"HTTP_{response.status_code}", "", ""

        data = response.json()
        if not _valid_chart(data):
            return False, "invalid_chart_payload", "", ""

        info = extract_latest_candle_info_from_data(data)
        latest_ts = info.get("latest_timestamp", "")
        latest_date = str(info.get("latest_candle_date", "") or "")

        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(cache_file(symbol), "w", encoding="utf-8") as f:
            json.dump(data, f)

        return True, "ok", latest_ts, latest_date

    except Exception as exc:
        return False, str(exc), "", ""


def _symbols_for_daily_refresh() -> Dict[str, List[str]]:
    """Build daily refresh groups.

    Manual holdings are read through cache_policy.read_active_holdings(), which
    now uses MANUAL_PORTFOLIO_JSON first and ignores stale virtual holdings in
    manual portfolio mode.
    """
    return {
        "INDEX": dedupe_symbols(CACHE_INDICES),
        "ACTIVE_HOLDING": read_active_holdings(),
        "PREVIOUSLY_TRADABLE": read_previously_tradable_symbols(limit=CACHE_DAILY_TRADABLE_LIMIT),
        "HIGH_QUALITY": read_high_quality_symbols(limit=CACHE_HIGH_QUALITY_LIMIT),
    }


def _symbols_for_full_refresh() -> List[str]:
    symbols: List[str] = []
    for path in (NSE_ALL_SYMBOLS_FILE, STOCKS_FILE):
        symbols.extend(read_symbols_auto(path))
    return dedupe_symbols(symbols)


def _plan_refresh(full_refresh: bool) -> List[Tuple[str, str, float, bool]]:
    """Return list of (symbol, group, max_age_hours, force_download)."""
    plan: List[Tuple[str, str, float, bool]] = []
    seen = set()

    daily_groups = _symbols_for_daily_refresh()
    group_age = {
        "INDEX": INDEX_CACHE_MAX_AGE_HOURS,
        "ACTIVE_HOLDING": ACTIVE_HOLDING_CACHE_MAX_AGE_HOURS,
        "PREVIOUSLY_TRADABLE": PRICE_CACHE_MAX_AGE_HOURS,
        "HIGH_QUALITY": CANDIDATE_CACHE_MAX_AGE_HOURS,
    }

    for group, symbols in daily_groups.items():
        for symbol in symbols:
            if not symbol or symbol in seen:
                continue
            seen.add(symbol)
            plan.append((symbol, group, group_age[group], FORCE_PRICE_REFRESH))

    if full_refresh:
        for symbol in _symbols_for_full_refresh():
            if not symbol or symbol in seen:
                continue
            seen.add(symbol)
            plan.append((symbol, "FULL_WEEKLY", PRICE_CACHE_MAX_AGE_HOURS, FORCE_PRICE_REFRESH))

    return plan


def _short_detail(decision: Dict[str, Any]) -> str:
    parts = [str(decision.get("reason", ""))]

    latest = decision.get("latest_candle_date") or ""
    expected = decision.get("expected_candle_date") or ""
    age = decision.get("age_hours")

    if latest or expected:
        parts.append(f"latest={latest or 'NA'} expected={expected or 'NA'}")

    if age is not None:
        try:
            parts.append(f"age={float(age):.1f}h")
        except Exception:
            pass

    return " | ".join([p for p in parts if p])


def main() -> int:
    os.makedirs(CACHE_DIR, exist_ok=True)

    manifest = load_cache_manifest()
    expected_date = expected_latest_trading_date().isoformat()
    full_refresh = should_run_full_cache_refresh()
    plan = _plan_refresh(full_refresh)

    print("\nCACHE MANAGER")
    print("=" * 80)
    print(f"Date                    : {today_ist_str()}")
    print(f"Expected daily candle    : {expected_date}")
    print(f"Full weekly refresh      : {full_refresh}")
    print(f"Symbols in refresh plan  : {len(plan)}")

    rows: List[Dict[str, Any]] = []
    downloaded = 0
    skipped = 0
    failed = 0
    skip_reason_counts: Dict[str, int] = {}

    for i, (symbol, group, max_age, force) in enumerate(plan, start=1):
        path = cache_file(symbol)
        decision = should_refresh_price_cache(
            path=path,
            max_age_hours=max_age,
            force=force,
        )

        if not decision.get("refresh", True):
            skipped += 1
            reason = str(decision.get("reason", "SKIP"))
            skip_reason_counts[reason] = skip_reason_counts.get(reason, 0) + 1
            rows.append(
                {
                    "symbol": symbol,
                    "group": group,
                    "action": "SKIP",
                    "status": "OK",
                    "detail": _short_detail(decision),
                    "latest_candle_date": decision.get("latest_candle_date", ""),
                    "expected_candle_date": decision.get("expected_candle_date", expected_date),
                }
            )
            continue

        print(f"[{i}/{len(plan)}] {symbol} ({group}) - {decision.get('reason', 'refresh')}")

        ok, detail, latest_ts, latest_date_str = _download_symbol(symbol)
        expected_for_symbol = str(decision.get("expected_candle_date", expected_date))

        mark_symbol_cached(
            manifest,
            symbol,
            group=group,
            latest_timestamp=latest_ts,
            latest_candle_date=latest_date_str,
            expected_candle_date=expected_for_symbol,
            ok=ok,
            error="" if ok else detail,
        )

        if ok:
            downloaded += 1
            action_detail = detail
            if latest_date_str and latest_date_str < expected_for_symbol:
                action_detail = f"ok_but_no_new_candle latest={latest_date_str} expected={expected_for_symbol}"

            rows.append(
                {
                    "symbol": symbol,
                    "group": group,
                    "action": "DOWNLOAD",
                    "status": "OK",
                    "detail": action_detail,
                    "latest_candle_date": latest_date_str,
                    "expected_candle_date": expected_for_symbol,
                }
            )
        else:
            failed += 1
            rows.append(
                {
                    "symbol": symbol,
                    "group": group,
                    "action": "DOWNLOAD",
                    "status": "FAIL",
                    "detail": detail,
                    "latest_candle_date": "",
                    "expected_candle_date": expected_for_symbol,
                }
            )
            print(f"  failed: {detail}")

            if failed >= CACHE_MAX_FAILURES:
                print(f"Stopping early because failures reached CACHE_MAX_FAILURES={CACHE_MAX_FAILURES}")
                break

        time.sleep(CACHE_REQUEST_SLEEP_SECONDS)

    if full_refresh:
        mark_full_cache_refresh(manifest, symbol_count=len(_symbols_for_full_refresh()))

    manifest.setdefault("runs", [])
    manifest["runs"].append(
        {
            "date": today_ist_str(),
            "expected_daily_candle": expected_date,
            "full_refresh": full_refresh,
            "planned": len(plan),
            "downloaded": downloaded,
            "skipped": skipped,
            "failed": failed,
            "skip_reason_counts": skip_reason_counts,
        }
    )
    manifest["runs"] = manifest["runs"][-30:]
    save_cache_manifest(manifest)

    with open(CACHE_REFRESH_REPORT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "symbol",
                "group",
                "action",
                "status",
                "detail",
                "latest_candle_date",
                "expected_candle_date",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    top_skips = sorted(skip_reason_counts.items(), key=lambda kv: kv[1], reverse=True)[:12]

    summary = [
        "CACHE REFRESH SUMMARY",
        "=" * 80,
        f"Date: {today_ist_str()}",
        f"Expected daily candle: {expected_date}",
        f"Full weekly refresh: {full_refresh}",
        f"Planned symbols: {len(plan)}",
        f"Downloaded: {downloaded}",
        f"Skipped: {skipped}",
        f"Failed: {failed}",
        "",
        "Top skip reasons:",
    ]

    if top_skips:
        summary.extend([f"  {reason}: {count}" for reason, count in top_skips])
    else:
        summary.append("  None")

    summary.extend(
        [
            "",
            "Policy:",
            "Daily groups: INDEX, ACTIVE_HOLDING, PREVIOUSLY_TRADABLE, HIGH_QUALITY",
            "Weekly group: FULL_WEEKLY NSE_ALL universe",
            "Smart skip: if latest cached daily candle is current, do not download again",
            "Manual portfolio: active holdings come from MANUAL_PORTFOLIO_JSON in manual mode",
        ]
    )

    with open(CACHE_REFRESH_SUMMARY_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(summary) + "\n")

    print("\n" + "\n".join(summary))

    # Cache failures are logged but should not kill the whole pipeline unless an
    # unexpected Python exception happens. Later data_quality.py will reject
    # symbols whose cache is missing or stale.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
