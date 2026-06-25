"""
manual_portfolio_loader.py - Load actual user holdings from GitHub secret/env.

Purpose
-------
BUY recommendations are not treated as bought. The engine manages only the
holdings the user explicitly supplies in MANUAL_PORTFOLIO_JSON or an optional
manual_portfolio.json file.

Recommended GitHub secret value:
[
  {"symbol":"KIRLOSENG.NS","entry_price":2483.60,"entry_date":"2026-06-25","position_pct":10.0},
  {"symbol":"LAURUSLABS.NS","entry_price":1474.30,"entry_date":"2026-06-25","quantity":5}
]

If the secret is absent or [], the active portfolio becomes empty. This is
intentional for PORTFOLIO_SOURCE=MANUAL_ENV, because stale virtual holdings must
not remain in portfolio_state.csv.
"""

from __future__ import annotations

import csv
import json
import os
from datetime import datetime
from typing import Any, Dict, Iterable, List, Tuple

from config import (
    AUTO_TRACK_RECOMMENDED_BUYS,
    DEFAULT_MANUAL_POSITION_PCT,
    MANUAL_PORTFOLIO_FILE,
    MANUAL_PORTFOLIO_JSON,
    PORTFOLIO_FILE,
    PORTFOLIO_SOURCE,
    PORTFOLIO_SOURCE_REPORT_FILE,
    PORTFOLIO_STATE_FILE,
    SECTOR_MAP,
    SECTOR_OVERRIDES,
    TARGET1_R_MULTIPLE,
    TARGET2_R_MULTIPLE,
    TOTAL_CAPITAL,
    UNMAPPED_SECTOR_LABEL,
)

STATE_FIELDS = [
    "symbol", "sector", "entry_date", "entry_price", "setup_type", "confidence_at_entry",
    "position_pct", "stop_loss", "target_1", "target_2", "trailing_stop", "highest_price",
    "current_price", "unrealized_pnl_pct", "days_held", "current_action", "exit_date",
    "exit_price", "exit_reason", "status",
]


def _f(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _normalize_symbol(raw: Any) -> str:
    symbol = str(raw or "").strip().upper()
    if not symbol:
        return ""
    if symbol.startswith("^") or symbol.endswith(".NS") or symbol.endswith(".BO"):
        return symbol
    return f"{symbol}.NS"


def _sector_lookup(symbol: str, supplied: str = "") -> str:
    supplied = str(supplied or "").strip()
    if supplied and supplied.upper() not in ("UNKNOWN", "NONE", "N/A", "NA"):
        return supplied
    if symbol in SECTOR_OVERRIDES:
        return SECTOR_OVERRIDES[symbol]
    for sector, symbols in SECTOR_MAP.items():
        if symbol in {str(s).upper() for s in symbols}:
            return sector
    return UNMAPPED_SECTOR_LABEL


def _read_json_payload() -> Tuple[List[Dict[str, Any]], str, str]:
    text = MANUAL_PORTFOLIO_JSON.strip()
    source = "MANUAL_PORTFOLIO_JSON"

    if not text and os.path.exists(MANUAL_PORTFOLIO_FILE):
        try:
            with open(MANUAL_PORTFOLIO_FILE, "r", encoding="utf-8") as f:
                text = f.read().strip()
            source = MANUAL_PORTFOLIO_FILE
        except Exception as exc:
            return [], source, f"failed reading {MANUAL_PORTFOLIO_FILE}: {exc}"

    if not text:
        return [], source, "empty manual portfolio"

    try:
        data = json.loads(text)
    except Exception as exc:
        return [], source, f"invalid JSON: {exc}"

    if isinstance(data, dict):
        data = data.get("holdings") or data.get("positions") or []

    if not isinstance(data, list):
        return [], source, "manual portfolio JSON must be a list or {'holdings': [...]}"

    rows = [x for x in data if isinstance(x, dict)]
    return rows, source, "ok"


def _date_ok(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return datetime.now().strftime("%Y-%m-%d")
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except Exception:
            pass
    return text


def _position_pct(item: Dict[str, Any], entry_price: float) -> str:
    if item.get("position_pct") not in (None, ""):
        pct = _f(item.get("position_pct"), 0.0)
        return f"{pct:.2f}" if pct > 0 else ""
    if item.get("allocation_pct") not in (None, ""):
        pct = _f(item.get("allocation_pct"), 0.0)
        return f"{pct:.2f}" if pct > 0 else ""
    qty = _f(item.get("quantity"), 0.0)
    if qty > 0 and entry_price > 0 and TOTAL_CAPITAL > 0:
        return f"{qty * entry_price / TOTAL_CAPITAL * 100.0:.2f}"
    if DEFAULT_MANUAL_POSITION_PCT:
        pct = _f(DEFAULT_MANUAL_POSITION_PCT, 0.0)
        return f"{pct:.2f}" if pct > 0 else ""
    return ""


def _derive_risk_levels(item: Dict[str, Any], entry: float) -> Tuple[float, float, float, float]:
    stop = _f(item.get("stop_loss"), 0.0)
    if stop <= 0 and entry > 0:
        stop = entry * 0.94
    risk = max(entry - stop, entry * 0.01 if entry > 0 else 1.0)
    target1 = _f(item.get("target_1"), 0.0) or _f(item.get("target1"), 0.0)
    target2 = _f(item.get("target_2"), 0.0) or _f(item.get("target2"), 0.0)
    trail = _f(item.get("trailing_stop"), 0.0) or _f(item.get("trail"), 0.0)
    if target1 <= 0 and entry > 0:
        target1 = entry + TARGET1_R_MULTIPLE * risk
    if target2 <= 0 and entry > 0:
        target2 = entry + TARGET2_R_MULTIPLE * risk
    if trail <= 0:
        trail = stop
    return stop, target1, target2, trail


def _build_state_rows(items: Iterable[Dict[str, Any]]) -> Tuple[List[Dict[str, str]], List[str]]:
    rows: List[Dict[str, str]] = []
    errors: List[str] = []
    seen = set()

    for idx, item in enumerate(items, 1):
        symbol = _normalize_symbol(item.get("symbol") or item.get("SYMBOL") or item.get("ticker"))
        if not symbol:
            errors.append(f"row {idx}: missing symbol")
            continue
        if symbol in seen:
            errors.append(f"row {idx}: duplicate symbol {symbol} ignored")
            continue
        seen.add(symbol)

        entry = _f(item.get("entry_price") or item.get("buy_price") or item.get("price"), 0.0)
        if entry <= 0:
            errors.append(f"{symbol}: missing/invalid entry_price")
            continue

        entry_date = _date_ok(item.get("entry_date") or item.get("buy_date") or item.get("date"))
        sector = _sector_lookup(symbol, str(item.get("sector") or ""))
        pct = _position_pct(item, entry)
        stop, target1, target2, trail = _derive_risk_levels(item, entry)
        highest = max(_f(item.get("highest_price"), entry), entry)
        current = _f(item.get("current_price"), entry)
        pnl = ((current - entry) / entry * 100.0) if entry > 0 and current > 0 else 0.0

        rows.append({
            "symbol": symbol,
            "sector": sector,
            "entry_date": entry_date,
            "entry_price": f"{entry:.2f}",
            "setup_type": str(item.get("setup_type") or "MANUAL"),
            "confidence_at_entry": str(item.get("confidence") or item.get("confidence_at_entry") or ""),
            "position_pct": pct,
            "stop_loss": f"{stop:.2f}",
            "target_1": f"{target1:.2f}",
            "target_2": f"{target2:.2f}",
            "trailing_stop": f"{trail:.2f}",
            "highest_price": f"{highest:.2f}",
            "current_price": f"{current:.2f}",
            "unrealized_pnl_pct": f"{pnl:.2f}",
            "days_held": "0",
            "current_action": "HOLD",
            "exit_date": "",
            "exit_price": "",
            "exit_reason": "",
            "status": "ACTIVE",
        })

    return rows, errors


def _write_csv(path: str, fields: List[str], rows: List[Dict[str, Any]]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def _write_legacy_portfolio(rows: List[Dict[str, str]]) -> None:
    with open(PORTFOLIO_FILE, "w", encoding="utf-8") as f:
        f.write("# Manual holdings only. Generated from MANUAL_PORTFOLIO_JSON.\n")
        f.write("# SYMBOL,BUY_PRICE,CONFIDENCE,SECTOR,POSITION_PCT,ENTRY_DATE\n")
        for row in rows:
            f.write(
                f"{row.get('symbol')},{row.get('entry_price')},{row.get('confidence_at_entry')},"
                f"{row.get('sector')},{row.get('position_pct')},{row.get('entry_date')}\n"
            )


def main() -> None:
    source_mode = PORTFOLIO_SOURCE.upper()
    if source_mode not in ("MANUAL_ENV", "MANUAL_JSON", "MANUAL_FILE"):
        msg = f"Portfolio source {PORTFOLIO_SOURCE}; manual loader skipped. AUTO_TRACK_RECOMMENDED_BUYS={AUTO_TRACK_RECOMMENDED_BUYS}"
        print(msg)
        with open(PORTFOLIO_SOURCE_REPORT_FILE, "w", encoding="utf-8") as f:
            f.write(msg + "\n")
        return

    raw_rows, source, status = _read_json_payload()
    state_rows, errors = _build_state_rows(raw_rows)
    _write_csv(PORTFOLIO_STATE_FILE, STATE_FIELDS, state_rows)
    _write_legacy_portfolio(state_rows)

    missing_pct = sum(1 for r in state_rows if not str(r.get("position_pct", "")).strip())
    exposure_known = sum(_f(r.get("position_pct"), 0.0) for r in state_rows)
    report_lines = [
        "MANUAL PORTFOLIO LOADER",
        "=" * 80,
        f"source_mode: {PORTFOLIO_SOURCE}",
        f"source: {source}",
        f"source_status: {status}",
        f"active_holdings_loaded: {len(state_rows)}",
        f"known_exposure_pct: {exposure_known:.2f}",
        f"missing_position_pct_count: {missing_pct}",
        f"auto_track_recommended_buys: {AUTO_TRACK_RECOMMENDED_BUYS}",
    ]
    if errors:
        report_lines.append("errors:")
        report_lines.extend(f"- {e}" for e in errors[:50])

    with open(PORTFOLIO_SOURCE_REPORT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines) + "\n")

    print("\n".join(report_lines))
    print(f"Saved: {PORTFOLIO_STATE_FILE}, {PORTFOLIO_FILE}, {PORTFOLIO_SOURCE_REPORT_FILE}")


if __name__ == "__main__":
    main()
