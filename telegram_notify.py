"""
telegram_notify.py - Compact execution-style daily brief.

Report design fixes:
- no fake 0.00% exposure when manual position sizes are missing
- BUY recommendations remain separate from actual holdings
- active manual holdings do not appear as WATCHLIST/REJECTED
- watchlist/rejection reasons are specific and actionable
- news exits show evidence when available
"""

from __future__ import annotations

import csv
import json
import os
import time
from typing import Dict, List

import requests

from config import (
    AI_VALIDATION_REPORT_FILE,
    CORRELATION_REPORT_FILE,
    DELAY_BETWEEN_MSGS,
    MESSAGE_CHAR_LIMIT,
    PORTFOLIO_EXPOSURE_SUMMARY_FILE,
    PORTFOLIO_SOURCE_REPORT_FILE,
    PORTFOLIO_STATE_FILE,
    PORTFOLIO_STATUS_FILE,
    RECOMMENDATIONS_FILE,
    REJECTED_CANDIDATES_FILE,
    REPORT_MAX_REJECTED,
    REPORT_MAX_WATCHLIST,
    SECTOR_SCORES_FILE,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    TELEGRAM_REPORT_FILE,
    UNMAPPED_SECTOR_LABEL,
    WATCHLIST_FILE,
)
from market_regime import read_regime_file

EXIT_ACTIONS = {
    "SELL", "STOP_LOSS_EXIT", "TRAILING_STOP_EXIT", "TIME_EXIT", "NEWS_RISK_EXIT",
    "SECTOR_WEAKNESS_EXIT", "MARKET_REGIME_EXIT",
}
CAUTION_ACTIONS = {"HOLD_CAUTION", "REDUCE", "BOOK_PROFIT"}


def _read_csv(path: str) -> List[Dict[str, str]]:
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", newline="", encoding="utf-8", errors="ignore") as f:
            return list(csv.DictReader(f))
    except Exception:
        return []


def _read_json(path: str) -> Dict:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _read_text(path: str, limit: int = 800) -> str:
    if not os.path.exists(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read(limit)
    except Exception:
        return ""


def _f(v, default: float = 0.0) -> float:
    try:
        if v is None or v == "":
            return default
        return float(v)
    except Exception:
        return default


def _top(rows: List[Dict[str, str]], n: int) -> List[Dict[str, str]]:
    return rows[: max(0, n)]


def _metric(rows: List[Dict[str, str]], name: str, default: str = "") -> str:
    for row in rows:
        if row.get("METRIC") == name:
            return str(row.get("VALUE", default))
    return default


def _section(title: str) -> List[str]:
    return ["", title, "-" * len(title)]


def _fmt_num(v, suffix: str = "") -> str:
    try:
        return f"{float(v):.1f}{suffix}"
    except Exception:
        return str(v) if str(v).strip() else "NA"


def _sector_groups(sectors: List[Dict[str, str]]) -> Dict[str, List[Dict[str, str]]]:
    groups = {"LEADING": [], "IMPROVING": [], "NEUTRAL": [], "WEAKENING": [], "LAGGING": []}
    for row in sectors:
        cls = str(row.get("CLASSIFICATION", row.get("classification", "NEUTRAL"))).upper()
        groups.setdefault(cls, []).append(row)
    for key in groups:
        groups[key].sort(key=lambda r: _f(r.get("SECTOR_SCORE", r.get("sector_score"))), reverse=True)
    return groups


def _fmt_sector(rows: List[Dict[str, str]], n: int = 4) -> str:
    vals = []
    for row in _top(rows, n):
        sec = row.get("SECTOR") or row.get("sector") or ""
        score = row.get("SECTOR_SCORE") or row.get("sector_score") or ""
        if sec:
            vals.append(f"{sec}({_fmt_num(score)})")
    return ", ".join(vals) if vals else "None"


def _ai_status() -> str:
    val = _read_json(AI_VALIDATION_REPORT_FILE)
    if not val:
        return "Not run"
    status = str(val.get("status", "Unknown"))
    if status == "ok":
        return "Applied"
    meta = val.get("meta") if isinstance(val.get("meta"), dict) else {}
    err = meta.get("error") or val.get("message") or "deterministic report used"
    if "missing" in str(err).lower():
        return "Unavailable - missing/disabled key"
    if "json" in str(err).lower():
        return "Unavailable - invalid JSON"
    if "http" in str(err).lower():
        return f"Unavailable - {str(err)[:60]}"
    return f"Unavailable - {str(err)[:60]}"


def _portfolio_summary(state: List[Dict[str, str]], exposure_rows: List[Dict[str, str]]) -> Dict[str, object]:
    active = [r for r in state if str(r.get("status", "ACTIVE")).upper() == "ACTIVE"]
    known_exposure = _metric(exposure_rows, "known_total_exposure_pct", "")
    total_exposure = _metric(exposure_rows, "total_exposure_pct", "")
    exposure_status = _metric(exposure_rows, "exposure_status", "")
    missing = _metric(exposure_rows, "missing_position_pct_count", "0")
    available = _metric(exposure_rows, "available_capacity_pct", "")
    if not exposure_rows:
        known = sum(_f(r.get("position_pct")) for r in active if str(r.get("position_pct", "")).strip())
        missing_count = sum(1 for r in active if not str(r.get("position_pct", "")).strip())
        known_exposure = f"{known:.2f}"
        total_exposure = f"{known:.2f}" if missing_count == 0 else "UNKNOWN"
        exposure_status = "KNOWN" if missing_count == 0 else "PARTIAL_UNKNOWN"
        missing = str(missing_count)
        available = "UNKNOWN" if missing_count else ""
    return {
        "active": active,
        "known_exposure": known_exposure,
        "total_exposure": total_exposure or "UNKNOWN",
        "exposure_status": exposure_status or "UNKNOWN",
        "missing_position_pct_count": missing,
        "available_capacity": available or "UNKNOWN",
    }


def _buy_blockers(regime: Dict[str, object], ps: Dict[str, object], rejected: List[Dict[str, str]]) -> List[str]:
    blockers: List[str] = []
    regime_name = str(regime.get("regime", "TRANSITION"))
    if regime_name in ("TRANSITION", "WEAK_SIDEWAYS", "BEAR", "STRONG_BEAR", "HIGH_VOLATILITY"):
        blockers.append(f"regime is {regime_name}")
    if ps.get("active"):
        blockers.append(f"{len(ps['active'])} active manual holdings")
    if ps.get("exposure_status") != "KNOWN":
        blockers.append("portfolio exposure partially unknown")
    if rejected:
        cats: Dict[str, int] = {}
        for row in rejected[:30]:
            cat = row.get("REJECTION_CATEGORY", "OTHER") or "OTHER"
            cats[cat] = cats.get(cat, 0) + 1
        common = sorted(cats.items(), key=lambda x: x[1], reverse=True)[:2]
        if common:
            blockers.append("main candidate fails: " + ", ".join(f"{k}({v})" for k, v in common))
    return blockers[:4]


def _status_split(status: List[Dict[str, str]]) -> Dict[str, List[Dict[str, str]]]:
    exits: List[Dict[str, str]] = []
    caution: List[Dict[str, str]] = []
    holds: List[Dict[str, str]] = []
    for row in status:
        action = str(row.get("ACTION", "")).upper()
        if action in EXIT_ACTIONS:
            exits.append(row)
        elif action in CAUTION_ACTIONS:
            caution.append(row)
        elif action:
            holds.append(row)
    return {"exits": exits, "caution": caution, "holds": holds}


def build_report() -> str:
    regime = read_regime_file()
    sectors = _read_csv(SECTOR_SCORES_FILE)
    groups = _sector_groups(sectors)
    recs = [r for r in _read_csv(RECOMMENDATIONS_FILE) if str(r.get("ACTION", "")).upper() == "BUY"]
    watch = _read_csv(WATCHLIST_FILE)
    rejected = _read_csv(REJECTED_CANDIDATES_FILE)
    status = _read_csv(PORTFOLIO_STATUS_FILE)
    state = _read_csv(PORTFOLIO_STATE_FILE)
    exposure_rows = _read_csv(PORTFOLIO_EXPOSURE_SUMMARY_FILE)
    corr = _read_csv(CORRELATION_REPORT_FILE)
    ps = _portfolio_summary(state, exposure_rows)
    split = _status_split(status)
    source_report = _read_text(PORTFOLIO_SOURCE_REPORT_FILE)

    max_new = regime.get("max_new_buys", "")
    min_conf = regime.get("min_buy_confidence", "")
    min_tq = regime.get("min_trade_quality_score", "")
    active_count = len(ps["active"])
    exposure_text = str(ps["total_exposure"])
    if exposure_text != "UNKNOWN":
        exposure_text = _fmt_num(exposure_text, "%")
    else:
        exposure_text = f"UNKNOWN (known {_fmt_num(ps.get('known_exposure'), '%')}, missing {ps.get('missing_position_pct_count')})"

    lines: List[str] = []
    lines.append("SWING TRADE DAILY BRIEF")
    lines.append("Decision-quality lifecycle engine")
    lines.append("")
    lines.append("MARKET")
    lines.append("------")
    lines.append(
        f"Regime: {regime.get('regime', 'TRANSITION')} | Score {_fmt_num(regime.get('regime_score', regime.get('score', '')))} | "
        f"Vol: {regime.get('volatility_status', regime.get('volatility_score', 'NA'))}"
    )
    lines.append(f"Breadth: EMA20 {_fmt_num(regime.get('breadth_ema20_pct', ''), '%')} | EMA50 {_fmt_num(regime.get('breadth_ema50_pct', ''), '%')}")
    lines.append(f"Buying: {regime.get('fresh_buying_allowed', '')} | Max buys {max_new} | Required Conf {min_conf} / TQ {min_tq}")

    lines.append("")
    lines.append("PORTFOLIO")
    lines.append("---------")
    lines.append(f"Source: Manual JSON | Active {active_count} | Exposure {exposure_text} | Capacity {ps.get('available_capacity')}")
    lines.append(f"Risk: exits {len(split['exits'])}, caution {len(split['caution'])}, AI {_ai_status()}")
    if "invalid JSON" in source_report or "missing/invalid" in source_report:
        lines.append("Portfolio input warning: check MANUAL_PORTFOLIO_JSON.")

    lines += _section("SECTORS")
    lines.append("Leading: " + _fmt_sector(groups.get("LEADING", [])))
    lines.append("Improving: " + _fmt_sector(groups.get("IMPROVING", [])))
    lines.append("Weakening: " + _fmt_sector(groups.get("WEAKENING", [])))
    lines.append("Lagging: " + _fmt_sector(groups.get("LAGGING", [])))

    lines += _section("BUY")
    if not recs:
        lines.append("None - no high-quality setup passed all gates today.")
        blockers = _buy_blockers(regime, ps, rejected)
        if blockers:
            lines.append("Main blockers: " + "; ".join(blockers) + ".")
    for idx, row in enumerate(recs, 1):
        lines.append(
            f"{idx}. {row.get('SYMBOL')} | {row.get('SECTOR')} | {row.get('SETUP_TYPE')} | "
            f"TQ {_fmt_num(row.get('TRADE_QUALITY_SCORE'))} | Conf {_fmt_num(row.get('CONFIDENCE'))} | RR {_fmt_num(row.get('REWARD_RISK'))}"
        )
        lines.append(
            f"   Entry {row.get('ENTRY_PRICE')} | Stop {row.get('STOP_LOSS')} | "
            f"T1 {row.get('TARGET_1')} | T2 {row.get('TARGET_2')} | Size {row.get('POSITION_PCT')}%"
        )
        lines.append(f"   Reason: {row.get('REASON')}")
        if row.get("KEY_RISK") and str(row.get("KEY_RISK")).lower() != "none":
            lines.append(f"   Risk: {row.get('KEY_RISK')}")

    lines += _section("WATCHLIST")
    if not watch:
        lines.append("No clean near-miss setup today.")
    for idx, row in enumerate(_top(watch, REPORT_MAX_WATCHLIST), 1):
        lines.append(
            f"{idx}. {row.get('SYMBOL')} | {row.get('SECTOR')} | "
            f"TQ {_fmt_num(row.get('TRADE_QUALITY_SCORE'))} | Conf {_fmt_num(row.get('CONFIDENCE'))} | {row.get('WATCHLIST_CATEGORY')}"
        )
        lines.append(f"   Reason: {row.get('REASON')}")
        lines.append(f"   Next: {row.get('NEXT_CONDITION_NEEDED')}")

    lines += _section("HOLD")
    if not split["holds"]:
        lines.append("None.")
    for row in split["holds"]:
        lines.append(
            f"{row.get('SYMBOL')} | {row.get('ACTION')} | PnL {_fmt_num(row.get('PNL_PCT'), '%')} | "
            f"CP {row.get('CURRENT_PRICE')} | Trail {row.get('TRAILING_STOP')}"
        )
        lines.append(f"   Valid: {row.get('WHY_VALID')}")
        lines.append(f"   Invalidates: {row.get('INVALIDATION_TRIGGER')}")

    lines += _section("CAUTION / REDUCE")
    if not split["caution"]:
        lines.append("None.")
    for row in split["caution"]:
        lines.append(
            f"{row.get('SYMBOL')} | {row.get('ACTION')} | PnL {_fmt_num(row.get('PNL_PCT'), '%')} | "
            f"CP {row.get('CURRENT_PRICE')} | Trail {row.get('TRAILING_STOP')}"
        )
        lines.append(f"   Risk: {row.get('REASON')}")
        lines.append(f"   Invalidates: {row.get('INVALIDATION_TRIGGER')}")

    lines += _section("EXIT / SELL")
    if not split["exits"]:
        lines.append("None.")
    for row in split["exits"]:
        reason = row.get("EXIT_REASON") or row.get("REASON")
        lines.append(
            f"{row.get('SYMBOL')} | {row.get('ACTION')} | {row.get('URGENCY')} | "
            f"PnL {_fmt_num(row.get('PNL_PCT'), '%')} | Exit ref {row.get('EXIT_PRICE') or row.get('CURRENT_PRICE')}"
        )
        lines.append(f"   Trigger: {reason}")
        if row.get("EVENT_TYPE") or row.get("EVENT_SUMMARY"):
            lines.append(
                f"   Evidence: {row.get('EVENT_TYPE') or 'event'} | Severity {row.get('EVENT_SEVERITY') or 'NA'} | "
                f"Source {row.get('EVENT_SOURCE_TYPE') or 'news'}"
            )
            if row.get("EVENT_SUMMARY"):
                lines.append(f"   Summary: {row.get('EVENT_SUMMARY')}")
        lines.append("   Manual action: execute manually; remove from MANUAL_PORTFOLIO_JSON after selling.")

    lines += _section("REJECTED HIGH-RANK")
    if not rejected:
        lines.append("No rejected candidate file available.")
    for row in _top(rejected, REPORT_MAX_REJECTED):
        sector = row.get("SECTOR") or ""
        label = f"{row.get('REJECTION_CATEGORY')}"
        if sector == UNMAPPED_SECTOR_LABEL:
            label += "+SECTOR_UNMAPPED"
        lines.append(
            f"#{row.get('FINAL_RANK')} {row.get('SYMBOL')} | TQ {_fmt_num(row.get('FINAL_SCORE'))} | "
            f"Conf {_fmt_num(row.get('CONFIDENCE'))} | {label} | Watch {row.get('WATCHLIST_ELIGIBLE')}"
        )
        lines.append(f"   Reason: {row.get('ONE_LINE_REASON')}")

    lines += _section("PORTFOLIO RISK")
    sector_metrics = [(r.get("METRIC", ""), r.get("VALUE", "")) for r in exposure_rows if str(r.get("METRIC", "")).startswith("sector_exposure_")]
    if sector_metrics:
        vals = []
        for key, value in sector_metrics[:6]:
            sector = key.replace("sector_exposure_", "")
            if sector != UNMAPPED_SECTOR_LABEL:
                vals.append(f"{sector} {_fmt_num(value, '%')}")
        lines.append("Sector exposure: " + (", ".join(vals) if vals else "none mapped"))
    else:
        lines.append("Sector exposure: none mapped")
    corr_warn = [r for r in corr if str(r.get("CORRELATION_STATUS", "")).upper() in ("BLOCK", "CAUTION")]
    if corr_warn:
        lines.append("Correlation: " + "; ".join(f"{r.get('SYMBOL')} {r.get('REASON')}" for r in corr_warn[:3]))
    else:
        lines.append("Correlation: none / unavailable")
    severe_events = [r for r in split["exits"] if str(r.get("ACTION", "")).upper() == "NEWS_RISK_EXIT"]
    lines.append("Event risk: " + (", ".join(r.get("SYMBOL", "") for r in severe_events[:5]) if severe_events else "none severe"))
    lines.append("")
    lines.append("BUY is a recommendation only. HOLD/EXIT is based only on MANUAL_PORTFOLIO_JSON holdings.")
    lines.append("Reference only. Execute manually and manage risk.")
    return "\n".join(lines).strip() + "\n"


def _chunks(text: str, limit: int = MESSAGE_CHAR_LIMIT) -> List[str]:
    if len(text) <= limit:
        return [text]
    chunks: List[str] = []
    current: List[str] = []
    current_len = 0
    for line in text.splitlines():
        if current_len + len(line) + 1 > limit and current:
            chunks.append("\n".join(current))
            current = [line]
            current_len = len(line) + 1
        else:
            current.append(line)
            current_len += len(line) + 1
    if current:
        chunks.append("\n".join(current))
    return chunks


def send_telegram(text: str) -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    ok = True
    for chunk in _chunks(text):
        try:
            resp = requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                data={"chat_id": TELEGRAM_CHAT_ID, "text": chunk},
                timeout=20,
            )
            ok = ok and resp.status_code == 200
            time.sleep(DELAY_BETWEEN_MSGS)
        except Exception:
            ok = False
    return ok


def main() -> None:
    report = build_report()
    with open(TELEGRAM_REPORT_FILE, "w", encoding="utf-8") as f:
        f.write(report)
    sent = send_telegram(report)
    print("\nTELEGRAM REPORT")
    print("=" * 70)
    print(f"Saved: {TELEGRAM_REPORT_FILE}")
    print(f"Sent : {sent}")


if __name__ == "__main__":
    main()
