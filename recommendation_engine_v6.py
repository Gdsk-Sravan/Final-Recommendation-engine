"""
recommendation_engine_v6.py - Four-bucket decision engine.

Final behavior
--------------
BUY recommendations are recommendations only. They are NOT treated as bought
unless AUTO_TRACK_RECOMMENDED_BUYS=true. Actual holdings are loaded separately by
manual_portfolio_loader.py from MANUAL_PORTFOLIO_JSON.

This engine:
- skips active manual holdings from BUY/WATCHLIST/REJECTED candidate buckets
- uses specific rejection categories, not generic PORTFOLIO_FIT_FAIL
- reserves PORTFOLIO_FIT_FAIL for good setups blocked by capacity/exposure only
- creates a clean watchlist only for true near-misses
- writes portfolio exposure truthfully, including UNKNOWN when position_pct is missing
"""

from __future__ import annotations

import csv
import os
from datetime import datetime
from typing import Dict, Iterable, List, Sequence, Tuple

from config import (
    AUTO_TRACK_RECOMMENDED_BUYS,
    CONFIDENCE_SCORES_FILE,
    MAX_ACTIVE_POSITIONS,
    MAX_PORTFOLIO_HEAT,
    MAX_SAME_SECTOR_POSITIONS,
    MAX_SECTOR_EXPOSURE_PCT,
    MIN_AVG_TRADED_VALUE,
    MIN_AVG_VOLUME,
    MIN_ENTRY_SCORE,
    MIN_RS_SCORE,
    MIN_TECH_SCORE,
    NEWS_SEVERITY_EXIT_THRESHOLD,
    NEWS_SEVERITY_WATCHLIST_THRESHOLD,
    PORTFOLIO_EXPOSURE_SUMMARY_FILE,
    PORTFOLIO_FILE,
    PORTFOLIO_SOURCE,
    PORTFOLIO_STATE_FILE,
    RECOMMENDATIONS_FILE,
    REJECTED_CANDIDATES_FILE,
    REGIME_SETTINGS,
    RISK_PER_TRADE_PCT,
    SECTOR_OVERRIDES,
    TOTAL_CAPITAL,
    UNMAPPED_SECTOR_LABEL,
    WATCHLIST_CONFIDENCE_BUFFER,
    WATCHLIST_COUNT,
    WATCHLIST_FILE,
    WATCHLIST_MAX_FAILED_GATES,
    WATCHLIST_TRADE_QUALITY_BUFFER,
)
from market_regime import read_regime_file

try:
    from correlation_engine import correlation_between
except Exception:  # pragma: no cover
    correlation_between = None

STATE_FIELDS = [
    "symbol", "sector", "entry_date", "entry_price", "setup_type", "confidence_at_entry",
    "position_pct", "stop_loss", "target_1", "target_2", "trailing_stop", "highest_price",
    "current_price", "unrealized_pnl_pct", "days_held", "current_action", "exit_date",
    "exit_price", "exit_reason", "status",
]

REC_FIELDS = [
    "SYMBOL", "SECTOR", "ACTION", "SETUP_TYPE", "TRADE_QUALITY_SCORE", "CONFIDENCE",
    "ENTRY_PRICE", "STOP_LOSS", "TARGET_1", "TARGET_2", "TRAILING_STOP", "TRAILING_STOP_START",
    "POSITION_PCT", "POSITION_AMOUNT", "REWARD_RISK", "REASON", "KEY_RISK", "PORTFOLIO_FIT",
]

WATCH_FIELDS = [
    "FINAL_RANK", "SYMBOL", "SECTOR", "SETUP_TYPE", "TRADE_QUALITY_SCORE", "CONFIDENCE",
    "REASON", "FAILED_GATES", "NEXT_CONDITION_NEEDED", "WATCHLIST_CATEGORY", "PORTFOLIO_FIT",
]

REJECT_FIELDS = [
    "FINAL_RANK", "SYMBOL", "SECTOR", "FINAL_SCORE", "CONFIDENCE", "FAILED_GATES",
    "ONE_LINE_REASON", "REJECTION_CATEGORY", "WATCHLIST_ELIGIBLE", "NEXT_CONDITION_NEEDED",
    "MARKET_REGIME", "SECTOR_CLASS", "REWARD_RISK", "NEWS_RISK", "ENTRY_QUALITY",
]

CRITICAL_REJECTION_PRIORITY = [
    "DATA_QUALITY_FAIL",
    "NEWS_RISK_FAIL",
    "LIQUIDITY_FAIL",
    "REGIME_FAIL",
    "CONFIDENCE_FAIL",
    "TRADE_QUALITY_FAIL",
    "RISK_REWARD_FAIL",
    "SECTOR_FAIL",
    "CORRELATION_FAIL",
    "PORTFOLIO_FIT_FAIL",
]

PORTFOLIO_CATEGORIES = {"PORTFOLIO_FIT_FAIL", "CORRELATION_FAIL", "DAILY_LIMIT_REACHED"}
HARD_NEVER_WATCH = {"DATA_QUALITY_FAIL", "NEWS_RISK_FAIL", "LIQUIDITY_FAIL"}


def _f(value, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _i(value, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def _norm_sector(sector: object) -> str:
    text = str(sector or "").strip()
    if not text or text.upper() in ("UNKNOWN", "NONE", "N/A", "NA"):
        return UNMAPPED_SECTOR_LABEL
    return text


def _load_rows(path: str) -> List[Dict[str, str]]:
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", newline="", encoding="utf-8", errors="ignore") as f:
            return list(csv.DictReader(f))
    except Exception:
        return []


def _write_csv(path: str, fieldnames: List[str], rows: List[Dict[str, object]]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def _load_confidence(path: str = CONFIDENCE_SCORES_FILE) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    numeric = [
        "FINAL_RANK", "FINAL_CONFIDENCE", "CONFIDENCE", "TRADE_QUALITY_SCORE", "TECH_SCORE",
        "ELITE_SCORE", "ENTRY_SCORE", "NEWS_SCORE", "RS_SCORE", "SECTOR_SCORE", "ENTRY_PRICE",
        "STOP_LOSS", "TARGET_1", "TARGET_2", "TRAILING_STOP", "TRAILING_STOP_START",
        "REWARD_RISK", "RISK_PER_SHARE", "AVG_VOLUME20", "AVG_TRADED_VALUE20", "EXPECTANCY",
        "PROFIT_FACTOR", "MAX_DRAWDOWN", "AI_SEVERITY", "LIQUIDITY_TRADABILITY_SCORE",
        "CORRELATION_PENALTY", "PORTFOLIO_FIT_SCORE", "RISK_REWARD_SCORE",
    ]
    for raw in _load_rows(path):
        sym = (raw.get("SYMBOL") or raw.get("symbol") or "").strip().upper()
        if not sym:
            continue
        row: Dict[str, object] = dict(raw)
        row["SYMBOL"] = sym
        sector_raw = row.get("SECTOR")
        if (not sector_raw or str(sector_raw).upper() in ("UNKNOWN", "NONE", "N/A", "NA")) and sym in SECTOR_OVERRIDES:
            sector_raw = SECTOR_OVERRIDES[sym]
        row["SECTOR"] = _norm_sector(sector_raw)
        for key in numeric:
            row[key] = _f(row.get(key), 0.0)
        row["BLACK_SWAN"] = _i(row.get("BLACK_SWAN"), 0)
        rows.append(row)
    rows.sort(
        key=lambda r: (
            _f(r.get("TRADE_QUALITY_SCORE")),
            _f(r.get("FINAL_CONFIDENCE", r.get("CONFIDENCE"))),
            _f(r.get("LIQUIDITY_TRADABILITY_SCORE")),
        ),
        reverse=True,
    )
    for idx, row in enumerate(rows, 1):
        row["FINAL_RANK"] = _i(row.get("FINAL_RANK"), idx) or idx
    return rows


def _load_portfolio_state(path: str = PORTFOLIO_STATE_FILE) -> List[Dict[str, str]]:
    rows = []
    for row in _load_rows(path):
        if not row.get("symbol"):
            continue
        out = {field: row.get(field, "") for field in STATE_FIELDS}
        out["sector"] = _norm_sector(out.get("sector"))
        rows.append(out)
    return rows


def _active_positions(state: List[Dict[str, str]]) -> List[Dict[str, str]]:
    return [r for r in state if str(r.get("status", "ACTIVE")).upper() == "ACTIVE"]


def _active_symbols(state: List[Dict[str, str]]) -> set:
    return {str(r.get("symbol", "")).upper() for r in _active_positions(state) if r.get("symbol")}


def _known_active_exposure(state: List[Dict[str, str]]) -> float:
    return sum(_f(r.get("position_pct"), 0.0) for r in _active_positions(state) if str(r.get("position_pct", "")).strip())


def _missing_position_pct_count(state: List[Dict[str, str]]) -> int:
    return sum(1 for r in _active_positions(state) if not str(r.get("position_pct", "")).strip())


def _sector_exposure(state: List[Dict[str, str]]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for r in _active_positions(state):
        sector = _norm_sector(r.get("sector"))
        if sector == UNMAPPED_SECTOR_LABEL:
            continue
        pct = _f(r.get("position_pct"), 0.0)
        if pct <= 0:
            continue
        out[sector] = out.get(sector, 0.0) + pct
    return out


def _active_sector_count(state: List[Dict[str, str]], sector: str) -> int:
    sector = _norm_sector(sector)
    if sector == UNMAPPED_SECTOR_LABEL:
        return 0
    return sum(1 for r in _active_positions(state) if _norm_sector(r.get("sector")) == sector)


def _max_correlation(symbol: str, active_symbols: Iterable[str]) -> Tuple[float, str]:
    if correlation_between is None:
        return 0.0, ""
    best = 0.0
    best_sym = ""
    for other in active_symbols:
        if not other:
            continue
        try:
            corr = _f(correlation_between(symbol, other), 0.0)
        except Exception:
            corr = 0.0
        if corr > best:
            best = corr
            best_sym = str(other)
    return best, best_sym


def _category(gates: Sequence[Tuple[str, str]]) -> str:
    cats = [c for c, _ in gates]
    for cat in CRITICAL_REJECTION_PRIORITY:
        if cat in cats:
            return cat
    return cats[0] if cats else "NOT_SELECTED"


def _messages(gates: Sequence[Tuple[str, str]]) -> List[str]:
    return [m for _, m in gates if m]


def _position_size(row: Dict[str, object], regime_info: Dict[str, object], state: List[Dict[str, str]]) -> Tuple[float, float, str]:
    entry = _f(row.get("ENTRY_PRICE"))
    stop = _f(row.get("STOP_LOSS"))
    confidence = _f(row.get("FINAL_CONFIDENCE", row.get("CONFIDENCE")))
    sector = _norm_sector(row.get("SECTOR"))
    if entry <= 0 or stop <= 0 or entry <= stop:
        return 0.0, 0.0, "invalid stop distance"

    risk_amount = TOTAL_CAPITAL * RISK_PER_TRADE_PCT / 100.0
    raw_pct = (risk_amount / (entry - stop)) * entry / TOTAL_CAPITAL * 100.0 if TOTAL_CAPITAL > 0 else 0.0
    confidence_cap = 16.0 if confidence >= 92 else 13.0 if confidence >= 88 else 10.0 if confidence >= 82 else 6.0
    regime_cap = _f(regime_info.get("max_position_size"), 7.0)
    max_total = _f(regime_info.get("max_total_portfolio_exposure"), _f(regime_info.get("max_total_exposure"), 35.0))
    known_exposure = _known_active_exposure(state)
    total_remaining = max(0.0, max_total - known_exposure)
    sector_remaining = 999.0
    if sector != UNMAPPED_SECTOR_LABEL:
        sector_remaining = max(0.0, min(_f(regime_info.get("max_sector_exposure"), MAX_SECTOR_EXPOSURE_PCT), MAX_SECTOR_EXPOSURE_PCT) - _sector_exposure(state).get(sector, 0.0))
    heat_remaining = max(0.0, MAX_PORTFOLIO_HEAT - len(_active_positions(state)) * RISK_PER_TRADE_PCT)
    heat_cap_pct = heat_remaining / max(RISK_PER_TRADE_PCT, 0.01) * raw_pct if heat_remaining > 0 else 0.0
    final_pct = max(0.0, min(raw_pct, confidence_cap, regime_cap, total_remaining, sector_remaining, heat_cap_pct))
    reason = "ok" if final_pct > 0 else "no remaining portfolio capacity"
    return round(final_pct, 2), round(TOTAL_CAPITAL * final_pct / 100.0, 2), reason


def _gate_candidate(row: Dict[str, object], regime_info: Dict[str, object], state: List[Dict[str, str]], selected: List[Dict[str, object]]) -> Dict[str, object]:
    regime = str(regime_info.get("regime", "TRANSITION")).upper()
    settings = REGIME_SETTINGS.get(regime, REGIME_SETTINGS.get("TRANSITION", {}))
    min_conf = _f(regime_info.get("min_buy_confidence"), settings.get("min_buy_confidence", 85))
    min_tq = _f(regime_info.get("min_trade_quality_score"), settings.get("min_trade_quality_score", 80))
    min_rr = _f(regime_info.get("min_reward_risk"), settings.get("min_reward_risk", 1.8))

    conf = _f(row.get("FINAL_CONFIDENCE", row.get("CONFIDENCE")))
    tq = _f(row.get("TRADE_QUALITY_SCORE"))
    rr = _f(row.get("REWARD_RISK"))
    sector = _norm_sector(row.get("SECTOR"))
    sector_class = str(row.get("SECTOR_CLASS", "NEUTRAL") or "NEUTRAL").upper()
    setup = str(row.get("SETUP_TYPE", "UNKNOWN") or "UNKNOWN").upper()

    hard: List[Tuple[str, str]] = []
    soft: List[Tuple[str, str]] = []

    def h(cat: str, msg: str) -> None:
        hard.append((cat, msg))

    def s(cat: str, msg: str) -> None:
        soft.append((cat, msg))

    if _f(row.get("ENTRY_PRICE")) <= 0 or _f(row.get("STOP_LOSS")) <= 0 or _f(row.get("TARGET_1")) <= 0 or _f(row.get("TARGET_2")) <= 0:
        h("DATA_QUALITY_FAIL", "entry, stop, or target missing")
    if _i(row.get("BLACK_SWAN"), 0):
        h("NEWS_RISK_FAIL", "black-swan event risk")
    severity = _f(row.get("AI_SEVERITY"))
    if severity >= NEWS_SEVERITY_EXIT_THRESHOLD:
        h("NEWS_RISK_FAIL", f"severe event/news risk {severity:.0f}")
    elif severity >= NEWS_SEVERITY_WATCHLIST_THRESHOLD:
        s("NEWS_RISK_FAIL", f"moderate event/news risk {severity:.0f}")
    if _f(row.get("AVG_VOLUME20")) < MIN_AVG_VOLUME or _f(row.get("AVG_TRADED_VALUE20")) < MIN_AVG_TRADED_VALUE:
        h("LIQUIDITY_FAIL", "liquidity below tradability minimum")
    if rr < min_rr:
        cat = "RISK_REWARD_FAIL"
        msg = f"reward/risk {rr:.2f} below required {min_rr:.2f}"
        if rr >= max(1.2, min_rr - 0.35):
            s(cat, msg)
        else:
            h(cat, msg)
    if conf < min_conf:
        msg = f"confidence {conf:.1f} below {regime} threshold {min_conf:.1f}"
        if conf >= min_conf - WATCHLIST_CONFIDENCE_BUFFER:
            s("CONFIDENCE_FAIL", msg)
        else:
            h("CONFIDENCE_FAIL", msg)
    if tq < min_tq:
        msg = f"trade quality {tq:.1f} below required {min_tq:.1f}"
        if tq >= min_tq - WATCHLIST_TRADE_QUALITY_BUFFER:
            s("TRADE_QUALITY_FAIL", msg)
        else:
            h("TRADE_QUALITY_FAIL", msg)
    if _f(row.get("ENTRY_SCORE")) < MIN_ENTRY_SCORE:
        h("TRADE_QUALITY_FAIL", f"entry score {_f(row.get('ENTRY_SCORE')):.1f} below {MIN_ENTRY_SCORE}")
    if _f(row.get("TECH_SCORE")) < MIN_TECH_SCORE:
        h("TRADE_QUALITY_FAIL", f"technical score {_f(row.get('TECH_SCORE')):.1f} below {MIN_TECH_SCORE}")
    if _f(row.get("RS_SCORE")) < MIN_RS_SCORE:
        h("TRADE_QUALITY_FAIL", f"relative strength {_f(row.get('RS_SCORE')):.1f} below {MIN_RS_SCORE}")
    if not bool(regime_info.get("fresh_buying_allowed", True)):
        h("REGIME_FAIL", f"fresh buying blocked in {regime}")
    if setup in [str(x).upper() for x in settings.get("restricted_setup_types", [])]:
        s("TRADE_QUALITY_FAIL", f"setup {setup} restricted in {regime}")
    if sector == UNMAPPED_SECTOR_LABEL:
        s("SECTOR_FAIL", "sector unmapped; sector confirmation unavailable")
    elif sector_class == "LAGGING":
        h("SECTOR_FAIL", "sector is LAGGING")
    elif sector_class == "WEAKENING":
        s("SECTOR_FAIL", "sector is WEAKENING")
    elif sector_class not in ("LEADING", "IMPROVING"):
        s("SECTOR_FAIL", f"sector is {sector_class}, not leading/improving")

    active = _active_positions(state)
    active_symbols = [r.get("symbol", "") for r in active]
    if len(active) >= MAX_ACTIVE_POSITIONS:
        h("PORTFOLIO_FIT_FAIL", f"maximum active positions reached ({len(active)}/{MAX_ACTIVE_POSITIONS})")
    if sector != UNMAPPED_SECTOR_LABEL and _active_sector_count(state, sector) >= MAX_SAME_SECTOR_POSITIONS:
        s("PORTFOLIO_FIT_FAIL", f"same-sector active position cap reached for {sector}")
    max_corr, corr_sym = _max_correlation(str(row.get("SYMBOL")), active_symbols)
    if max_corr >= _f(row.get("MAX_CORRELATION_WITH_HOLDINGS"), 0.78):
        s("CORRELATION_FAIL", f"correlation {max_corr:.2f} with active holding {corr_sym}")
    for selected_row in selected:
        if correlation_between is None:
            continue
        try:
            corr = _f(correlation_between(str(row.get("SYMBOL")), str(selected_row.get("SYMBOL"))), 0.0)
        except Exception:
            corr = 0.0
        if corr >= 0.78:
            s("CORRELATION_FAIL", f"near-duplicate with selected buy {selected_row.get('SYMBOL')} ({corr:.2f})")
            break

    pct, amount, size_reason = _position_size(row, regime_info, state)
    if pct <= 0 and not any(c in HARD_NEVER_WATCH for c, _ in hard):
        h("PORTFOLIO_FIT_FAIL", size_reason)

    all_gates = hard + soft
    return {
        "passed": not hard and not soft,
        "hard": hard,
        "soft": soft,
        "all": all_gates,
        "category": _category(all_gates),
        "position_pct": pct,
        "position_amount": amount,
        "portfolio_fit": "OK" if pct > 0 and not any(c == "PORTFOLIO_FIT_FAIL" for c, _ in all_gates) else "CONSTRAINED",
        "max_corr": max_corr,
        "corr_symbol": corr_sym,
        "min_conf": min_conf,
        "min_tq": min_tq,
    }


def _one_line_reason(row: Dict[str, object], gates: Sequence[Tuple[str, str]]) -> str:
    msgs = _messages(gates)
    if msgs:
        return msgs[0]
    parts: List[str] = []
    sector_class = str(row.get("SECTOR_CLASS", "")).upper()
    if sector_class in ("LEADING", "IMPROVING"):
        parts.append(f"{sector_class.lower()} sector")
    if _f(row.get("RS_SCORE")) >= 65:
        parts.append("strong relative strength")
    if _f(row.get("REWARD_RISK")) >= 2.2:
        parts.append("good reward/risk")
    if _f(row.get("ENTRY_SCORE")) >= 70:
        parts.append("clean entry")
    return ", ".join(parts) if parts else "passed deterministic quality checks"


def _next_condition(gates: Sequence[Tuple[str, str]], row: Dict[str, object], regime: str) -> str:
    cats = [c for c, _ in gates]
    text = "; ".join(_messages(gates)).lower()
    if "PORTFOLIO_FIT_FAIL" in cats:
        return "Free portfolio capacity or reduce overlapping exposure."
    if "CORRELATION_FAIL" in cats:
        return "Wait for correlation/exposure to reduce or choose stronger uncorrelated name."
    if "CONFIDENCE_FAIL" in cats or "TRADE_QUALITY_FAIL" in cats:
        return "Needs stronger price/volume confirmation or improved regime support."
    if "RISK_REWARD_FAIL" in cats:
        return "Wait for better entry near support or clearer upside target."
    if "SECTOR_FAIL" in cats:
        if "unmapped" in text:
            return "Map sector or wait for stronger stock-specific confirmation."
        return "Wait for sector to improve to LEADING/IMPROVING."
    if "REGIME_FAIL" in cats:
        return f"Needs {regime} regime confirmation to improve."
    if "NEWS_RISK_FAIL" in cats:
        return "Wait for event risk to clear and setup to reconfirm."
    return "Needs failed gate to clear."


def _watchlist_eligible(gate: Dict[str, object], conf: float, tq: float) -> bool:
    hard: List[Tuple[str, str]] = gate["hard"]
    soft: List[Tuple[str, str]] = gate["soft"]
    all_gates = hard + soft
    cats = [c for c, _ in all_gates]
    if any(c in HARD_NEVER_WATCH for c in cats):
        return False
    min_conf = _f(gate.get("min_conf"), 85)
    min_tq = _f(gate.get("min_tq"), 80)
    near_quality = conf >= min_conf - WATCHLIST_CONFIDENCE_BUFFER and tq >= min_tq - WATCHLIST_TRADE_QUALITY_BUFFER
    portfolio_only = bool(cats) and all(c in PORTFOLIO_CATEGORIES for c in cats) and tq >= min_tq - WATCHLIST_TRADE_QUALITY_BUFFER
    soft_near = not hard and len(soft) <= WATCHLIST_MAX_FAILED_GATES and near_quality
    hard_near = len(hard) <= WATCHLIST_MAX_FAILED_GATES and near_quality and all(c in {"CONFIDENCE_FAIL", "TRADE_QUALITY_FAIL", "RISK_REWARD_FAIL", "REGIME_FAIL", "SECTOR_FAIL"} for c, _ in hard)
    return bool(portfolio_only or soft_near or hard_near)


def _buy_state_row(row: Dict[str, object], position_pct: float) -> Dict[str, str]:
    today = datetime.now().strftime("%Y-%m-%d")
    price = _f(row.get("ENTRY_PRICE"))
    return {
        "symbol": str(row.get("SYMBOL")), "sector": _norm_sector(row.get("SECTOR")),
        "entry_date": today, "entry_price": f"{price:.2f}", "setup_type": str(row.get("SETUP_TYPE", "UNKNOWN")),
        "confidence_at_entry": f"{_f(row.get('FINAL_CONFIDENCE', row.get('CONFIDENCE'))):.2f}",
        "position_pct": f"{position_pct:.2f}", "stop_loss": f"{_f(row.get('STOP_LOSS')):.2f}",
        "target_1": f"{_f(row.get('TARGET_1')):.2f}", "target_2": f"{_f(row.get('TARGET_2')):.2f}",
        "trailing_stop": f"{_f(row.get('TRAILING_STOP')):.2f}", "highest_price": f"{price:.2f}",
        "current_price": f"{price:.2f}", "unrealized_pnl_pct": "0.00", "days_held": "0",
        "current_action": "HOLD", "exit_date": "", "exit_price": "", "exit_reason": "", "status": "ACTIVE",
    }


def _write_portfolio_state(rows: List[Dict[str, str]]) -> None:
    _write_csv(PORTFOLIO_STATE_FILE, STATE_FIELDS, rows)


def _write_legacy_portfolio(state: List[Dict[str, str]]) -> None:
    with open(PORTFOLIO_FILE, "w", encoding="utf-8") as f:
        f.write("# Manual holdings only unless AUTO_TRACK_RECOMMENDED_BUYS=true.\n")
        f.write("# SYMBOL,BUY_PRICE,CONFIDENCE,SECTOR,POSITION_PCT,ENTRY_DATE\n")
        for row in _active_positions(state):
            f.write(f"{row.get('symbol')},{row.get('entry_price')},{row.get('confidence_at_entry')},{row.get('sector')},{row.get('position_pct')},{row.get('entry_date')}\n")


def _write_exposure_summary(state: List[Dict[str, str]], regime_info: Dict[str, object]) -> None:
    active = _active_positions(state)
    known = _known_active_exposure(state)
    missing = _missing_position_pct_count(state)
    max_total = _f(regime_info.get("max_total_portfolio_exposure"), _f(regime_info.get("max_total_exposure"), 0.0))
    available = max(0.0, max_total - known) if missing == 0 else "UNKNOWN"
    exposure_status = "KNOWN" if missing == 0 else "PARTIAL_UNKNOWN"
    rows: List[Dict[str, object]] = [
        {"METRIC": "portfolio_source", "VALUE": PORTFOLIO_SOURCE},
        {"METRIC": "auto_track_recommended_buys", "VALUE": str(AUTO_TRACK_RECOMMENDED_BUYS).lower()},
        {"METRIC": "active_positions", "VALUE": len(active)},
        {"METRIC": "known_total_exposure_pct", "VALUE": round(known, 2)},
        {"METRIC": "total_exposure_pct", "VALUE": round(known, 2) if missing == 0 else "UNKNOWN"},
        {"METRIC": "exposure_status", "VALUE": exposure_status},
        {"METRIC": "missing_position_pct_count", "VALUE": missing},
        {"METRIC": "max_total_exposure_pct", "VALUE": max_total},
        {"METRIC": "available_capacity_pct", "VALUE": available},
        {"METRIC": "max_active_positions", "VALUE": MAX_ACTIVE_POSITIONS},
    ]
    for sector, pct in sorted(_sector_exposure(state).items(), key=lambda x: x[1], reverse=True):
        rows.append({"METRIC": f"sector_exposure_{sector}", "VALUE": round(pct, 2)})
    _write_csv(PORTFOLIO_EXPOSURE_SUMMARY_FILE, ["METRIC", "VALUE"], rows)


def _rec_row(row: Dict[str, object], gate: Dict[str, object], reason: str) -> Dict[str, object]:
    return {
        "SYMBOL": row.get("SYMBOL"), "SECTOR": _norm_sector(row.get("SECTOR")), "ACTION": "BUY",
        "SETUP_TYPE": row.get("SETUP_TYPE", "UNKNOWN"), "TRADE_QUALITY_SCORE": f"{_f(row.get('TRADE_QUALITY_SCORE')):.2f}",
        "CONFIDENCE": f"{_f(row.get('FINAL_CONFIDENCE', row.get('CONFIDENCE'))):.2f}",
        "ENTRY_PRICE": f"{_f(row.get('ENTRY_PRICE')):.2f}", "STOP_LOSS": f"{_f(row.get('STOP_LOSS')):.2f}",
        "TARGET_1": f"{_f(row.get('TARGET_1')):.2f}", "TARGET_2": f"{_f(row.get('TARGET_2')):.2f}",
        "TRAILING_STOP": f"{_f(row.get('TRAILING_STOP')):.2f}", "TRAILING_STOP_START": f"{_f(row.get('TRAILING_STOP_START')):.2f}",
        "POSITION_PCT": f"{_f(gate.get('position_pct')):.2f}", "POSITION_AMOUNT": f"{_f(gate.get('position_amount')):.2f}",
        "REWARD_RISK": f"{_f(row.get('REWARD_RISK')):.2f}", "REASON": reason,
        "KEY_RISK": row.get("RISK_FLAGS", "none") or "none", "PORTFOLIO_FIT": gate.get("portfolio_fit", ""),
    }


def _reject_row(row: Dict[str, object], rank: int, gates: Sequence[Tuple[str, str]], category: str, watch: bool, next_needed: str, regime: str) -> Dict[str, object]:
    return {
        "FINAL_RANK": rank, "SYMBOL": row.get("SYMBOL"), "SECTOR": _norm_sector(row.get("SECTOR")),
        "FINAL_SCORE": f"{_f(row.get('TRADE_QUALITY_SCORE')):.2f}",
        "CONFIDENCE": f"{_f(row.get('FINAL_CONFIDENCE', row.get('CONFIDENCE'))):.2f}",
        "FAILED_GATES": "; ".join(_messages(gates)) if gates else "not selected",
        "ONE_LINE_REASON": _one_line_reason(row, gates), "REJECTION_CATEGORY": category,
        "WATCHLIST_ELIGIBLE": "true" if watch else "false", "NEXT_CONDITION_NEEDED": next_needed,
        "MARKET_REGIME": regime, "SECTOR_CLASS": row.get("SECTOR_CLASS", "NEUTRAL"),
        "REWARD_RISK": f"{_f(row.get('REWARD_RISK')):.2f}",
        "NEWS_RISK": f"severity={_f(row.get('AI_SEVERITY')):.0f}, black_swan={_i(row.get('BLACK_SWAN'))}",
        "ENTRY_QUALITY": f"{_f(row.get('ENTRY_SCORE')):.2f}",
    }


def main() -> None:
    scored = _load_confidence()
    regime_info = read_regime_file()
    regime = str(regime_info.get("regime", "TRANSITION")).upper()
    settings = REGIME_SETTINGS.get(regime, REGIME_SETTINGS.get("TRANSITION", {}))
    max_new = _i(regime_info.get("max_new_buys"), settings.get("max_new_buys", 0))
    state = _load_portfolio_state()
    active_symbols = _active_symbols(state)

    buys: List[Dict[str, object]] = []
    watch: List[Dict[str, object]] = []
    rejected: List[Dict[str, object]] = []

    if not scored:
        _write_csv(RECOMMENDATIONS_FILE, REC_FIELDS, [])
        _write_csv(WATCHLIST_FILE, WATCH_FIELDS, [])
        _write_csv(REJECTED_CANDIDATES_FILE, REJECT_FIELDS, [])
        _write_portfolio_state(state)
        _write_exposure_summary(state, regime_info)
        print("[ERROR] No confidence score rows found.")
        return

    for row in scored:
        symbol = str(row.get("SYMBOL", "")).upper()
        if symbol in active_symbols:
            # Active manual holdings belong only in HOLD/MANAGE or EXIT from portfolio_monitor.
            continue

        gate = _gate_candidate(row, regime_info, state, buys)
        gates = list(gate["all"])
        rank = _i(row.get("FINAL_RANK"), len(rejected) + len(watch) + len(buys) + 1)
        conf = _f(row.get("FINAL_CONFIDENCE", row.get("CONFIDENCE")))
        tq = _f(row.get("TRADE_QUALITY_SCORE"))
        category = str(gate.get("category") or _category(gates))
        next_needed = _next_condition(gates, row, regime)
        watch_eligible = _watchlist_eligible(gate, conf, tq)

        if gate["passed"] and len(buys) < max_new:
            reason = _one_line_reason(row, [])
            rec = _rec_row(row, gate, reason)
            buys.append(rec)
            if AUTO_TRACK_RECOMMENDED_BUYS:
                state.append(_buy_state_row(row, _f(gate.get("position_pct"))))
                active_symbols.add(symbol)
        else:
            if gate["passed"] and len(buys) >= max_new:
                gates = [("DAILY_LIMIT_REACHED", f"daily max new buys reached ({max_new})")]
                category = "DAILY_LIMIT_REACHED"
                next_needed = "Wait for next trading day or free a stronger slot."
                watch_eligible = tq >= _f(gate.get("min_tq"), 80) - WATCHLIST_TRADE_QUALITY_BUFFER
            if watch_eligible and len(watch) < max(WATCHLIST_COUNT, 1):
                watch.append({
                    "FINAL_RANK": rank, "SYMBOL": row.get("SYMBOL"), "SECTOR": _norm_sector(row.get("SECTOR")),
                    "SETUP_TYPE": row.get("SETUP_TYPE", "UNKNOWN"), "TRADE_QUALITY_SCORE": f"{tq:.2f}",
                    "CONFIDENCE": f"{conf:.2f}", "REASON": _one_line_reason(row, gates),
                    "FAILED_GATES": "; ".join(_messages(gates)), "NEXT_CONDITION_NEEDED": next_needed,
                    "WATCHLIST_CATEGORY": category, "PORTFOLIO_FIT": gate.get("portfolio_fit", ""),
                })
            rejected.append(_reject_row(row, rank, gates, category, watch_eligible, next_needed, regime))

    _write_csv(RECOMMENDATIONS_FILE, REC_FIELDS, buys)
    _write_csv(WATCHLIST_FILE, WATCH_FIELDS, watch)
    _write_csv(REJECTED_CANDIDATES_FILE, REJECT_FIELDS, rejected[:300])
    _write_portfolio_state(state)
    _write_legacy_portfolio(state)
    _write_exposure_summary(state, regime_info)

    print("\nRECOMMENDATION ENGINE V6")
    print("=" * 100)
    print(f"Regime                    : {regime}")
    print(f"Portfolio source          : {PORTFOLIO_SOURCE}")
    print(f"Auto-track recommended BUY: {AUTO_TRACK_RECOMMENDED_BUYS}")
    print(f"Manual active holdings    : {len(_active_positions(state))}")
    print(f"Max new buys              : {max_new}")
    print(f"BUY recommendations       : {len(buys)}")
    print(f"WATCHLIST                 : {len(watch)}")
    print(f"Rejected log              : {len(rejected[:300])}")
    if not buys:
        print("BUY: None - no high-quality setup passed all gates today.")
    for rec in buys:
        print(f"BUY {rec['SYMBOL']:<18} TQ={rec['TRADE_QUALITY_SCORE']} Conf={rec['CONFIDENCE']} RR={rec['REWARD_RISK']} Size={rec['POSITION_PCT']}%")
    print(f"Saved                     : {RECOMMENDATIONS_FILE}, {WATCHLIST_FILE}, {REJECTED_CANDIDATES_FILE}")


if __name__ == "__main__":
    main()
