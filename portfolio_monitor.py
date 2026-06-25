"""
portfolio_monitor.py - Manual-holdings monitor and exit-signal engine.

This module monitors only actual holdings loaded from MANUAL_PORTFOLIO_JSON via
manual_portfolio_loader.py. It does not assume recommended BUYs were executed.
By default it also does not close/remove holdings automatically; EXIT/SELL rows
are execution instructions. You remove the holding from MANUAL_PORTFOLIO_JSON
when you actually sell it.
"""

from __future__ import annotations

import csv
import os
from datetime import date, datetime
from typing import Dict, List, Tuple

from config import (
    AI_NEWS_SCORES_FILE,
    AUTO_CLOSE_EXIT_SIGNALS,
    NEWS_SCORES_FILE,
    NEWS_SEVERITY_EXIT_THRESHOLD,
    NEWS_SEVERITY_WATCHLIST_THRESHOLD,
    PORTFOLIO_SOURCE,
    PORTFOLIO_STATE_FILE,
    PORTFOLIO_STATUS_FILE,
    TIME_EXIT_DAYS,
    TRADE_JOURNAL_FILE,
    TRAILING_STOP_ATR_MULTIPLIER,
)
from confidence_engine import compute_exit_risk_score
from data_provider import get_ohlcv
from market_regime import read_regime_file
from sector_rotation import load_sector_scores
from sector_utils import resolve_sector

STATE_FIELDS = [
    "symbol", "sector", "entry_date", "entry_price", "setup_type", "confidence_at_entry",
    "position_pct", "stop_loss", "target_1", "target_2", "trailing_stop", "highest_price",
    "current_price", "unrealized_pnl_pct", "days_held", "current_action", "exit_date",
    "exit_price", "exit_reason", "status",
]

STATUS_FIELDS = [
    "SYMBOL", "ACTION", "STATUS", "PNL_PCT", "CURRENT_PRICE", "ENTRY_PRICE", "STOP_LOSS",
    "TRAILING_STOP", "TARGET_1", "TARGET_1_STATUS", "TARGET_2", "TARGET_2_STATUS",
    "SECTOR", "SECTOR_STATUS", "RELATIVE_STRENGTH_STATUS", "EVENT_RISK_STATUS",
    "EVENT_SEVERITY", "EVENT_TYPE", "EVENT_SOURCE_TYPE", "EVENT_SUMMARY",
    "DAYS_HELD", "EXIT_RISK_SCORE", "WHY_VALID", "INVALIDATION_TRIGGER", "REASON",
    "URGENCY", "EXIT_PRICE", "EXIT_REASON",
]

EXIT_ACTIONS = {
    "SELL", "STOP_LOSS_EXIT", "TRAILING_STOP_EXIT", "TIME_EXIT", "NEWS_RISK_EXIT",
    "SECTOR_WEAKNESS_EXIT", "MARKET_REGIME_EXIT",
}


def _f(v, default: float = 0.0) -> float:
    try:
        if v is None or v == "":
            return default
        return float(v)
    except Exception:
        return default


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def _read_csv(path: str) -> List[Dict[str, str]]:
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", newline="", encoding="utf-8", errors="ignore") as f:
            return list(csv.DictReader(f))
    except Exception:
        return []


def _write_csv(path: str, fields: List[str], rows: List[Dict[str, object]]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def _ema(values: List[float], period: int) -> float:
    if not values:
        return 0.0
    if len(values) < period:
        return values[-1]
    mult = 2 / (period + 1)
    ema = sum(values[:period]) / period
    for val in values[period:]:
        ema = (val - ema) * mult + ema
    return ema


def _atr(closes: List[float], highs: List[float], lows: List[float], period: int = 14) -> float:
    n = min(len(closes), len(highs), len(lows))
    if n < 2:
        return 0.0
    trs: List[float] = []
    for i in range(1, n):
        trs.append(max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1])))
    sample = trs[-period:] if len(trs) >= period else trs
    return sum(sample) / len(sample) if sample else 0.0


def _pct_return(values: List[float], lookback: int) -> float:
    if len(values) < lookback + 1 or values[-lookback - 1] <= 0:
        return 0.0
    return (values[-1] / values[-lookback - 1] - 1) * 100


def _days_held(entry_date: str) -> int:
    try:
        return max(0, (date.today() - datetime.strptime(entry_date, "%Y-%m-%d").date()).days)
    except Exception:
        return 0


def _load_state() -> List[Dict[str, str]]:
    rows = _read_csv(PORTFOLIO_STATE_FILE)
    out: List[Dict[str, str]] = []
    for row in rows:
        sym = row.get("symbol") or row.get("SYMBOL")
        if not sym:
            continue
        fixed = {field: row.get(field, "") for field in STATE_FIELDS}
        fixed["symbol"] = sym
        fixed["sector"] = resolve_sector(sym, fixed.get("sector"))
        fixed["status"] = fixed.get("status") or "ACTIVE"
        out.append(fixed)
    return out


def _write_state(rows: List[Dict[str, str]]) -> None:
    _write_csv(PORTFOLIO_STATE_FILE, STATE_FIELDS, rows)


def _append_trade(row: Dict[str, str]) -> None:
    file_exists = os.path.exists(TRADE_JOURNAL_FILE) and os.path.getsize(TRADE_JOURNAL_FILE) > 0
    fields = STATE_FIELDS + ["realized_pnl_pct"]
    entry = _f(row.get("entry_price"))
    exit_price = _f(row.get("exit_price"))
    realized = ((exit_price - entry) / entry * 100) if entry > 0 and exit_price > 0 else _f(row.get("unrealized_pnl_pct"))
    with open(TRADE_JOURNAL_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        if not file_exists:
            writer.writeheader()
        out = {field: row.get(field, "") for field in STATE_FIELDS}
        out["realized_pnl_pct"] = f"{realized:.2f}"
        writer.writerow(out)


def _load_news_risk() -> Dict[str, Dict[str, object]]:
    out: Dict[str, Dict[str, object]] = {}
    for path in (AI_NEWS_SCORES_FILE, NEWS_SCORES_FILE):
        for row in _read_csv(path):
            sym = (row.get("SYMBOL") or row.get("symbol") or "").strip()
            if not sym:
                continue
            severity = max(_f(row.get("AI_SEVERITY")), _f(row.get("MAX_SEVERITY")), _f(row.get("SEVERITY_SCORE")))
            black = str(row.get("BLACK_SWAN", "0")).strip().lower() in ("1", "true", "yes", "y")
            event = row.get("AI_EVENT_TYPE") or row.get("EVENT_TYPE") or row.get("event_type") or "NoEvent"
            summary = row.get("AI_SUMMARY") or row.get("EVENT_SUMMARY") or row.get("HEADLINE") or row.get("headline") or ""
            source_type = row.get("SOURCE_TYPE") or row.get("source_type") or row.get("source") or "news"
            out[sym] = {
                "severity": severity,
                "black_swan": black,
                "event": event,
                "summary": summary,
                "source_type": source_type,
            }
    return out


def _sector_class(sector_scores: Dict[str, Dict[str, object]], sector: str) -> str:
    row = sector_scores.get(sector) or sector_scores.get(str(sector).upper()) or {}
    return str(row.get("classification") or row.get("CLASSIFICATION") or "NEUTRAL").upper()


def _rs_status(closes: List[float]) -> str:
    short = _pct_return(closes, 10)
    medium = _pct_return(closes, 20)
    if short > 3 and medium > 5:
        return "IMPROVING"
    if short < -3 and medium < 0:
        return "DETERIORATING"
    if short >= 0:
        return "STABLE"
    return "SOFTENING"


def _target_status(current: float, target: float) -> str:
    if target <= 0:
        return "MISSING"
    return "HIT" if current >= target else "PENDING"


def _update_trailing_stop(entry: float, current: float, stop: float, old_trail: float, target1: float, closes: List[float], highs: List[float], lows: List[float]) -> float:
    atr = _atr(closes, highs, lows)
    ema20 = _ema(closes, 20)
    trail = max(old_trail, stop)
    risk = max(entry - stop, 0.01)
    moved_r = (current - entry) / risk
    if current >= target1 or moved_r >= 1.5:
        candidates = [trail, stop]
        if atr > 0:
            candidates.append(current - TRAILING_STOP_ATR_MULTIPLIER * atr)
        if ema20 > 0:
            candidates.append(ema20 * 0.995)
        trail = max(candidates)
    return max(trail, stop)


def _status_reason(action: str, reason: str) -> Tuple[str, str]:
    if action in EXIT_ACTIONS:
        return "HIGH", reason
    if action in {"HOLD_CAUTION", "REDUCE", "BOOK_PROFIT"}:
        return "MEDIUM", reason
    return "LOW", reason


def _exit_action(action: str) -> bool:
    return action in EXIT_ACTIONS


def _status_row_base(sym: str, action: str, pnl: float, current: float, entry: float, stop: float, trail: float, target1: float, target2: float, sector: str, reason: str, urgency: str = "MEDIUM") -> Dict[str, object]:
    return {
        "SYMBOL": sym,
        "ACTION": action,
        "STATUS": "ACTIVE",
        "PNL_PCT": f"{pnl:.2f}",
        "CURRENT_PRICE": f"{current:.2f}",
        "ENTRY_PRICE": f"{entry:.2f}",
        "STOP_LOSS": f"{stop:.2f}",
        "TRAILING_STOP": f"{trail:.2f}",
        "TARGET_1": f"{target1:.2f}",
        "TARGET_1_STATUS": "UNKNOWN",
        "TARGET_2": f"{target2:.2f}",
        "TARGET_2_STATUS": "UNKNOWN",
        "SECTOR": sector,
        "SECTOR_STATUS": "UNKNOWN",
        "RELATIVE_STRENGTH_STATUS": "UNKNOWN",
        "EVENT_RISK_STATUS": "UNKNOWN",
        "EVENT_SEVERITY": "",
        "EVENT_TYPE": "",
        "EVENT_SOURCE_TYPE": "",
        "EVENT_SUMMARY": "",
        "DAYS_HELD": "",
        "EXIT_RISK_SCORE": "",
        "WHY_VALID": "data unavailable; not exiting without price confirmation",
        "INVALIDATION_TRIGGER": "fresh OHLCV data required",
        "REASON": reason,
        "URGENCY": urgency,
        "EXIT_PRICE": "",
        "EXIT_REASON": "",
    }


def _update_one(row: Dict[str, str], regime: Dict[str, object], sectors: Dict[str, Dict[str, object]], news: Dict[str, Dict[str, object]]) -> Tuple[Dict[str, str], Dict[str, object]]:
    sym = row.get("symbol", "")
    sector = resolve_sector(sym, row.get("sector", ""))
    row["sector"] = sector
    if str(row.get("status", "ACTIVE")).upper() != "ACTIVE":
        return row, {}

    entry = _f(row.get("entry_price"))
    stop = _f(row.get("stop_loss"))
    target1 = _f(row.get("target_1"))
    target2 = _f(row.get("target_2"))
    old_trail = _f(row.get("trailing_stop"), stop)
    days = _days_held(row.get("entry_date", ""))
    ohlcv = get_ohlcv(sym)

    if not ohlcv or len(ohlcv.get("closes", [])) < 50 or entry <= 0:
        current = _f(row.get("current_price"), entry)
        pnl = ((current - entry) / entry * 100) if entry else 0.0
        row.update({"current_action": "HOLD_CAUTION", "days_held": str(days), "unrealized_pnl_pct": f"{pnl:.2f}"})
        status = _status_row_base(sym, "HOLD_CAUTION", pnl, current, entry, stop, old_trail, target1, target2, sector, "missing current OHLCV data")
        status["DAYS_HELD"] = days
        return row, status

    closes = [float(x) for x in ohlcv.get("closes", [])]
    highs = [float(x) for x in ohlcv.get("highs", closes)]
    lows = [float(x) for x in ohlcv.get("lows", closes)]
    volumes = [float(x) for x in ohlcv.get("volumes", [0] * len(closes))]
    current = closes[-1]
    pnl = ((current - entry) / entry) * 100
    ema20 = _ema(closes, 20)
    ema50 = _ema(closes, 50)
    vol20 = sum(volumes[-20:]) / min(len(volumes), 20) if volumes else 0.0
    highest = max(_f(row.get("highest_price"), entry), max(highs[-5:]) if highs else current, current)
    new_trail = _update_trailing_stop(entry, current, stop, old_trail, target1, closes, highs, lows)

    row.update({
        "current_price": f"{current:.2f}",
        "highest_price": f"{highest:.2f}",
        "trailing_stop": f"{new_trail:.2f}",
        "unrealized_pnl_pct": f"{pnl:.2f}",
        "days_held": str(days),
    })

    sector_status = _sector_class(sectors, sector)
    nr = news.get(sym, {"severity": 0.0, "black_swan": False, "event": "NoEvent", "summary": "", "source_type": "news"})
    severity = _f(nr.get("severity"))
    black_swan = bool(nr.get("black_swan"))
    event = str(nr.get("event") or "NoEvent")
    event_summary = str(nr.get("summary") or "")[:220]
    source_type = str(nr.get("source_type") or "news")
    event_status = "SEVERE" if black_swan or severity >= NEWS_SEVERITY_EXIT_THRESHOLD else "MODERATE" if severity >= NEWS_SEVERITY_WATCHLIST_THRESHOLD else "CLEAR"
    rs_status = _rs_status(closes)

    below_stop = current <= stop and stop > 0
    trail_hit = new_trail > stop and current <= new_trail and pnl > 0
    below_ema20 = current < ema20 if ema20 else False
    below_ema50 = current < ema50 if ema50 else False
    support_break = bool(len(lows) >= 21 and current < min(lows[-21:-1]) and (vol20 and volumes[-1] > vol20 * 1.2))
    time_decay = days >= TIME_EXIT_DAYS and pnl < 3.0
    strong_bear = str(regime.get("regime", "TRANSITION")).upper() == "STRONG_BEAR"

    exit_score = compute_exit_risk_score(
        pnl_pct=pnl,
        below_stop=below_stop,
        below_ema20=below_ema20,
        below_ema50=below_ema50,
        sector_class=sector_status,
        market_regime=str(regime.get("regime", "TRANSITION")),
        ai_severity=int(severity),
        black_swan=black_swan,
        trailing_stop_hit=trail_hit,
        time_decay=time_decay,
    )

    action = "HOLD"
    reason = "trend valid; price above active risk level"
    why_valid = "above stop/trailing stop; no severe event risk"
    invalidation = f"close below {max(stop, new_trail):.2f} or severe event risk"

    if black_swan:
        action, reason = "NEWS_RISK_EXIT", f"black-swan event risk: {event}"
    elif severity >= NEWS_SEVERITY_EXIT_THRESHOLD:
        action, reason = "NEWS_RISK_EXIT", f"severe event/news risk {severity:.0f}: {event}"
    elif below_stop:
        action, reason = "STOP_LOSS_EXIT", f"hard stop hit at {stop:.2f}"
    elif trail_hit:
        action, reason = "TRAILING_STOP_EXIT", f"trailing stop hit at {new_trail:.2f}"
    elif support_break:
        action, reason = "SELL", "key 20-day support broke with elevated volume"
    elif strong_bear and below_ema20:
        action, reason = "MARKET_REGIME_EXIT", "STRONG_BEAR regime and stock lost EMA20"
    elif sector_status == "LAGGING" and below_ema20:
        action, reason = "SECTOR_WEAKNESS_EXIT", "sector LAGGING and stock below EMA20"
    elif below_ema50 and pnl < 0:
        action, reason = "SELL", "below EMA50 with negative PnL"
    elif time_decay:
        action, reason = "TIME_EXIT", f"no useful follow-through after {days} days"
    elif current >= target2 and target2 > 0:
        action, reason = "BOOK_PROFIT", f"target 2 reached at {target2:.2f}"
        invalidation = f"protect gains below trail {new_trail:.2f}"
    elif current >= target1 and target1 > 0:
        if sector_status in ("WEAKENING", "LAGGING") or below_ema20 or rs_status in ("SOFTENING", "DETERIORATING"):
            action, reason = "BOOK_PROFIT", "target 1 reached and momentum/sector risk rising"
        else:
            action, reason = "HOLD", "target 1 reached; trend and sector still acceptable"
        invalidation = f"protect gains below trail {new_trail:.2f}"
    elif sector_status == "WEAKENING" or event_status == "MODERATE" or rs_status == "DETERIORATING" or below_ema20:
        action = "HOLD_CAUTION"
        bits = []
        if sector_status == "WEAKENING":
            bits.append("sector weakening")
        if event_status == "MODERATE":
            bits.append(f"moderate event risk {severity:.0f}")
        if rs_status == "DETERIORATING":
            bits.append("relative strength deteriorating")
        if below_ema20:
            bits.append("price below EMA20")
        reason = "; ".join(bits) or "borderline hold"
        why_valid = "not below hard/trailing stop; no severe event risk"
        invalidation = f"close below {max(stop, new_trail):.2f} or sector becomes LAGGING"
    elif sector_status == "LAGGING" or below_ema20:
        action = "REDUCE"
        reason = "risk rising; reduce exposure unless price immediately recovers"
        why_valid = "not yet at exit trigger, but structure is weakening"
        invalidation = f"close below {max(stop, new_trail):.2f}"

    row["current_action"] = action
    if _exit_action(action):
        row["exit_reason"] = reason
        row["exit_price"] = f"{current:.2f}"
        row["exit_date"] = date.today().isoformat()
        if AUTO_CLOSE_EXIT_SIGNALS:
            row["status"] = "CLOSED"
            _append_trade(row)
        else:
            row["status"] = "ACTIVE"
    else:
        row["exit_reason"] = ""
        row["exit_price"] = ""
        row["exit_date"] = ""
        row["status"] = "ACTIVE"

    urgency, reason_text = _status_reason(action, reason)
    status_row = {
        "SYMBOL": sym,
        "ACTION": action,
        "STATUS": row.get("status", "ACTIVE"),
        "PNL_PCT": f"{pnl:.2f}",
        "CURRENT_PRICE": f"{current:.2f}",
        "ENTRY_PRICE": f"{entry:.2f}",
        "STOP_LOSS": f"{stop:.2f}",
        "TRAILING_STOP": f"{new_trail:.2f}",
        "TARGET_1": f"{target1:.2f}",
        "TARGET_1_STATUS": _target_status(current, target1),
        "TARGET_2": f"{target2:.2f}",
        "TARGET_2_STATUS": _target_status(current, target2),
        "SECTOR": sector,
        "SECTOR_STATUS": sector_status,
        "RELATIVE_STRENGTH_STATUS": rs_status,
        "EVENT_RISK_STATUS": event_status,
        "EVENT_SEVERITY": f"{severity:.0f}",
        "EVENT_TYPE": event,
        "EVENT_SOURCE_TYPE": source_type,
        "EVENT_SUMMARY": event_summary,
        "DAYS_HELD": days,
        "EXIT_RISK_SCORE": f"{_clamp(_f(exit_score)):.2f}",
        "WHY_VALID": why_valid,
        "INVALIDATION_TRIGGER": invalidation,
        "REASON": reason_text,
        "URGENCY": urgency,
        "EXIT_PRICE": f"{current:.2f}" if _exit_action(action) else "",
        "EXIT_REASON": reason if _exit_action(action) else "",
    }
    return row, status_row


def main() -> None:
    state = _load_state()
    regime = read_regime_file()
    sectors = load_sector_scores()
    news = _load_news_risk()
    updated: List[Dict[str, str]] = []
    statuses: List[Dict[str, object]] = []

    for row in state:
        new_row, status_row = _update_one(row, regime, sectors, news)
        updated.append(new_row)
        if status_row:
            statuses.append(status_row)

    _write_state(updated)
    _write_csv(PORTFOLIO_STATUS_FILE, STATUS_FIELDS, statuses)

    print("\nPORTFOLIO MONITOR")
    print("=" * 80)
    print(f"Portfolio source       : {PORTFOLIO_SOURCE}")
    print(f"Auto-close exit signals: {AUTO_CLOSE_EXIT_SIGNALS}")
    print(f"Active manual holdings : {sum(1 for r in updated if str(r.get('status')).upper() == 'ACTIVE')}")
    print(f"Status rows            : {len(statuses)}")
    print(f"Saved                  : {PORTFOLIO_STATUS_FILE}, {PORTFOLIO_STATE_FILE}")
    for r in statuses[:15]:
        print(f"{r['SYMBOL']:<18} {r['ACTION']:<20} PnL={r['PNL_PCT']}% Reason={r['REASON']}")


if __name__ == "__main__":
    main()
