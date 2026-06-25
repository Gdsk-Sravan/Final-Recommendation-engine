"""
relative_strength.py — Relative Strength Engine

PURPOSE
───────
Measures how strongly a stock is performing relative to the NIFTY 50
index and, where available, its own sector index.

A stock can look great on an absolute chart but if NIFTY is up 20%
and the stock is only up 5%, it is actually a laggard.  Relative
strength catches this and prevents ranking weak stocks above strong ones.

METRICS PRODUCED
────────────────
  rs_raw          : (stock_return / nifty_return) over RS_LOOKBACK_DAYS
                    >1.0 = outperforming, <1.0 = underperforming
  rs_score        : 0–100 linear score derived from rs_raw
  rs_momentum     : short-term RS (RS_SHORT_LOOKBACK) - long-term RS
                    positive = RS is accelerating (improving leader)
                    negative = RS is decelerating (fading leader)
  rs_rank_score   : composite 0–100 combining rs_score + rs_momentum signal

SCORING SCALE
─────────────
  rs_raw  ≥ 1.5   → rs_score = 100   (strong outperformer)
  rs_raw  = 1.0   → rs_score = 50    (in-line with market)
  rs_raw  ≤ 0.5   → rs_score = 0     (significant underperformer)
  Linear interpolation between these anchors.

OUTPUT FILE  relative_strength_scores.txt
──────────────────────────────────────────
  SYMBOL,RS_SCORE,RS_RAW,RS_MOMENTUM,RS_RANK_SCORE
"""

import os
from typing import Dict, List, Optional

from config import (
    NIFTY_SYMBOL,
    RS_LOOKBACK_DAYS,
    RS_SHORT_LOOKBACK,
    RELATIVE_STRENGTH_SCORES_FILE,
)
from data_provider import get_closes

OUTPUT_FILE     = RELATIVE_STRENGTH_SCORES_FILE
QUALIFIED_FILE  = "qualified_stocks.txt"


# ─────────────────────────────────────────────────────────────────────
# MATH HELPERS
# ─────────────────────────────────────────────────────────────────────

def _pct_return(closes: List[float], lookback: int) -> Optional[float]:
    """Return % return over last `lookback` bars, or None if not enough data."""
    if len(closes) < lookback + 1:
        return None
    start = closes[-(lookback + 1)]
    end   = closes[-1]
    if start <= 0:
        return None
    return ((end - start) / start) * 100


def _rs_raw(stock_ret: float, nifty_ret: float) -> float:
    """
    Relative return ratio.
    Both arguments are % returns (can be negative).
    Maps returns to a ratio where 1.0 = in-line with market.
    """
    # Add 100 to convert % to multiplier, take ratio
    stock_mult = 1 + stock_ret / 100
    nifty_mult = 1 + nifty_ret / 100
    if nifty_mult <= 0:
        return 1.0
    return stock_mult / nifty_mult


def _rs_score_from_raw(rs_raw: float) -> float:
    """
    Linear mapping:
      rs_raw 0.5 → score  0
      rs_raw 1.0 → score 50
      rs_raw 1.5 → score 100
    Clamped to [0, 100].
    """
    score = (rs_raw - 0.5) / 1.0 * 100
    return round(max(0.0, min(100.0, score)), 2)


# ─────────────────────────────────────────────────────────────────────
# SINGLE STOCK RS
# ─────────────────────────────────────────────────────────────────────

def compute_rs(symbol: str, nifty_closes: List[float]) -> Dict:
    """
    Compute full relative-strength profile for one symbol.
    Returns a dict; on error returns a neutral default dict.
    """
    default = {
        "symbol":       symbol,
        "rs_score":     50.0,
        "rs_raw":       1.0,
        "rs_momentum":  0.0,
        "rs_rank_score": 50.0,
        "error":        "insufficient data",
    }

    closes = get_closes(symbol)
    required = max(RS_LOOKBACK_DAYS, RS_SHORT_LOOKBACK) + 2
    if len(closes) < required or len(nifty_closes) < required:
        return default

    # Primary RS (long-term)
    stock_ret_long  = _pct_return(closes,       RS_LOOKBACK_DAYS)
    nifty_ret_long  = _pct_return(nifty_closes, RS_LOOKBACK_DAYS)
    if stock_ret_long is None or nifty_ret_long is None:
        return default

    rs_long = _rs_raw(stock_ret_long, nifty_ret_long)
    rs_score_long = _rs_score_from_raw(rs_long)

    # Short-term RS for momentum
    stock_ret_short = _pct_return(closes,       RS_SHORT_LOOKBACK)
    nifty_ret_short = _pct_return(nifty_closes, RS_SHORT_LOOKBACK)
    rs_short = 1.0
    if stock_ret_short is not None and nifty_ret_short is not None:
        rs_short = _rs_raw(stock_ret_short, nifty_ret_short)

    # RS Momentum = direction of change in RS
    # Positive → stock is getting relatively stronger
    rs_momentum = round(rs_short - rs_long, 4)

    # Composite rank score: 80% long RS + 20% momentum direction
    momentum_bonus = min(max(rs_momentum * 20, -10), 10)  # cap ±10 pts
    rs_rank_score  = round(max(0.0, min(100.0, rs_score_long + momentum_bonus)), 2)

    return {
        "symbol":        symbol,
        "rs_score":      rs_score_long,
        "rs_raw":        round(rs_long, 4),
        "rs_momentum":   rs_momentum,
        "rs_rank_score": rs_rank_score,
        "error":         None,
    }


# ─────────────────────────────────────────────────────────────────────
# BATCH RS SCORER
# ─────────────────────────────────────────────────────────────────────

def batch_rs_scores(symbols: List[str]) -> Dict[str, Dict]:
    """
    Compute RS for a list of symbols.
    Returns {symbol: rs_dict}.
    Fetches NIFTY closes once and reuses for all symbols.
    """
    nifty_closes = get_closes(NIFTY_SYMBOL)
    results = {}
    for sym in symbols:
        results[sym] = compute_rs(sym, nifty_closes)
    return results


def load_rs_scores(path: str = OUTPUT_FILE) -> Dict[str, float]:
    """
    Load saved RS rank scores from file.
    Returns {SYMBOL: rs_rank_score}.
    """
    data = {}
    if not os.path.exists(path):
        return data
    try:
        with open(path, "r") as f:
            next(f, None)  # skip header
            for line in f:
                parts = line.strip().split(",")
                if len(parts) >= 5:
                    sym = parts[0].strip()
                    try:
                        data[sym] = float(parts[4])  # RS_RANK_SCORE
                    except ValueError:
                        pass
    except Exception:
        pass
    return data


# ─────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────

def main():
    if not os.path.exists(QUALIFIED_FILE):
        print(f"[ERROR] {QUALIFIED_FILE} not found")
        return

    with open(QUALIFIED_FILE, "r") as f:
        symbols = [x.strip() for x in f if x.strip()]

    print("\nRELATIVE STRENGTH ENGINE")
    print("=" * 70)
    print(f"  Universe : {len(symbols)} stocks  |  NIFTY: {NIFTY_SYMBOL}")
    print(f"  Lookback : {RS_LOOKBACK_DAYS}d primary / {RS_SHORT_LOOKBACK}d momentum")
    print()

    nifty_closes = get_closes(NIFTY_SYMBOL)
    if not nifty_closes:
        print(f"[ERROR] Cannot fetch NIFTY data — is {NIFTY_SYMBOL} cached?")
        return

    results = []
    for sym in symbols:
        r = compute_rs(sym, nifty_closes)
        results.append(r)

    results.sort(key=lambda x: x["rs_rank_score"], reverse=True)

    # Write output
    with open(OUTPUT_FILE, "w") as f:
        f.write("SYMBOL,RS_SCORE,RS_RAW,RS_MOMENTUM,RS_RANK_SCORE\n")
        for r in results:
            f.write(
                f"{r['symbol']},{r['rs_score']},{r['rs_raw']},"
                f"{r['rs_momentum']},{r['rs_rank_score']}\n"
            )

    # Console table
    print(f"  {'#':<4} {'SYMBOL':<25} {'RS_RAW':>8} {'RS_SCORE':>9} "
          f"{'MOMENTUM':>10} {'RANK_SCORE':>11}")
    print(f"  {'-'*68}")
    for i, r in enumerate(results[:20], 1):
        mom_str = f"{r['rs_momentum']:+.4f}"
        print(
            f"  {i:<4} {r['symbol']:<25} {r['rs_raw']:>8.4f} "
            f"{r['rs_score']:>9.1f} {mom_str:>10} {r['rs_rank_score']:>11.1f}"
        )

    leaders    = [r for r in results if r["rs_raw"] >= 1.2]
    laggards   = [r for r in results if r["rs_raw"] <  0.8]
    improving  = [r for r in results if r["rs_momentum"] > 0.05]

    print(f"\n  Outperformers (RS≥1.2) : {len(leaders)}")
    print(f"  Laggards      (RS<0.8) : {len(laggards)}")
    print(f"  Improving momentum    : {len(improving)}")
    print(f"\n  Saved → {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
