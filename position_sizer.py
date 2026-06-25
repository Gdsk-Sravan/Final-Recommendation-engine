"""
position_sizer.py - Risk-based sizing report.

Recommendation engine already calculates position size when a BUY is selected.
This module revalidates sizing using central config, portfolio exposure and
regime caps, then writes a consistent CSV for the daily brief.
"""

from __future__ import annotations

import csv
import os
from typing import Dict, List

from config import (
    TOTAL_CAPITAL,
    RISK_PER_TRADE_PCT,
    MAX_PORTFOLIO_HEAT,
    POSITION_SIZES_FILE,
    RECOMMENDATIONS_FILE,
    PORTFOLIO_STATE_FILE,
    PORTFOLIO_EXPOSURE_SUMMARY_FILE,
    REGIME_SETTINGS,
)
from market_regime import read_regime_file

FIELDS = [
    "SYMBOL", "ACTION", "ENTRY_PRICE", "STOP_LOSS", "RISK_PER_SHARE", "RISK_AMOUNT",
    "RAW_POSITION_PCT", "FINAL_POSITION_PCT", "POSITION_AMOUNT", "REGIME_CAP_PCT",
    "PORTFOLIO_HEAT_AFTER", "SIZING_REASON",
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


def _active_heat() -> float:
    heat = 0.0
    for row in _read_csv(PORTFOLIO_STATE_FILE):
        if str(row.get("status", "ACTIVE")).upper() == "ACTIVE":
            heat += _f(row.get("position_pct"))
    return heat


def _write_exposure_summary(active_exposure: float, rows: List[Dict[str, object]], regime_info: Dict[str, object]) -> None:
    existing = _read_csv(PORTFOLIO_EXPOSURE_SUMMARY_FILE)
    metrics = {r.get("METRIC"): r.get("VALUE") for r in existing if r.get("METRIC")}
    metrics.update({
        "position_sizer_active_exposure_pct": f"{active_exposure:.2f}",
        "new_buy_count": str(len(rows)),
        "risk_per_trade_pct": f"{RISK_PER_TRADE_PCT:.2f}",
        "max_portfolio_heat_pct": f"{MAX_PORTFOLIO_HEAT:.2f}",
        "regime": str(regime_info.get("regime", "TRANSITION")),
    })
    out = [{"METRIC": k, "VALUE": v} for k, v in metrics.items()]
    _write_csv(PORTFOLIO_EXPOSURE_SUMMARY_FILE, ["METRIC", "VALUE"], out)


def main() -> None:
    recs = [r for r in _read_csv(RECOMMENDATIONS_FILE) if str(r.get("ACTION", "")).upper() == "BUY"]
    regime_info = read_regime_file()
    regime = str(regime_info.get("regime", "TRANSITION")).upper()
    settings = REGIME_SETTINGS.get(regime, REGIME_SETTINGS.get("TRANSITION", {}))
    regime_cap = _f(regime_info.get("max_position_size"), _f(settings.get("max_position_size"), 7.0))
    max_total = _f(regime_info.get("max_total_portfolio_exposure"), _f(settings.get("max_total_exposure"), 35.0))
    active_exposure = _active_heat()
    available = max(0.0, max_total - active_exposure)
    rows: List[Dict[str, object]] = []
    heat_after = active_exposure

    for rec in recs:
        entry = _f(rec.get("ENTRY_PRICE"))
        stop = _f(rec.get("STOP_LOSS"))
        risk_per_share = max(entry - stop, 0.0)
        risk_amount = TOTAL_CAPITAL * RISK_PER_TRADE_PCT / 100.0
        raw_pct = (risk_amount / risk_per_share * entry / TOTAL_CAPITAL * 100.0) if entry > 0 and risk_per_share > 0 else 0.0
        engine_pct = _f(rec.get("POSITION_PCT"), raw_pct)
        cap_left = max(0.0, available - sum(_f(r.get("FINAL_POSITION_PCT")) for r in rows))
        final_pct = max(0.0, min(raw_pct, engine_pct, regime_cap, cap_left))
        heat_after += final_pct
        reason_bits = []
        if final_pct <= 0:
            reason_bits.append("no portfolio capacity or invalid stop distance")
        if final_pct < raw_pct:
            reason_bits.append("capped by regime/portfolio/engine allocation")
        if heat_after > MAX_PORTFOLIO_HEAT and MAX_PORTFOLIO_HEAT > 0:
            reason_bits.append("portfolio heat warning")
        if not reason_bits:
            reason_bits.append("risk-based size accepted")
        rows.append({
            "SYMBOL": rec.get("SYMBOL"), "ACTION": "BUY", "ENTRY_PRICE": f"{entry:.2f}",
            "STOP_LOSS": f"{stop:.2f}", "RISK_PER_SHARE": f"{risk_per_share:.2f}",
            "RISK_AMOUNT": f"{risk_amount:.2f}", "RAW_POSITION_PCT": f"{raw_pct:.2f}",
            "FINAL_POSITION_PCT": f"{final_pct:.2f}", "POSITION_AMOUNT": f"{TOTAL_CAPITAL * final_pct / 100.0:.2f}",
            "REGIME_CAP_PCT": f"{regime_cap:.2f}", "PORTFOLIO_HEAT_AFTER": f"{heat_after:.2f}",
            "SIZING_REASON": "; ".join(reason_bits),
        })

    _write_csv(POSITION_SIZES_FILE, FIELDS, rows)
    _write_exposure_summary(active_exposure, rows, regime_info)
    print("\nPOSITION SIZER")
    print("=" * 70)
    print(f"BUY rows: {len(rows)} | Active exposure: {active_exposure:.2f}% | Available: {available:.2f}%")
    print(f"Saved   : {POSITION_SIZES_FILE}, {PORTFOLIO_EXPOSURE_SUMMARY_FILE}")


if __name__ == "__main__":
    main()
