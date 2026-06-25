"""
validation_checks.py - Post-run safeguards for decision-quality engine.

These checks verify that the final files respect hard gates and lifecycle rules.
They are intentionally conservative; failures should be inspected before using
any daily recommendations.
"""

from __future__ import annotations

import csv
import json
import os
import sys
from typing import Dict, List

from config import (
    AI_VALIDATION_REPORT_FILE,
    CORRELATION_REPORT_FILE,
    MAX_CORRELATION_WITH_HOLDINGS,
    MIN_REWARD_RISK_BY_REGIME,
    PORTFOLIO_STATE_FILE,
    PORTFOLIO_STATUS_FILE,
    RECOMMENDATIONS_FILE,
    REJECTED_CANDIDATES_FILE,
    TRADABLE_UNIVERSE_FILE,
    WATCHLIST_FILE,
)
from market_regime import read_regime_file


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


def _read_json(path: str) -> Dict:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def main() -> int:
    issues: List[str] = []
    warnings: List[str] = []
    regime_info = read_regime_file()
    regime = str(regime_info.get("regime", "TRANSITION")).upper()
    recs = [r for r in _read_csv(RECOMMENDATIONS_FILE) if str(r.get("ACTION", "")).upper() == "BUY"]
    state = _read_csv(PORTFOLIO_STATE_FILE)
    watch = _read_csv(WATCHLIST_FILE)
    rejected = _read_csv(REJECTED_CANDIDATES_FILE)
    status = _read_csv(PORTFOLIO_STATUS_FILE)
    corr = _read_csv(CORRELATION_REPORT_FILE)

    if regime == "STRONG_BEAR" and recs:
        issues.append("BUY exists while regime is STRONG_BEAR")

    min_rr = MIN_REWARD_RISK_BY_REGIME.get(regime, 1.8)
    for row in recs:
        sym = row.get("SYMBOL")
        if _f(row.get("STOP_LOSS")) <= 0:
            issues.append(f"{sym}: BUY missing stop loss")
        if _f(row.get("TARGET_1")) <= 0 or _f(row.get("TARGET_2")) <= 0:
            issues.append(f"{sym}: BUY missing target")
        if _f(row.get("REWARD_RISK")) < min_rr:
            issues.append(f"{sym}: BUY reward/risk {_f(row.get('REWARD_RISK')):.2f} below regime minimum {min_rr:.2f}")

    active_symbols = [r.get("symbol") for r in state if str(r.get("status", "ACTIVE")).upper() == "ACTIVE" and r.get("symbol")]
    active_set = set(active_symbols)
    if len(active_symbols) != len(active_set):
        issues.append("duplicate active positions found in portfolio_state.csv")
    for row in recs:
        if row.get("SYMBOL") in active_set:
            issues.append(f"{row.get('SYMBOL')}: active holding also appears as BUY recommendation")
    for row in watch[:50]:
        if row.get("SYMBOL") in active_set:
            issues.append(f"{row.get('SYMBOL')}: active holding also appears in WATCHLIST")

    for row in state:
        if str(row.get("status", "ACTIVE")).upper() == "ACTIVE":
            stop = _f(row.get("stop_loss"))
            trail = _f(row.get("trailing_stop"))
            if trail and stop and trail < stop:
                issues.append(f"{row.get('symbol')}: trailing stop below hard stop")

    for row in rejected[:50]:
        if not row.get("ONE_LINE_REASON") or row.get("ONE_LINE_REASON") in ("not selected", ""):
            issues.append(f"{row.get('SYMBOL')}: rejected candidate missing specific reason")
        if not row.get("REJECTION_CATEGORY"):
            issues.append(f"{row.get('SYMBOL')}: rejected candidate missing category")

    if not recs and not watch:
        warnings.append("BUY is empty and WATCHLIST is also empty; acceptable only if no valid near-misses existed")

    for row in corr:
        if str(row.get("CORRELATION_STATUS", "")).upper() == "BLOCK" and _f(row.get("MAX_CORRELATION_WITH_ACTIVE")) < MAX_CORRELATION_WITH_HOLDINGS:
            issues.append(f"{row.get('SYMBOL')}: correlation BLOCK below configured limit")

    ai = _read_json(AI_VALIDATION_REPORT_FILE)
    if ai and ai.get("status") == "fallback":
        warnings.append("AI second pass unavailable; deterministic report used")

    if not os.path.exists(TRADABLE_UNIVERSE_FILE) or os.path.getsize(TRADABLE_UNIVERSE_FILE) == 0:
        issues.append("tradable_universe.csv missing or empty")

    for row in status:
        action = str(row.get("ACTION", "")).upper()
        if action in ("SELL", "NEWS_RISK_EXIT", "STOP_LOSS_EXIT", "TRAILING_STOP_EXIT") and not row.get("REASON"):
            issues.append(f"{row.get('SYMBOL')}: exit action missing reason")

    print("\nVALIDATION CHECKS")
    print("=" * 70)
    if issues:
        print("FAILURES:")
        for item in issues:
            print(f"- {item}")
    else:
        print("No hard-gate validation failures.")
    if warnings:
        print("\nWARNINGS:")
        for item in warnings:
            print(f"- {item}")
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
