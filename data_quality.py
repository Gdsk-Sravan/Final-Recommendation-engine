"""
data_quality.py - Staged data quality and tradability filter.

Reads the raw universe and writes tradable_universe.csv plus an auditable
rejected_universe.csv. It never invents missing metrics: unavailable data is
marked explicitly and the stock is withheld from scoring until data is valid.
"""

import csv
import os
from datetime import datetime, timezone
from typing import Dict, List, Tuple

from config import (
    NSE_ALL_SYMBOLS_FILE,
    STOCKS_FILE,
    TRADABLE_UNIVERSE_FILE,
    REJECTED_UNIVERSE_FILE,
    DATA_QUALITY_REPORT_FILE,
    MIN_HISTORY_DAYS,
    MIN_INDICATOR_HISTORY_DAYS,
    MAX_ZERO_VOLUME_DAYS_60,
    MIN_AVG_VOLUME,
    MIN_AVG_TRADED_VALUE,
    MIN_STOCK_PRICE,
    PENNY_STOCK_PRICE,
    MAX_SINGLE_DAY_MOVE_PCT,
    MAX_AVG_DAILY_MOVE_PCT,
    CACHE_DIR,
)
from data_provider import get_ohlcv, get_timestamps


def _read_symbols() -> List[str]:
    symbols: List[str] = []
    if os.path.exists(NSE_ALL_SYMBOLS_FILE):
        with open(NSE_ALL_SYMBOLS_FILE, "r", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                sym = row.get("SYMBOL") or row.get("symbol")
                if sym:
                    symbols.append(sym.strip())
    elif os.path.exists(STOCKS_FILE):
        with open(STOCKS_FILE, "r") as f:
            symbols = [x.strip() for x in f if x.strip() and not x.startswith("#")]
    return list(dict.fromkeys(symbols))


def _pct(a: float, b: float) -> float:
    return ((a - b) / b * 100.0) if b else 0.0


def _avg(vals: List[float]) -> float:
    return sum(vals) / len(vals) if vals else 0.0


def _cache_has_data() -> bool:
    return os.path.isdir(CACHE_DIR) and any(name.endswith(".json") for name in os.listdir(CACHE_DIR))


def evaluate_symbol(symbol: str) -> Tuple[bool, Dict[str, object]]:
    ohlcv = get_ohlcv(symbol)
    if not ohlcv:
        return False, {
            "symbol": symbol,
            "reason": "missing_ohlcv_cache",
            "failed_stage": "DATA_QUALITY",
            "missing_metric": "OHLCV",
        }

    closes = ohlcv.get("closes", [])
    highs = ohlcv.get("highs", [])
    lows = ohlcv.get("lows", [])
    volumes = ohlcv.get("volumes", [])
    n = min(len(closes), len(highs), len(lows), len(volumes))
    issues: List[str] = []
    failed_stage = ""
    missing_metric = ""

    if n < MIN_HISTORY_DAYS:
        issues.append(f"insufficient_history_{n}")
        failed_stage = "DATA_QUALITY"
        missing_metric = "history"
    if n < MIN_INDICATOR_HISTORY_DAYS:
        issues.append("indicators_not_calculable")
        failed_stage = failed_stage or "TECHNICAL_ELIGIBILITY"
        missing_metric = missing_metric or "ema200"
    if not closes or closes[-1] is None or closes[-1] <= 0:
        issues.append("invalid_close")
        failed_stage = "DATA_QUALITY"
        missing_metric = "close"
    zero_vol = sum(1 for v in volumes[-60:] if not v or v <= 0)
    if zero_vol > MAX_ZERO_VOLUME_DAYS_60:
        issues.append(f"too_many_zero_volume_days_{zero_vol}")
        failed_stage = failed_stage or "DATA_QUALITY"
        missing_metric = missing_metric or "volume"

    single_day_jump = 0.0
    daily_moves: List[float] = []
    for i in range(1, n):
        if closes[i - 1]:
            move = abs(_pct(closes[i], closes[i - 1]))
            daily_moves.append(move)
            single_day_jump = max(single_day_jump, move)
    avg_daily_move = _avg(daily_moves[-120:])
    if single_day_jump > MAX_SINGLE_DAY_MOVE_PCT:
        issues.append(f"possible_split_or_bad_tick_{single_day_jump:.1f}")
        failed_stage = failed_stage or "DATA_QUALITY"
        missing_metric = missing_metric or "adjustment"

    price = closes[-1] if closes else 0.0
    avg_volume20 = _avg([v for v in volumes[-20:] if v is not None])
    avg_traded_value20 = avg_volume20 * price
    if price < MIN_STOCK_PRICE or price < PENNY_STOCK_PRICE:
        issues.append(f"price_below_min_{price:.2f}")
        failed_stage = failed_stage or "TRADABILITY"
        missing_metric = missing_metric or "price"
    if avg_volume20 < MIN_AVG_VOLUME:
        issues.append(f"low_avg_volume_{avg_volume20:.0f}")
        failed_stage = failed_stage or "TRADABILITY"
        missing_metric = missing_metric or "avg_volume"
    if avg_traded_value20 < MIN_AVG_TRADED_VALUE:
        issues.append(f"low_avg_traded_value_{avg_traded_value20:.0f}")
        failed_stage = failed_stage or "TRADABILITY"
        missing_metric = missing_metric or "avg_traded_value"
    if avg_daily_move > MAX_AVG_DAILY_MOVE_PCT:
        issues.append(f"excessive_avg_daily_move_{avg_daily_move:.2f}")
        failed_stage = failed_stage or "TRADABILITY"
        missing_metric = missing_metric or "volatility"

    stale_days = ""
    ts = get_timestamps(symbol)
    if ts:
        age_days = (datetime.now(timezone.utc).timestamp() - ts[-1]) / 86400
        stale_days = round(age_days, 1)
        if age_days > 10:
            issues.append(f"stale_price_{age_days:.1f}d")
            failed_stage = failed_stage or "DATA_QUALITY"
            missing_metric = missing_metric or "fresh_price"

    payload = {
        "symbol": symbol,
        "status": "OK" if not issues else "REJECT",
        "issues": ";".join(issues) if issues else "none",
        "price": round(price, 2),
        "history_days": n,
        "avg_volume20": round(avg_volume20, 0),
        "avg_traded_value20": round(avg_traded_value20, 0),
        "avg_daily_move120": round(avg_daily_move, 2),
        "max_single_day_move": round(single_day_jump, 2),
        "zero_volume_days60": zero_vol,
        "stale_days": stale_days,
        "reason": ";".join(issues) if issues else "passed_data_quality_and_tradability",
        "failed_stage": failed_stage,
        "missing_metric": missing_metric,
    }
    return not issues, payload


def run_checks() -> Dict[str, object]:
    symbols = _read_symbols()
    tradable: List[Dict[str, object]] = []
    rejected: List[Dict[str, object]] = []
    report_rows: List[Dict[str, object]] = []

    cache_ready = _cache_has_data()
    if not cache_ready:
        for sym in symbols:
            report_rows.append({
                "SYMBOL": sym,
                "STATUS": "PENDING_CACHE",
                "ISSUES": "cache_not_built_yet",
                "PRICE": "",
                "HISTORY_DAYS": "",
                "AVG_VOLUME20": "",
                "AVG_TRADED_VALUE20": "",
                "AVG_DAILY_MOVE120": "",
            })
        # Preserve symbols for the cache manager; do not reject before first cache build.
        with open(TRADABLE_UNIVERSE_FILE, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["SYMBOL", "STATUS", "PRICE", "AVG_VOLUME20", "AVG_TRADED_VALUE20", "AVG_DAILY_MOVE120", "QUALITY_NOTES"])
            writer.writeheader()
            for sym in symbols:
                writer.writerow({"SYMBOL": sym, "STATUS": "PENDING_CACHE", "PRICE": "", "AVG_VOLUME20": "", "AVG_TRADED_VALUE20": "", "AVG_DAILY_MOVE120": "", "QUALITY_NOTES": "cache_not_built_yet"})
        _write_report(report_rows, len(symbols), 0, len(symbols), cache_ready)
        return {"symbols_checked": len(symbols), "tradable_count": len(symbols), "rejected_count": 0, "cache_ready": False, "ok_to_recommend": False}

    for sym in symbols:
        ok, row = evaluate_symbol(sym)
        report_rows.append({
            "SYMBOL": sym,
            "STATUS": row.get("status", "OK" if ok else "REJECT"),
            "ISSUES": row.get("issues", row.get("reason", "")),
            "PRICE": row.get("price", ""),
            "HISTORY_DAYS": row.get("history_days", ""),
            "AVG_VOLUME20": row.get("avg_volume20", ""),
            "AVG_TRADED_VALUE20": row.get("avg_traded_value20", ""),
            "AVG_DAILY_MOVE120": row.get("avg_daily_move120", ""),
        })
        if ok:
            tradable.append(row)
        else:
            rejected.append({
                "symbol": sym,
                "reason": row.get("reason", "rejected"),
                "failed_stage": row.get("failed_stage", "DATA_QUALITY"),
                "missing_metric": row.get("missing_metric", ""),
                "source": "DATA_QUALITY",
            })

    with open(TRADABLE_UNIVERSE_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["SYMBOL", "STATUS", "PRICE", "AVG_VOLUME20", "AVG_TRADED_VALUE20", "AVG_DAILY_MOVE120", "QUALITY_NOTES"])
        writer.writeheader()
        for row in tradable:
            writer.writerow({
                "SYMBOL": row["symbol"], "STATUS": "OK", "PRICE": row["price"],
                "AVG_VOLUME20": row["avg_volume20"], "AVG_TRADED_VALUE20": row["avg_traded_value20"],
                "AVG_DAILY_MOVE120": row["avg_daily_move120"], "QUALITY_NOTES": "passed",
            })

    # Merge with raw rejected rows if they already exist.
    existing: List[Dict[str, str]] = []
    if os.path.exists(REJECTED_UNIVERSE_FILE):
        try:
            with open(REJECTED_UNIVERSE_FILE, "r", newline="") as f:
                existing = list(csv.DictReader(f))
        except Exception:
            existing = []
    seen = {(r.get("symbol") or r.get("SYMBOL"), r.get("failed_stage")) for r in existing}
    with open(REJECTED_UNIVERSE_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["symbol", "reason", "failed_stage", "missing_metric", "source"])
        writer.writeheader()
        for row in existing:
            writer.writerow({"symbol": row.get("symbol", row.get("SYMBOL", "")), "reason": row.get("reason", ""), "failed_stage": row.get("failed_stage", ""), "missing_metric": row.get("missing_metric", ""), "source": row.get("source", "")})
        for row in rejected:
            key = (row["symbol"], row["failed_stage"])
            if key not in seen:
                writer.writerow(row)

    _write_report(report_rows, len(symbols), len(tradable), len(rejected), cache_ready)
    return {
        "symbols_checked": len(symbols),
        "tradable_count": len(tradable),
        "rejected_count": len(rejected),
        "cache_ready": True,
        "ok_to_recommend": len(tradable) > 0,
    }


def _write_report(rows: List[Dict[str, object]], total: int, tradable_count: int, rejected_count: int, cache_ready: bool) -> None:
    with open(DATA_QUALITY_REPORT_FILE, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["SECTION", "KEY", "VALUE"])
        writer.writerow(["SUMMARY", "symbols_checked", total])
        writer.writerow(["SUMMARY", "tradable_count", tradable_count])
        writer.writerow(["SUMMARY", "rejected_count", rejected_count])
        writer.writerow(["SUMMARY", "cache_ready", cache_ready])
        writer.writerow([])
        if rows:
            fieldnames = list(rows[0].keys())
            writer.writerow(fieldnames)
            for r in rows:
                writer.writerow([r.get(k, "") for k in fieldnames])


def main() -> None:
    result = run_checks()
    print("\nDATA QUALITY")
    print("=" * 80)
    for k, v in result.items():
        print(f"{k}: {v}")
    print(f"Saved: {DATA_QUALITY_REPORT_FILE}, {TRADABLE_UNIVERSE_FILE}, {REJECTED_UNIVERSE_FILE}")


if __name__ == "__main__":
    main()
