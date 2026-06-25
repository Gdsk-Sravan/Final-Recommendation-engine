"""
pre_news_selector.py - Build a small news/AI universe after deterministic scoring.

Purpose
-------
The engine scans the full NSE universe with deterministic market data first.
Only after that first-pass score exists do we spend time on slow I/O work:
Google News RSS and AI news review.

This file reads confidence_scores.csv from the first fusion pass and writes:
  - pre_news_candidates.csv
  - news_fetch_universe.txt
  - ai_news_universe.txt

Daily news fetch should use news_fetch_universe.txt, not qualified_stocks.txt.
AI news should use ai_news_universe.txt, not the entire headline file.
"""

from __future__ import annotations

import csv
import os
from typing import Dict, Iterable, List, Sequence

from config import (
    AI_NEWS_SYMBOL_LIMIT,
    AI_NEWS_UNIVERSE_FILE,
    CONFIDENCE_SCORES_FILE,
    NEWS_FETCH_TOP_N,
    NEWS_FETCH_UNIVERSE_FILE,
    PORTFOLIO_FILE,
    PORTFOLIO_STATE_FILE,
    PRE_NEWS_CANDIDATES_FILE,
    QUALIFIED_FILE,
)

CANDIDATE_FIELDS = [
    "RANK",
    "SYMBOL",
    "PRE_NEWS_SCORE",
    "TRADE_QUALITY_SCORE",
    "FINAL_CONFIDENCE",
    "SECTOR",
    "SECTOR_CLASS",
    "SETUP_TYPE",
    "ENTRY_SCORE",
    "RS_SCORE",
    "TECH_SCORE",
    "REWARD_RISK",
    "AVG_TRADED_VALUE20",
    "PRIORITY_GROUP",
    "SELECTION_REASON",
]


def _f(value, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def _norm_symbol(raw: str) -> str:
    s = (raw or "").strip().upper()
    if not s:
        return ""
    if s.startswith("^") or s.endswith(".NS") or s.endswith(".BO"):
        return s
    return f"{s}.NS"


def _dedupe(symbols: Iterable[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for raw in symbols:
        sym = _norm_symbol(str(raw))
        if not sym or sym in seen:
            continue
        seen.add(sym)
        out.append(sym)
    return out


def _read_text_symbols(path: str) -> List[str]:
    if not os.path.exists(path):
        return []
    symbols: List[str] = []
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            symbols.append(line.split(",")[0].strip())
    return _dedupe(symbols)


def _read_active_holdings() -> List[str]:
    symbols: List[str] = []

    if os.path.exists(PORTFOLIO_STATE_FILE):
        try:
            with open(PORTFOLIO_STATE_FILE, "r", newline="", encoding="utf-8", errors="ignore") as f:
                for row in csv.DictReader(f):
                    status = (row.get("status") or row.get("STATUS") or "ACTIVE").strip().upper()
                    symbol = row.get("symbol") or row.get("SYMBOL")
                    if symbol and status in ("ACTIVE", "HOLD", "OPEN", ""):
                        symbols.append(symbol)
        except Exception:
            pass

    symbols.extend(_read_text_symbols(PORTFOLIO_FILE))
    return _dedupe(symbols)


def _pre_news_score(row: Dict[str, str]) -> float:
    """Score using deterministic components only; intentionally ignores NEWS_SCORE."""
    trend = _f(row.get("TREND_QUALITY_SCORE"), _f(row.get("TECH_SCORE"), 50.0))
    momentum = _f(row.get("MOMENTUM_QUALITY_SCORE"), _f(row.get("RS_SCORE"), 50.0))
    volume = _f(row.get("VOLUME_PARTICIPATION_SCORE"), 50.0)
    sector = _f(row.get("SECTOR_STRENGTH_SCORE"), _f(row.get("SECTOR_SCORE"), 50.0))
    rs = _f(row.get("RELATIVE_STRENGTH_SCORE"), _f(row.get("RS_SCORE"), 50.0))
    hist = _f(row.get("HISTORICAL_EDGE_SCORE"), _f(row.get("ELITE_SCORE"), 40.0))
    rr = _f(row.get("RISK_REWARD_SCORE"), min(100.0, _f(row.get("REWARD_RISK"), 0.0) * 35.0))
    liq = _f(row.get("LIQUIDITY_TRADABILITY_SCORE"), 60.0)
    entry = _f(row.get("ENTRY_SCORE"), 50.0)

    score = (
        trend * 0.16
        + momentum * 0.15
        + volume * 0.10
        + sector * 0.15
        + rs * 0.16
        + hist * 0.10
        + rr * 0.08
        + liq * 0.05
        + entry * 0.05
    )

    # Soft penalties for obviously weak setup areas before spending time on news.
    if _f(row.get("REWARD_RISK"), 0.0) < 1.4:
        score -= 8.0
    if str(row.get("SECTOR_CLASS", "")).upper() in ("LAGGING", "WEAKENING"):
        score -= 6.0
    if _f(row.get("AVG_TRADED_VALUE20"), 0.0) <= 0:
        score -= 4.0

    return max(0.0, min(100.0, score))


def _load_confidence_rows() -> List[Dict[str, str]]:
    if not os.path.exists(CONFIDENCE_SCORES_FILE):
        return []

    rows: List[Dict[str, str]] = []
    with open(CONFIDENCE_SCORES_FILE, "r", newline="", encoding="utf-8", errors="ignore") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sym = _norm_symbol(row.get("SYMBOL") or row.get("symbol") or "")
            if not sym:
                continue
            row = dict(row)
            row["SYMBOL"] = sym
            row["PRE_NEWS_SCORE"] = f"{_pre_news_score(row):.2f}"
            rows.append(row)

    rows.sort(
        key=lambda r: (
            _f(r.get("PRE_NEWS_SCORE")),
            _f(r.get("TRADE_QUALITY_SCORE")),
            _f(r.get("FINAL_CONFIDENCE"), _f(r.get("CONFIDENCE"))),
            _f(r.get("AVG_TRADED_VALUE20")),
        ),
        reverse=True,
    )
    return rows


def _fallback_rows_from_qualified(limit: int) -> List[Dict[str, str]]:
    symbols = _read_text_symbols(QUALIFIED_FILE)[:limit]
    rows: List[Dict[str, str]] = []
    for idx, sym in enumerate(symbols, 1):
        rows.append(
            {
                "SYMBOL": sym,
                "PRE_NEWS_SCORE": "50.00",
                "TRADE_QUALITY_SCORE": "50.00",
                "FINAL_CONFIDENCE": "50.00",
                "SECTOR": "Unknown",
                "SECTOR_CLASS": "UNKNOWN",
                "SETUP_TYPE": "UNKNOWN",
                "ENTRY_SCORE": "0",
                "RS_SCORE": "0",
                "TECH_SCORE": "0",
                "REWARD_RISK": "0",
                "AVG_TRADED_VALUE20": "0",
            }
        )
    return rows


def _write_symbol_file(path: str, symbols: Sequence[str]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for sym in _dedupe(symbols):
            f.write(sym + "\n")


def main() -> None:
    rows = _load_confidence_rows()
    if not rows:
        print(f"[WARN] {CONFIDENCE_SCORES_FILE} missing or empty; falling back to {QUALIFIED_FILE}")
        rows = _fallback_rows_from_qualified(max(NEWS_FETCH_TOP_N, AI_NEWS_SYMBOL_LIMIT, 50))

    active = _read_active_holdings()
    active_set = set(active)

    selected_symbols: List[str] = []
    ai_symbols: List[str] = []
    output_rows: List[Dict[str, str]] = []

    # Active holdings must always get news coverage for exit/risk monitoring.
    for sym in active:
        selected_symbols.append(sym)
        ai_symbols.append(sym)
        output_rows.append(
            {
                "RANK": "0",
                "SYMBOL": sym,
                "PRE_NEWS_SCORE": "100.00",
                "TRADE_QUALITY_SCORE": "",
                "FINAL_CONFIDENCE": "",
                "SECTOR": "",
                "SECTOR_CLASS": "",
                "SETUP_TYPE": "ACTIVE_POSITION",
                "ENTRY_SCORE": "",
                "RS_SCORE": "",
                "TECH_SCORE": "",
                "REWARD_RISK": "",
                "AVG_TRADED_VALUE20": "",
                "PRIORITY_GROUP": "ACTIVE_HOLDING",
                "SELECTION_REASON": "Active holding - news required for exit risk monitoring",
            }
        )

    rank = 1
    for row in rows:
        sym = row.get("SYMBOL", "")
        if not sym or sym in active_set:
            continue

        if len(_dedupe(selected_symbols)) < NEWS_FETCH_TOP_N:
            selected_symbols.append(sym)
            output_rows.append(
                {
                    "RANK": str(rank),
                    "SYMBOL": sym,
                    "PRE_NEWS_SCORE": f"{_f(row.get('PRE_NEWS_SCORE')):.2f}",
                    "TRADE_QUALITY_SCORE": f"{_f(row.get('TRADE_QUALITY_SCORE')):.2f}",
                    "FINAL_CONFIDENCE": f"{_f(row.get('FINAL_CONFIDENCE'), _f(row.get('CONFIDENCE'))):.2f}",
                    "SECTOR": row.get("SECTOR", ""),
                    "SECTOR_CLASS": row.get("SECTOR_CLASS", ""),
                    "SETUP_TYPE": row.get("SETUP_TYPE", ""),
                    "ENTRY_SCORE": f"{_f(row.get('ENTRY_SCORE')):.2f}",
                    "RS_SCORE": f"{_f(row.get('RS_SCORE')):.2f}",
                    "TECH_SCORE": f"{_f(row.get('TECH_SCORE')):.2f}",
                    "REWARD_RISK": f"{_f(row.get('REWARD_RISK')):.2f}",
                    "AVG_TRADED_VALUE20": f"{_f(row.get('AVG_TRADED_VALUE20')):.2f}",
                    "PRIORITY_GROUP": "TOP_PRE_NEWS_CANDIDATE",
                    "SELECTION_REASON": "Top deterministic candidate before news and AI cost",
                }
            )
            rank += 1

        if len(_dedupe(ai_symbols)) < AI_NEWS_SYMBOL_LIMIT:
            ai_symbols.append(sym)

        if len(_dedupe(selected_symbols)) >= NEWS_FETCH_TOP_N and len(_dedupe(ai_symbols)) >= AI_NEWS_SYMBOL_LIMIT:
            break

    selected_symbols = _dedupe(selected_symbols)[: max(NEWS_FETCH_TOP_N, len(active))]
    ai_symbols = _dedupe(ai_symbols)[: max(AI_NEWS_SYMBOL_LIMIT, len(active))]

    with open(PRE_NEWS_CANDIDATES_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CANDIDATE_FIELDS)
        writer.writeheader()
        for row in output_rows:
            writer.writerow({k: row.get(k, "") for k in CANDIDATE_FIELDS})

    _write_symbol_file(NEWS_FETCH_UNIVERSE_FILE, selected_symbols)
    _write_symbol_file(AI_NEWS_UNIVERSE_FILE, ai_symbols)

    print("\nPRE-NEWS SELECTOR")
    print("=" * 80)
    print(f"Input score file     : {CONFIDENCE_SCORES_FILE}")
    print(f"Active holdings      : {len(active)}")
    print(f"News fetch symbols   : {len(selected_symbols)} -> {NEWS_FETCH_UNIVERSE_FILE}")
    print(f"AI news symbols      : {len(ai_symbols)} -> {AI_NEWS_UNIVERSE_FILE}")
    print(f"Candidate report     : {PRE_NEWS_CANDIDATES_FILE}")


if __name__ == "__main__":
    main()
