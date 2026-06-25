"""
entry_quality.py - Deterministic entry, stop, target and setup quality engine.

Calculates chart location, setup type, stop, targets, trailing-stop start and
risk/reward. It never issues BUY by itself.
"""

import csv
import os
from typing import Dict, List

from config import (
    ATR_PERIOD,
    INITIAL_STOP_ATR_MULTIPLIER,
    TRAILING_STOP_ATR_MULTIPLIER,
    TARGET1_R_MULTIPLE,
    TARGET2_R_MULTIPLE,
    MIN_REWARD_RISK,
    MAX_EXTENSION_FROM_EMA20_PCT,
    ENTRY_QUALITY_SCORES_FILE,
    FUSION_INPUT_FILE,
)
from data_provider import get_ohlcv


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


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


def _atr(closes: List[float], highs: List[float], lows: List[float], period: int = ATR_PERIOD) -> float:
    n = min(len(closes), len(highs), len(lows))
    if n < 2:
        return 0.0
    trs = []
    for i in range(1, n):
        trs.append(max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1])))
    sample = trs[-period:] if len(trs) >= period else trs
    return sum(sample) / len(sample) if sample else 0.0


def _return_pct(closes: List[float], lookback: int) -> float:
    if len(closes) < lookback + 1 or closes[-lookback - 1] == 0:
        return 0.0
    return (closes[-1] - closes[-lookback - 1]) / closes[-lookback - 1] * 100


def _slope_pct(closes: List[float], period: int, lookback: int = 5) -> float:
    if len(closes) < period + lookback + 2:
        return 0.0
    now = _ema(closes, period)
    prev = _ema(closes[:-lookback], period)
    return (now - prev) / prev * 100 if prev else 0.0


def _volume_ratio(volumes: List[float]) -> float:
    if len(volumes) < 21:
        return 1.0
    avg20 = sum(volumes[-21:-1]) / 20
    return volumes[-1] / avg20 if avg20 else 1.0


def _nearest_support(closes: List[float], lows: List[float]) -> float:
    current = closes[-1]
    candidates = []
    for lookback in (10, 20, 50):
        if len(lows) >= lookback:
            candidates.append(min(lows[-lookback:]))
    candidates.extend([_ema(closes, 20), _ema(closes, 50)])
    valid = [x for x in candidates if x > 0 and x < current]
    return max(valid) if valid else current * 0.94


def _nearest_resistance(closes: List[float], highs: List[float]) -> float:
    current = closes[-1]
    levels = []
    for lookback in (20, 50, 126, 252):
        if len(highs) >= lookback:
            h = max(highs[-lookback:])
            if h > current:
                levels.append(h)
    return min(levels) if levels else current * 1.12


def _setup_type(closes: List[float], highs: List[float], lows: List[float], volumes: List[float]) -> str:
    current = closes[-1]
    ema20 = _ema(closes, 20)
    ema50 = _ema(closes, 50)
    high20_prev = max(highs[-21:-1]) if len(highs) >= 21 else max(highs)
    high50_prev = max(highs[-51:-1]) if len(highs) >= 51 else max(highs)
    low20_prev = min(lows[-21:-1]) if len(lows) >= 21 else min(lows)
    vr = _volume_ratio(volumes)
    dist20 = abs((current - ema20) / ema20 * 100) if ema20 else 99
    dist50 = abs((current - ema50) / ema50 * 100) if ema50 else 99
    roc5 = _return_pct(closes, 5)
    roc10 = _return_pct(closes, 10)
    rsi = _rsi(closes)
    if current > high50_prev and vr >= 1.25:
        return "BASE_BREAKOUT"
    if current > high20_prev and vr >= 1.15:
        return "BREAKOUT"
    if current > high20_prev:
        return "RANGE_BREAKOUT"
    if dist20 <= 3.0 and current >= ema20 and ema20 >= ema50:
        return "PULLBACK_TO_EMA20"
    if dist50 <= 4.0 and current >= ema50 and ema20 >= ema50:
        return "PULLBACK_TO_EMA50"
    if current > ema20 and ema20 > ema50 and roc10 > 2:
        return "MOMENTUM_CONTINUATION"
    if current > low20_prev * 1.03 and current < ema20 and 38 <= rsi <= 55 and roc5 > 0:
        return "MEAN_REVERSION"
    return "REVERSAL_AVOID"


def _trend_score(closes: List[float]) -> float:
    current = closes[-1]
    ema20 = _ema(closes, 20)
    ema50 = _ema(closes, 50)
    ema200 = _ema(closes, 200)
    checks = [
        current > ema20,
        current > ema50,
        current > ema200 if len(closes) >= 200 else current > ema50,
        ema20 > ema50,
        ema50 > ema200 if len(closes) >= 200 else True,
        _slope_pct(closes, 20) > 0,
        _slope_pct(closes, 50) > 0,
    ]
    return sum(1 for x in checks if x) / len(checks) * 100


def _momentum_score(closes: List[float]) -> float:
    rsi = _rsi(closes)
    roc5 = _return_pct(closes, 5)
    roc10 = _return_pct(closes, 10)
    roc20 = _return_pct(closes, 20)
    score = 50 + roc5 * 1.6 + roc10 * 1.0 + roc20 * 0.45
    if 45 <= rsi <= 68:
        score += 12
    elif 68 < rsi <= 76:
        score += 5
    elif rsi > 80:
        score -= 18
    elif rsi < 38:
        score -= 12
    return _clamp(score)


def _location_score(closes: List[float], setup: str, rr: float) -> float:
    current = closes[-1]
    ema20 = _ema(closes, 20)
    extension = (current - ema20) / ema20 * 100 if ema20 else 0.0
    score = 50.0
    if setup in ("BREAKOUT", "BASE_BREAKOUT", "RANGE_BREAKOUT"):
        score += 16
    elif setup in ("PULLBACK_TO_EMA20", "PULLBACK_TO_EMA50", "MEAN_REVERSION"):
        score += 20
    elif setup == "MOMENTUM_CONTINUATION":
        score += 10
    else:
        score -= 28
    if rr >= 3:
        score += 18
    elif rr >= MIN_REWARD_RISK:
        score += 10
    else:
        score -= 25
    if extension > MAX_EXTENSION_FROM_EMA20_PCT:
        score -= 20
    elif extension > MAX_EXTENSION_FROM_EMA20_PCT * 0.7:
        score -= 8
    elif extension < -5:
        score -= 8
    return _clamp(score)


def compute_entry_score(symbol: str) -> Dict[str, object]:
    default = {
        "symbol": symbol, "entry_score": 0.0, "setup_type": "NO_DATA", "entry_price": 0.0,
        "stop_loss": 0.0, "target_1": 0.0, "target_2": 0.0, "trailing_stop": 0.0,
        "trailing_stop_start": 0.0, "reward_risk": 0.0, "risk_per_share": 0.0,
        "rsi": 50.0, "volume_ratio": 0.0, "extension_ema20_pct": 0.0,
        "avg_traded_value20": 0.0, "components": {}, "risk_flags": "insufficient_data", "error": "insufficient data",
    }
    ohlcv = get_ohlcv(symbol)
    if not ohlcv or len(ohlcv.get("closes", [])) < 60:
        return default
    closes = ohlcv["closes"]
    highs = ohlcv.get("highs", closes)
    lows = ohlcv.get("lows", closes)
    volumes = ohlcv.get("volumes", [])
    current = closes[-1]
    ema20 = _ema(closes, 20)
    ema50 = _ema(closes, 50)
    ema200 = _ema(closes, 200)
    atr = _atr(closes, highs, lows)
    support = _nearest_support(closes, lows)
    resistance = _nearest_resistance(closes, highs)
    setup = _setup_type(closes, highs, lows, volumes)

    atr_stop = current - INITIAL_STOP_ATR_MULTIPLIER * atr if atr else current * 0.94
    structural = max(support, ema50 if 0 < ema50 < current else support, atr_stop)
    stop_loss = round(min(current * 0.995, structural), 2)
    risk = max(current - stop_loss, 0.01)
    target_1 = round(max(current + TARGET1_R_MULTIPLE * risk, min(resistance, current + TARGET2_R_MULTIPLE * risk)), 2)
    target_2 = round(max(current + TARGET2_R_MULTIPLE * risk, resistance), 2)
    trailing_stop = round(max(stop_loss, current - TRAILING_STOP_ATR_MULTIPLIER * atr), 2) if atr else stop_loss
    trailing_stop_start = round(current + max(1.5 * risk, target_1 - current), 2)
    rr = round((target_2 - current) / risk, 2) if risk else 0.0

    trend = _trend_score(closes)
    momentum = _momentum_score(closes)
    vr = _volume_ratio(volumes)
    volume_score = _clamp(50 + (vr - 1.0) * 45)
    rr_score = _clamp(rr / 3.0 * 100)
    location = _location_score(closes, setup, rr)
    entry_score = _clamp(trend * 0.27 + momentum * 0.20 + volume_score * 0.15 + location * 0.23 + rr_score * 0.15)
    rsi = _rsi(closes)
    extension = (current - ema20) / ema20 * 100 if ema20 else 0.0
    avg_volume20 = sum(volumes[-20:]) / min(20, len(volumes)) if volumes else 0.0
    avg_traded_value20 = avg_volume20 * current

    risk_flags = []
    if rr < MIN_REWARD_RISK:
        risk_flags.append("poor_reward_risk")
    if extension > MAX_EXTENSION_FROM_EMA20_PCT:
        risk_flags.append("extended_from_ema20")
    if current < ema50:
        risk_flags.append("below_ema50")
    if len(closes) >= 200 and current < ema200:
        risk_flags.append("below_ema200")
    if setup == "REVERSAL_AVOID":
        risk_flags.append("no_clean_setup")
    if vr < 0.85 and setup in ("BREAKOUT", "BASE_BREAKOUT", "RANGE_BREAKOUT"):
        risk_flags.append("weak_breakout_volume")

    return {
        "symbol": symbol,
        "entry_score": round(entry_score, 2),
        "setup_type": setup,
        "entry_price": round(current, 2),
        "stop_loss": stop_loss,
        "target_1": target_1,
        "target_2": target_2,
        "trailing_stop": trailing_stop,
        "trailing_stop_start": trailing_stop_start,
        "reward_risk": rr,
        "risk_per_share": round(risk, 2),
        "rsi": round(rsi, 2),
        "volume_ratio": round(vr, 2),
        "avg_volume20": round(avg_volume20, 0),
        "avg_traded_value20": round(avg_traded_value20, 0),
        "extension_ema20_pct": round(extension, 2),
        "ema20": round(ema20, 2),
        "ema50": round(ema50, 2),
        "ema200": round(ema200, 2),
        "atr": round(atr, 2),
        "nearest_support": round(support, 2),
        "nearest_resistance": round(resistance, 2),
        "components": {
            "trend_quality_score": round(trend, 2),
            "momentum_quality_score": round(momentum, 2),
            "volume_participation_score": round(volume_score, 2),
            "entry_location_score": round(location, 2),
            "risk_reward_score": round(rr_score, 2),
        },
        "risk_flags": ";".join(risk_flags) if risk_flags else "none",
        "error": None,
    }


def write_entry_scores(symbols: List[str], path: str = ENTRY_QUALITY_SCORES_FILE) -> None:
    fieldnames = [
        "SYMBOL", "ENTRY_SCORE", "SETUP_TYPE", "ENTRY_PRICE", "STOP_LOSS", "TARGET_1", "TARGET_2",
        "TRAILING_STOP", "TRAILING_STOP_START", "REWARD_RISK", "RISK_PER_SHARE", "RSI", "VOLUME_RATIO",
        "AVG_TRADED_VALUE20", "EXTENSION_EMA20_PCT", "NEAREST_SUPPORT", "NEAREST_RESISTANCE", "RISK_FLAGS",
        "TREND_QUALITY_SCORE", "MOMENTUM_QUALITY_SCORE", "VOLUME_PARTICIPATION_SCORE", "RISK_REWARD_SCORE",
    ]
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for sym in symbols:
            r = compute_entry_score(sym)
            c = r.get("components", {})
            writer.writerow({
                "SYMBOL": sym, "ENTRY_SCORE": r["entry_score"], "SETUP_TYPE": r["setup_type"], "ENTRY_PRICE": r["entry_price"],
                "STOP_LOSS": r["stop_loss"], "TARGET_1": r["target_1"], "TARGET_2": r["target_2"],
                "TRAILING_STOP": r["trailing_stop"], "TRAILING_STOP_START": r.get("trailing_stop_start", 0),
                "REWARD_RISK": r["reward_risk"], "RISK_PER_SHARE": r["risk_per_share"], "RSI": r["rsi"],
                "VOLUME_RATIO": r["volume_ratio"], "AVG_TRADED_VALUE20": r.get("avg_traded_value20", 0),
                "EXTENSION_EMA20_PCT": r["extension_ema20_pct"], "NEAREST_SUPPORT": r.get("nearest_support", 0),
                "NEAREST_RESISTANCE": r.get("nearest_resistance", 0), "RISK_FLAGS": r["risk_flags"],
                "TREND_QUALITY_SCORE": c.get("trend_quality_score", 0), "MOMENTUM_QUALITY_SCORE": c.get("momentum_quality_score", 0),
                "VOLUME_PARTICIPATION_SCORE": c.get("volume_participation_score", 0), "RISK_REWARD_SCORE": c.get("risk_reward_score", 0),
            })


def main() -> None:
    if not os.path.exists(FUSION_INPUT_FILE):
        print(f"Missing {FUSION_INPUT_FILE}")
        return
    with open(FUSION_INPUT_FILE, "r") as f:
        symbols = [x.strip() for x in f if x.strip() and not x.startswith("#")]
    write_entry_scores(symbols)
    print("\nENTRY QUALITY")
    print("=" * 80)
    print(f"Processed: {len(symbols)}")
    print(f"Saved    : {ENTRY_QUALITY_SCORES_FILE}")


if __name__ == "__main__":
    main()
