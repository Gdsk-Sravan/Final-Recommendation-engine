"""
ai_second_pass.py - Optional AI refinement after deterministic scan.

This file sends a structured snapshot to the configured Grok API and accepts
only bounded, validated changes. AI cannot create buys, invent metrics, change
prices/stops/targets, or violate deterministic hard gates. It can improve
explanations, downgrade risky BUYs to WATCHLIST, mark holdings for caution/exit
when severe event risk is identified, and apply small confidence adjustments.
"""

from __future__ import annotations

import csv
import json
import os
from datetime import date
from typing import Any, Dict, List, Tuple

from ai_service import AIService
from config import (
    AI_CONFIDENCE_ADJUSTMENT_LIMIT,
    AI_INPUT_SNAPSHOT_FILE,
    AI_OUTPUT_SNAPSHOT_FILE,
    AI_TOP_CANDIDATE_LIMIT,
    AI_VALIDATION_REPORT_FILE,
    CONFIDENCE_SCORES_FILE,
    CORRELATION_REPORT_FILE,
    PORTFOLIO_EXPOSURE_SUMMARY_FILE,
    PORTFOLIO_STATE_FILE,
    PORTFOLIO_FILE,
    PORTFOLIO_STATUS_FILE,
    RECOMMENDATIONS_FILE,
    REJECTED_CANDIDATES_FILE,
    WATCHLIST_FILE,
)
from market_regime import read_regime_file

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
STATUS_FIELDS = [
    "SYMBOL", "ACTION", "STATUS", "PNL_PCT", "CURRENT_PRICE", "ENTRY_PRICE", "STOP_LOSS",
    "TRAILING_STOP", "TARGET_1", "TARGET_1_STATUS", "TARGET_2", "TARGET_2_STATUS",
    "SECTOR", "SECTOR_STATUS", "RELATIVE_STRENGTH_STATUS", "EVENT_RISK_STATUS",
    "EVENT_SEVERITY", "EVENT_TYPE", "EVENT_SOURCE_TYPE", "EVENT_SUMMARY",
    "DAYS_HELD", "EXIT_RISK_SCORE", "WHY_VALID", "INVALIDATION_TRIGGER", "REASON",
    "URGENCY", "EXIT_PRICE", "EXIT_REASON",
]

ALLOWED_ACTION_DOWNGRADES = {"WATCHLIST", "BLOCK_BUY", "HOLD_CAUTION", "REDUCE", "NEWS_RISK_EXIT", "SELL"}


def _f(v, default: float = 0.0) -> float:
    try:
        if v is None or v == "":
            return default
        return float(v)
    except Exception:
        return default


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _read_csv(path: str) -> List[Dict[str, str]]:
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", newline="") as f:
            return list(csv.DictReader(f))
    except Exception:
        return []


def _write_csv(path: str, fields: List[str], rows: List[Dict[str, Any]]) -> None:
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def _read_text(path: str) -> str:
    if not os.path.exists(path):
        return ""
    try:
        with open(path, "r") as f:
            return f.read()[:4000]
    except Exception:
        return ""


def _dump_json(path: str, data: Any) -> None:
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _snapshot() -> Dict[str, Any]:
    scored = _read_csv(CONFIDENCE_SCORES_FILE)[:AI_TOP_CANDIDATE_LIMIT]
    return {
        "scan_date": date.today().isoformat(),
        "regime": read_regime_file(),
        "sector_rotation": _read_text("sector_rotation_summary.txt"),
        "portfolio_summary": _read_csv(PORTFOLIO_EXPOSURE_SUMMARY_FILE),
        "active_positions": [r for r in _read_csv(PORTFOLIO_STATE_FILE) if str(r.get("status", "ACTIVE")).upper() == "ACTIVE"],
        "top_candidates": scored,
        "buy_candidates": _read_csv(RECOMMENDATIONS_FILE),
        "watchlist_candidates": _read_csv(WATCHLIST_FILE),
        "rejected_near_misses": _read_csv(REJECTED_CANDIDATES_FILE)[:AI_TOP_CANDIDATE_LIMIT],
        "hold_manage": _read_csv(PORTFOLIO_STATUS_FILE),
        "correlation_report": _read_csv(CORRELATION_REPORT_FILE),
        "instructions": {
            "do_not_invent_market_data": True,
            "do_not_change_prices_stops_targets": True,
            "do_not_create_new_buy_symbols": True,
            "deterministic_hard_gates_win": True,
        },
    }


def _system_prompt() -> str:
    return (
        "You are an optional second-pass reviewer for a deterministic swing-trading engine. "
        "Return JSON only. Do not invent prices, indicators, facts, or symbols. "
        "You may improve explanations, flag event risk, downgrade BUY to WATCHLIST/BLOCK_BUY, "
        "suggest HOLD_CAUTION/REDUCE/SELL/NEWS_RISK_EXIT for current holdings, and apply small confidence adjustments. "
        "You may not promote WATCHLIST/REJECTED names to BUY and may not override stops, targets, position sizing, or portfolio hard gates. "
        "JSON schema: {"
        "\"buy_adjustments\":[{\"symbol\":str,\"action\":\"KEEP_BUY|WATCHLIST|BLOCK_BUY\",\"confidence_adjustment\":number,\"reason\":str}],"
        "\"watchlist_adjustments\":[{\"symbol\":str,\"priority\":\"HIGH|MEDIUM|LOW\",\"reason\":str,\"next_condition_needed\":str}],"
        "\"hold_adjustments\":[{\"symbol\":str,\"action\":\"HOLD|HOLD_CAUTION|REDUCE\",\"reason\":str,\"invalidation_trigger\":str}],"
        "\"exit_suggestions\":[{\"symbol\":str,\"action\":\"SELL|NEWS_RISK_EXIT|REDUCE\",\"reason\":str,\"urgency\":\"HIGH|MEDIUM|LOW\"}],"
        "\"confidence_adjustments\":[{\"symbol\":str,\"adjustment\":number,\"reason\":str}],"
        "\"explanation_updates\":[{\"symbol\":str,\"bucket\":\"BUY|WATCHLIST|REJECTED|HOLD|EXIT\",\"reason\":str}],"
        "\"event_risk_flags\":[{\"symbol\":str,\"severity\":\"NONE|LOW|MODERATE|SEVERE\",\"reason\":str,\"recommended_action\":str}]"
        "}."
    )


def _valid_symbols(payload: Dict[str, Any]) -> set:
    symbols = set()
    for key in ("top_candidates", "buy_candidates", "watchlist_candidates", "rejected_near_misses", "hold_manage", "active_positions"):
        for row in payload.get(key, []) or []:
            sym = row.get("SYMBOL") or row.get("symbol")
            if sym:
                symbols.add(sym)
    return symbols


def _validate(ai: Dict[str, Any], symbols: set) -> Tuple[Dict[str, Any], List[str]]:
    report: List[str] = []
    cleaned: Dict[str, Any] = {}
    for key in ["buy_adjustments", "watchlist_adjustments", "hold_adjustments", "exit_suggestions", "confidence_adjustments", "explanation_updates", "event_risk_flags"]:
        items = ai.get(key, []) if isinstance(ai.get(key, []), list) else []
        out = []
        for item in items:
            if not isinstance(item, dict):
                continue
            sym = item.get("symbol") or item.get("SYMBOL")
            if sym not in symbols:
                report.append(f"ignored unknown symbol {sym} in {key}")
                continue
            item = dict(item)
            item["symbol"] = sym
            if "confidence_adjustment" in item:
                item["confidence_adjustment"] = _clamp(_f(item.get("confidence_adjustment")), -AI_CONFIDENCE_ADJUSTMENT_LIMIT, AI_CONFIDENCE_ADJUSTMENT_LIMIT)
            if "adjustment" in item:
                item["adjustment"] = _clamp(_f(item.get("adjustment")), -AI_CONFIDENCE_ADJUSTMENT_LIMIT, AI_CONFIDENCE_ADJUSTMENT_LIMIT)
            out.append(item)
        cleaned[key] = out
    return cleaned, report


def _apply_explanations(rows: List[Dict[str, str]], sym_key: str, reason_key: str, updates: List[Dict[str, Any]], bucket: str) -> None:
    by_sym = {u.get("symbol"): u for u in updates if str(u.get("bucket", "")).upper() == bucket}
    for row in rows:
        sym = row.get(sym_key)
        if sym in by_sym:
            reason = str(by_sym[sym].get("reason", "")).strip()
            if reason:
                row[reason_key] = reason[:280]


def _downgrade_buys(recs: List[Dict[str, str]], watch: List[Dict[str, str]], rejected: List[Dict[str, str]], buy_adj: List[Dict[str, Any]], event_flags: List[Dict[str, Any]]) -> set:
    downgrade: Dict[str, str] = {}
    for item in buy_adj:
        action = str(item.get("action", "KEEP_BUY")).upper()
        if action in ("WATCHLIST", "BLOCK_BUY"):
            downgrade[item["symbol"]] = str(item.get("reason", "AI risk downgrade"))[:280]
    for item in event_flags:
        sev = str(item.get("severity", "")).upper()
        rec_action = str(item.get("recommended_action", "")).upper()
        if sev == "SEVERE" or rec_action in ("WATCHLIST", "BLOCK_BUY", "SELL", "NEWS_RISK_EXIT"):
            downgrade[item["symbol"]] = str(item.get("reason", "AI severe event risk flag"))[:280]

    downgraded_symbols = set()
    keep: List[Dict[str, str]] = []
    for row in recs:
        sym = row.get("SYMBOL")
        if sym in downgrade:
            downgraded_symbols.add(sym)
            watch.append({
                "FINAL_RANK": row.get("FINAL_RANK", ""), "SYMBOL": sym, "SECTOR": row.get("SECTOR", "Unknown"),
                "SETUP_TYPE": row.get("SETUP_TYPE", "UNKNOWN"), "TRADE_QUALITY_SCORE": row.get("TRADE_QUALITY_SCORE", ""),
                "CONFIDENCE": row.get("CONFIDENCE", ""), "REASON": downgrade[sym],
                "FAILED_GATES": "AI second-pass event/setup caution", "NEXT_CONDITION_NEEDED": "risk clears and setup reconfirms",
                "WATCHLIST_CATEGORY": "AI_DOWNGRADE", "PORTFOLIO_FIT": row.get("PORTFOLIO_FIT", ""),
            })
            rejected.append({
                "FINAL_RANK": row.get("FINAL_RANK", ""), "SYMBOL": sym, "SECTOR": row.get("SECTOR", "Unknown"),
                "FINAL_SCORE": row.get("TRADE_QUALITY_SCORE", ""), "CONFIDENCE": row.get("CONFIDENCE", ""),
                "FAILED_GATES": "AI second-pass event/setup caution", "ONE_LINE_REASON": downgrade[sym],
                "REJECTION_CATEGORY": "NEWS_RISK_FAIL", "WATCHLIST_ELIGIBLE": "true", "NEXT_CONDITION_NEEDED": "risk clears and setup reconfirms",
                "MARKET_REGIME": "", "SECTOR_CLASS": "", "REWARD_RISK": row.get("REWARD_RISK", ""),
                "NEWS_RISK": "AI second-pass severe/moderate flag", "ENTRY_QUALITY": "",
            })
        else:
            keep.append(row)
    recs[:] = keep
    return downgraded_symbols



def _remove_downgraded_virtual_buys(symbols: set) -> None:
    if not symbols:
        return
    state = _read_csv(PORTFOLIO_STATE_FILE)
    if not state:
        return
    today = date.today().isoformat()
    keep = []
    for row in state:
        sym = row.get("symbol")
        # A final AI downgrade happens before the report is sent, so remove only
        # the virtual position just created today. Existing holdings are managed
        # by portfolio_monitor and status rows.
        if sym in symbols and str(row.get("status", "ACTIVE")).upper() == "ACTIVE" and row.get("entry_date") == today:
            continue
        keep.append(row)
    if keep != state:
        fields = list(state[0].keys()) if state else []
        if fields:
            _write_csv(PORTFOLIO_STATE_FILE, fields, keep)
        try:
            with open(PORTFOLIO_FILE, "w") as f:
                f.write("# SYMBOL,BUY_PRICE,CONFIDENCE,SECTOR,POSITION_PCT,ENTRY_DATE\n")
                for row in keep:
                    if str(row.get("status", "ACTIVE")).upper() == "ACTIVE":
                        f.write(f"{row.get('symbol')},{row.get('entry_price')},{row.get('confidence_at_entry')},{row.get('sector')},{row.get('position_pct')},{row.get('entry_date')}\n")
        except Exception:
            pass


def _apply_confidence(rows: List[Dict[str, str]], symbol_key: str, fields: List[str], adjustments: List[Dict[str, Any]]) -> None:
    adj = {x.get("symbol"): _f(x.get("adjustment", x.get("confidence_adjustment"))) for x in adjustments}
    for row in rows:
        sym = row.get(symbol_key)
        if sym in adj:
            for field in fields:
                if field in row and str(row.get(field, "")).strip():
                    val = _clamp(_f(row.get(field)) + adj[sym], 0, 100)
                    row[field] = f"{val:.2f}"


def _apply_hold_exit(status_rows: List[Dict[str, str]], hold_adj: List[Dict[str, Any]], exits: List[Dict[str, Any]], event_flags: List[Dict[str, Any]]) -> None:
    holds = {x.get("symbol"): x for x in hold_adj}
    exit_map = {x.get("symbol"): x for x in exits}
    for x in event_flags:
        if str(x.get("severity", "")).upper() == "SEVERE":
            exit_map[x.get("symbol")] = {"action": x.get("recommended_action") or "NEWS_RISK_EXIT", "reason": x.get("reason", "AI severe event risk"), "urgency": "HIGH"}
    for row in status_rows:
        sym = row.get("SYMBOL")
        if sym in exit_map:
            item = exit_map[sym]
            action = str(item.get("action", "SELL")).upper()
            if action not in ("SELL", "NEWS_RISK_EXIT", "REDUCE"):
                action = "HOLD_CAUTION"
            row["ACTION"] = action
            row["REASON"] = str(item.get("reason", row.get("REASON", "")))[:280]
            row["URGENCY"] = str(item.get("urgency", "HIGH")).upper()
            row["EVENT_RISK_STATUS"] = "SEVERE" if action == "NEWS_RISK_EXIT" else row.get("EVENT_RISK_STATUS", "")
            if action in ("SELL", "NEWS_RISK_EXIT"):
                row["EXIT_REASON"] = row["REASON"]
        elif sym in holds:
            item = holds[sym]
            action = str(item.get("action", "HOLD_CAUTION")).upper()
            if action in ("HOLD", "HOLD_CAUTION", "REDUCE"):
                row["ACTION"] = action
                row["REASON"] = str(item.get("reason", row.get("REASON", "")))[:280]
                if item.get("invalidation_trigger"):
                    row["INVALIDATION_TRIGGER"] = str(item.get("invalidation_trigger"))[:180]
                if action != "HOLD":
                    row["URGENCY"] = "MEDIUM"


def main() -> None:
    payload = _snapshot()
    _dump_json(AI_INPUT_SNAPSHOT_FILE, payload)
    service = AIService()
    ai, meta = service.complete_json(_system_prompt(), payload)
    if ai is None:
        fallback = {"status": "fallback", "meta": meta, "message": "AI second pass unavailable; deterministic report used"}
        _dump_json(AI_OUTPUT_SNAPSHOT_FILE, fallback)
        _dump_json(AI_VALIDATION_REPORT_FILE, fallback)
        print("\nAI SECOND PASS")
        print("=" * 70)
        print(fallback["message"])
        return

    symbols = _valid_symbols(payload)
    cleaned, validation_notes = _validate(ai, symbols)
    cleaned["meta"] = meta
    _dump_json(AI_OUTPUT_SNAPSHOT_FILE, cleaned)

    recs = _read_csv(RECOMMENDATIONS_FILE)
    watch = _read_csv(WATCHLIST_FILE)
    rejected = _read_csv(REJECTED_CANDIDATES_FILE)
    status_rows = _read_csv(PORTFOLIO_STATUS_FILE)

    explanation_updates = cleaned.get("explanation_updates", [])
    _apply_explanations(recs, "SYMBOL", "REASON", explanation_updates, "BUY")
    _apply_explanations(watch, "SYMBOL", "REASON", explanation_updates, "WATCHLIST")
    _apply_explanations(rejected, "SYMBOL", "ONE_LINE_REASON", explanation_updates, "REJECTED")
    _apply_explanations(status_rows, "SYMBOL", "REASON", explanation_updates, "HOLD")
    downgraded_symbols = _downgrade_buys(recs, watch, rejected, cleaned.get("buy_adjustments", []), cleaned.get("event_risk_flags", []))
    _remove_downgraded_virtual_buys(downgraded_symbols)
    combined_adj = cleaned.get("confidence_adjustments", []) + cleaned.get("buy_adjustments", [])
    _apply_confidence(recs, "SYMBOL", ["CONFIDENCE", "TRADE_QUALITY_SCORE"], combined_adj)
    _apply_confidence(watch, "SYMBOL", ["CONFIDENCE", "TRADE_QUALITY_SCORE"], combined_adj)
    _apply_hold_exit(status_rows, cleaned.get("hold_adjustments", []), cleaned.get("exit_suggestions", []), cleaned.get("event_risk_flags", []))

    _write_csv(RECOMMENDATIONS_FILE, REC_FIELDS, recs)
    _write_csv(WATCHLIST_FILE, WATCH_FIELDS, watch)
    _write_csv(REJECTED_CANDIDATES_FILE, REJECT_FIELDS, rejected[:400])
    _write_csv(PORTFOLIO_STATUS_FILE, STATUS_FIELDS, status_rows)

    validation = {
        "status": "ok",
        "notes": validation_notes,
        "applied": {
            "buy_count_after_ai": len([r for r in recs if str(r.get("ACTION", "")).upper() == "BUY"]),
            "downgraded_recommended_buys": sorted(downgraded_symbols),
            "watchlist_count_after_ai": len(watch),
            "portfolio_status_rows": len(status_rows),
        },
        "hard_gate_policy": "AI was not allowed to create buys, change prices/stops/targets, or override deterministic exits.",
    }
    _dump_json(AI_VALIDATION_REPORT_FILE, validation)
    print("\nAI SECOND PASS")
    print("=" * 70)
    print(f"Validated response. Notes: {len(validation_notes)}")
    print(f"Saved: {AI_INPUT_SNAPSHOT_FILE}, {AI_OUTPUT_SNAPSHOT_FILE}, {AI_VALIDATION_REPORT_FILE}")


if __name__ == "__main__":
    main()
