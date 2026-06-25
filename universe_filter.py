"""
universe_filter.py - Technical eligibility layer after data quality.

This does not force bullish picks. It keeps stocks with enough history,
liquidity and indicator structure to be scored by the downstream engines.
"""

import csv
import os
from typing import Dict, List

from config import (
    TRADABLE_UNIVERSE_FILE,
    QUALIFIED_FILE,
    QUALIFIED_STOCKS_CSV_FILE,
    REJECTED_UNIVERSE_FILE,
    MIN_INDICATOR_HISTORY_DAYS,
    MIN_AVG_VOLUME,
    MIN_AVG_TRADED_VALUE,
)
from data_provider import get_ohlcv


def _ema(prices: List[float], period: int) -> float:
    if not prices:
        return 0.0
    if len(prices) < period:
        return prices[-1]
    mult = 2 / (period + 1)
    val = sum(prices[:period]) / period
    for p in prices[period:]:
        val = (p - val) * mult + val
    return val


def _rsi(closes: List[float], period: int = 14) -> float:
    if len(closes) < period + 2:
        return 50.0
    gains = []
    losses = []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - 100 / (1 + rs)


def _atr(closes: List[float], highs: List[float], lows: List[float], period: int = 14) -> float:
    n = min(len(closes), len(highs), len(lows))
    if n < 2:
        return 0.0
    trs = []
    for i in range(1, n):
        trs.append(max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1])))
    sample = trs[-period:] if len(trs) >= period else trs
    return sum(sample) / len(sample) if sample else 0.0


def _read_tradable_symbols() -> List[str]:
    symbols: List[str] = []
    if os.path.exists(TRADABLE_UNIVERSE_FILE):
        with open(TRADABLE_UNIVERSE_FILE, "r", newline="") as f:
            reader = csv.DictReader(f)
            for r in reader:
                sym = r.get("SYMBOL") or r.get("symbol")
                status = (r.get("STATUS") or "OK").upper()
                if sym and status in ("OK", "PENDING_CACHE"):
                    symbols.append(sym.strip())
    if not symbols and os.path.exists("stocks.txt"):
        with open("stocks.txt", "r") as f:
            symbols = [x.strip() for x in f if x.strip() and not x.startswith("#")]
    return list(dict.fromkeys(symbols))


def _evaluate(symbol: str) -> Dict[str, object]:
    ohlcv = get_ohlcv(symbol)
    if not ohlcv:
        return {"SYMBOL": symbol, "QUALIFIED": False, "REASON": "missing_ohlcv", "FAILED_STAGE": "TECHNICAL_ELIGIBILITY"}
    closes = ohlcv.get("closes", [])
    highs = ohlcv.get("highs", [])
    lows = ohlcv.get("lows", [])
    volumes = ohlcv.get("volumes", [])
    n = min(len(closes), len(highs), len(lows), len(volumes))
    reasons = []
    if n < MIN_INDICATOR_HISTORY_DAYS:
        reasons.append(f"insufficient_indicator_history_{n}")
    price = closes[-1] if closes else 0.0
    ema20 = _ema(closes, 20)
    ema50 = _ema(closes, 50)
    ema200 = _ema(closes, 200)
    atr = _atr(closes, highs, lows)
    rsi = _rsi(closes)
    avg_volume20 = sum(volumes[-20:]) / min(20, len(volumes)) if volumes else 0.0
    avg_traded_value20 = avg_volume20 * price
    if avg_volume20 < MIN_AVG_VOLUME:
        reasons.append("low_avg_volume")
    if avg_traded_value20 < MIN_AVG_TRADED_VALUE:
        reasons.append("low_avg_traded_value")
    if ema20 <= 0 or ema50 <= 0 or ema200 <= 0 or atr <= 0:
        reasons.append("indicator_not_calculable")
    if price <= 0:
        reasons.append("invalid_price")
    # Eligibility is intentionally broad: scoring handles bullish/bearish quality.
    return {
        "SYMBOL": symbol,
        "QUALIFIED": len(reasons) == 0,
        "REASON": ";".join(reasons) if reasons else "passed_technical_eligibility",
        "FAILED_STAGE": "TECHNICAL_ELIGIBILITY" if reasons else "",
        "PRICE": round(price, 2),
        "EMA20": round(ema20, 2),
        "EMA50": round(ema50, 2),
        "EMA200": round(ema200, 2),
        "ATR": round(atr, 2),
        "RSI": round(rsi, 2),
        "AVG_VOLUME20": round(avg_volume20, 0),
        "AVG_TRADED_VALUE20": round(avg_traded_value20, 0),
        "ABOVE_EMA20": price > ema20 if ema20 else False,
        "ABOVE_EMA50": price > ema50 if ema50 else False,
        "ABOVE_EMA200": price > ema200 if ema200 else False,
    }


def main() -> None:
    symbols = _read_tradable_symbols()
    rows = [_evaluate(sym) for sym in symbols]
    qualified = [r for r in rows if r.get("QUALIFIED")]
    rejected = [r for r in rows if not r.get("QUALIFIED")]

    with open(QUALIFIED_FILE, "w") as f:
        for r in qualified:
            f.write(str(r["SYMBOL"]) + "\n")

    with open(QUALIFIED_STOCKS_CSV_FILE, "w", newline="") as f:
        fieldnames = ["SYMBOL", "PRICE", "EMA20", "EMA50", "EMA200", "ATR", "RSI", "AVG_VOLUME20", "AVG_TRADED_VALUE20", "ABOVE_EMA20", "ABOVE_EMA50", "ABOVE_EMA200", "REASON"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in qualified:
            writer.writerow({k: r.get(k, "") for k in fieldnames})

    # Append technical rejections to rejected_universe.csv while preserving earlier stages.
    existing: List[Dict[str, str]] = []
    if os.path.exists(REJECTED_UNIVERSE_FILE):
        try:
            with open(REJECTED_UNIVERSE_FILE, "r", newline="") as f:
                existing = list(csv.DictReader(f))
        except Exception:
            existing = []
    with open(REJECTED_UNIVERSE_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["symbol", "reason", "failed_stage", "missing_metric", "source"])
        writer.writeheader()
        seen = set()
        for r in existing:
            key = (r.get("symbol"), r.get("failed_stage"), r.get("reason"))
            if key not in seen:
                writer.writerow({"symbol": r.get("symbol", ""), "reason": r.get("reason", ""), "failed_stage": r.get("failed_stage", ""), "missing_metric": r.get("missing_metric", ""), "source": r.get("source", "")})
                seen.add(key)
        for r in rejected:
            writer.writerow({"symbol": r.get("SYMBOL"), "reason": r.get("REASON"), "failed_stage": r.get("FAILED_STAGE"), "missing_metric": "indicator_or_liquidity", "source": "UNIVERSE_FILTER"})

    print("\nUNIVERSE FILTER")
    print("=" * 80)
    print(f"Input symbols : {len(symbols)}")
    print(f"Qualified     : {len(qualified)}")
    print(f"Rejected      : {len(rejected)}")
    print(f"Saved         : {QUALIFIED_FILE}, {QUALIFIED_STOCKS_CSV_FILE}")


if __name__ == "__main__":
    main()
