"""
correlation_engine.py - Portfolio/candidate correlation and duplicate-risk report.

Calculates rolling 60-day close-return correlation between active holdings and
new BUY/WATCHLIST candidates. The recommendation engine treats correlation as a
hard/soft portfolio-fit input; this report makes that accounting transparent.
"""

from __future__ import annotations

import csv
import math
import os
from typing import Dict, List, Tuple

from config import (
    CORRELATION_REPORT_FILE,
    MAX_CORRELATION_WITH_HOLDINGS,
    PORTFOLIO_STATE_FILE,
    RECOMMENDATIONS_FILE,
    WATCHLIST_FILE,
)
from data_provider import get_ohlcv

FIELDS = [
    "SYMBOL", "BUCKET", "SECTOR", "MAX_CORRELATION_WITH_ACTIVE", "MOST_CORRELATED_ACTIVE",
    "CORRELATION_STATUS", "DUPLICATE_RISK", "REASON",
]


def _f(v, default: float = 0.0) -> float:
    try:
        if v is None or v == "":
            return default
        return float(v)
    except Exception:
        return default


def _read_csv(path: str) -> List[Dict[str, str]]:
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", newline="") as f:
            return list(csv.DictReader(f))
    except Exception:
        return []


def _write_csv(path: str, fields: List[str], rows: List[Dict[str, object]]) -> None:
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def _returns(symbol: str, lookback: int = 60) -> List[float]:
    data = get_ohlcv(symbol)
    closes = [float(x) for x in data.get("closes", []) if x is not None] if data else []
    if len(closes) < lookback + 1:
        return []
    sample = closes[-lookback - 1:]
    out = []
    for i in range(1, len(sample)):
        prev = sample[i - 1]
        out.append((sample[i] / prev - 1.0) if prev else 0.0)
    return out


def _corr(a: List[float], b: List[float]) -> float:
    n = min(len(a), len(b))
    if n < 20:
        return 0.0
    x = a[-n:]
    y = b[-n:]
    mx = sum(x) / n
    my = sum(y) / n
    cov = sum((x[i] - mx) * (y[i] - my) for i in range(n))
    vx = sum((v - mx) ** 2 for v in x)
    vy = sum((v - my) ** 2 for v in y)
    if vx <= 0 or vy <= 0:
        return 0.0
    return cov / math.sqrt(vx * vy)


def _active_positions() -> List[Dict[str, str]]:
    return [r for r in _read_csv(PORTFOLIO_STATE_FILE) if str(r.get("status", "ACTIVE")).upper() == "ACTIVE"]


def max_correlation_with_active(symbol: str, active: List[Dict[str, str]], cache: Dict[str, List[float]] | None = None) -> Tuple[float, str]:
    cache = cache if cache is not None else {}
    if symbol not in cache:
        cache[symbol] = _returns(symbol)
    sret = cache.get(symbol, [])
    best = 0.0
    best_sym = ""
    for row in active:
        active_sym = row.get("symbol") or row.get("SYMBOL")
        if not active_sym or active_sym == symbol:
            continue
        if active_sym not in cache:
            cache[active_sym] = _returns(active_sym)
        c = _corr(sret, cache.get(active_sym, []))
        if abs(c) > abs(best):
            best = c
            best_sym = active_sym
    return best, best_sym


def _candidate_rows() -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for row in _read_csv(RECOMMENDATIONS_FILE):
        if str(row.get("ACTION", "")).upper() == "BUY":
            rows.append({"SYMBOL": row.get("SYMBOL", ""), "SECTOR": row.get("SECTOR", "Unknown"), "BUCKET": "BUY"})
    for row in _read_csv(WATCHLIST_FILE):
        rows.append({"SYMBOL": row.get("SYMBOL", ""), "SECTOR": row.get("SECTOR", "Unknown"), "BUCKET": "WATCHLIST"})
    seen = set()
    unique = []
    for row in rows:
        sym = row.get("SYMBOL")
        if sym and sym not in seen:
            unique.append(row)
            seen.add(sym)
    return unique


def main() -> None:
    active = _active_positions()
    candidates = _candidate_rows()
    cache: Dict[str, List[float]] = {}
    rows: List[Dict[str, object]] = []
    active_by_sector: Dict[str, int] = {}
    for row in active:
        sector = row.get("sector", "Unknown") or "Unknown"
        active_by_sector[sector] = active_by_sector.get(sector, 0) + 1

    for cand in candidates:
        sym = cand.get("SYMBOL", "")
        sector = cand.get("SECTOR", "Unknown") or "Unknown"
        corr, active_sym = max_correlation_with_active(sym, active, cache)
        same_sector_count = active_by_sector.get(sector, 0)
        if abs(corr) >= MAX_CORRELATION_WITH_HOLDINGS:
            status = "BLOCK"
            duplicate = "HIGH"
            reason = f"60-day correlation {corr:.2f} with {active_sym} exceeds {MAX_CORRELATION_WITH_HOLDINGS:.2f}"
        elif abs(corr) >= MAX_CORRELATION_WITH_HOLDINGS - 0.10:
            status = "CAUTION"
            duplicate = "MEDIUM"
            reason = f"correlation {corr:.2f} near limit; check duplicate exposure"
        elif same_sector_count >= 2:
            status = "CAUTION"
            duplicate = "MEDIUM"
            reason = f"already {same_sector_count} active positions in {sector}"
        else:
            status = "OK"
            duplicate = "LOW"
            reason = "correlation and sector duplication acceptable"
        rows.append({
            "SYMBOL": sym,
            "BUCKET": cand.get("BUCKET", ""),
            "SECTOR": sector,
            "MAX_CORRELATION_WITH_ACTIVE": f"{corr:.4f}",
            "MOST_CORRELATED_ACTIVE": active_sym,
            "CORRELATION_STATUS": status,
            "DUPLICATE_RISK": duplicate,
            "REASON": reason,
        })

    _write_csv(CORRELATION_REPORT_FILE, FIELDS, rows)
    print("\nCORRELATION ENGINE")
    print("=" * 70)
    print(f"Active positions : {len(active)}")
    print(f"Candidates       : {len(candidates)}")
    print(f"Saved            : {CORRELATION_REPORT_FILE}")


if __name__ == "__main__":
    main()
