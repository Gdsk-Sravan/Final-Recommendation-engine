"""
market_regime.py - Regime-specific market posture engine.

Classifies the broad market into STRONG_BULL, BULL, SIDEWAYS, WEAK_SIDEWAYS,
BEAR, STRONG_BEAR, HIGH_VOLATILITY, or TRANSITION. The output controls how
strict downstream BUY gates should be; it does not select stocks directly.
"""

import json
import os
from typing import Dict, List, Tuple

from config import (
    NIFTY_SYMBOL,
    INDIA_VIX_SYMBOL,
    QUALIFIED_FILE,
    MARKET_REGIME_FILE,
    REGIME_SETTINGS,
    REGIME_SETTINGS_FILE,
    SECTOR_MAP,
    HIGH_VOLATILITY_ATR_PCT,
    HIGH_VOLATILITY_VIX_LEVEL,
    PANIC_GAP_DOWN_PCT,
    TRANSITION_SCORE_LOW,
    TRANSITION_SCORE_HIGH,
)
from data_provider import get_closes, get_ohlcv


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


def _slope_pct(prices: List[float], period: int, lookback: int = 5) -> float:
    if len(prices) < period + lookback + 2:
        return 0.0
    now = _ema(prices, period)
    prev = _ema(prices[:-lookback], period)
    return ((now - prev) / prev * 100.0) if prev else 0.0


def _return_pct(prices: List[float], lookback: int) -> float:
    if len(prices) < lookback + 1 or prices[-lookback - 1] == 0:
        return 0.0
    return (prices[-1] - prices[-lookback - 1]) / prices[-lookback - 1] * 100.0


def _atr_pct(ohlcv: Dict, period: int = 14) -> float:
    closes = ohlcv.get("closes", [])
    highs = ohlcv.get("highs", [])
    lows = ohlcv.get("lows", [])
    n = min(len(closes), len(highs), len(lows))
    if n < period + 2:
        return 0.0
    trs = []
    for i in range(1, n):
        trs.append(max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1])))
    atr = sum(trs[-period:]) / min(period, len(trs))
    return atr / closes[-1] * 100.0 if closes[-1] else 0.0


def _read_symbols(path: str = QUALIFIED_FILE) -> List[str]:
    if not os.path.exists(path):
        path = "stocks.txt"
    if not os.path.exists(path):
        return []
    with open(path, "r") as f:
        return [x.strip() for x in f if x.strip() and not x.startswith("#")]


def _breadth() -> Tuple[float, float, int]:
    symbols = _read_symbols()
    above20 = above50 = total = 0
    for sym in symbols:
        closes = get_closes(sym)
        if len(closes) < 60:
            continue
        total += 1
        if closes[-1] > _ema(closes, 20):
            above20 += 1
        if closes[-1] > _ema(closes, 50):
            above50 += 1
    if total == 0:
        return 50.0, 50.0, 0
    return round(above20 / total * 100, 2), round(above50 / total * 100, 2), total


def _sector_participation() -> Tuple[float, float, int]:
    pos5 = pos20 = used = 0
    for symbols in SECTOR_MAP.values():
        ret5 = []
        ret20 = []
        for sym in symbols:
            closes = get_closes(sym)
            if len(closes) >= 21:
                ret5.append(_return_pct(closes, 5))
                ret20.append(_return_pct(closes, 20))
        if len(ret20) < 2:
            continue
        used += 1
        if sum(ret5) / len(ret5) > 0:
            pos5 += 1
        if sum(ret20) / len(ret20) > 0:
            pos20 += 1
    if used == 0:
        return 50.0, 50.0, 0
    return round(pos5 / used * 100, 2), round(pos20 / used * 100, 2), used


def _volatility_score(atr_pct: float, gap_down_pct: float, vix: float) -> float:
    if atr_pct <= 0:
        score = 55.0
    elif atr_pct <= 1.0:
        score = 88.0
    elif atr_pct <= 1.5:
        score = 75.0
    elif atr_pct <= 2.2:
        score = 55.0
    elif atr_pct <= 3.0:
        score = 35.0
    else:
        score = 15.0
    if vix >= HIGH_VOLATILITY_VIX_LEVEL:
        score -= min(35.0, (vix - HIGH_VOLATILITY_VIX_LEVEL) * 2.5 + 10)
    if gap_down_pct <= PANIC_GAP_DOWN_PCT:
        score -= 22.0
    elif gap_down_pct <= -0.8:
        score -= 10.0
    return _clamp(score)


def _trend_conflict(current: float, ema20: float, ema50: float, ema200: float) -> bool:
    if not current or not ema20 or not ema50 or not ema200:
        return True
    near_ema = abs(current - ema50) / ema50 * 100 < 1.5
    mixed = (current > ema20 and current < ema50) or (current < ema20 and current > ema50)
    flat_stack = abs(ema20 - ema50) / ema50 * 100 < 0.8
    return near_ema or mixed or flat_stack


def _classify(score: float, closes: List[float], breadth20: float, breadth50: float, atrp: float, gap_down_pct: float, vix: float, conflict: bool) -> str:
    if closes:
        current = closes[-1]
        ema50 = _ema(closes, 50)
        ema200 = _ema(closes, 200)
        if len(closes) >= 220 and current < ema200 and ema50 < ema200 and breadth50 < 30:
            return "STRONG_BEAR"
        if len(closes) >= 220 and current < ema200 and breadth50 < 40:
            return "BEAR"
    if atrp >= HIGH_VOLATILITY_ATR_PCT or gap_down_pct <= PANIC_GAP_DOWN_PCT or vix >= HIGH_VOLATILITY_VIX_LEVEL:
        return "HIGH_VOLATILITY"
    if conflict or TRANSITION_SCORE_LOW <= score <= TRANSITION_SCORE_HIGH:
        return "TRANSITION"
    if score >= 82:
        return "STRONG_BULL"
    if score >= 66:
        return "BULL"
    if score >= 52:
        return "SIDEWAYS"
    if score >= 38:
        return "WEAK_SIDEWAYS"
    if score >= 24:
        return "BEAR"
    return "STRONG_BEAR"


def get_regime() -> Dict[str, object]:
    closes = get_closes(NIFTY_SYMBOL)
    ohlcv = get_ohlcv(NIFTY_SYMBOL)
    current = closes[-1] if closes else 0.0
    ema20 = _ema(closes, 20)
    ema50 = _ema(closes, 50)
    ema200 = _ema(closes, 200)
    ema20_slope = _slope_pct(closes, 20)
    ema50_slope = _slope_pct(closes, 50)
    ret5 = _return_pct(closes, 5)
    ret20 = _return_pct(closes, 20)
    ret50 = _return_pct(closes, 50)
    gap_down_pct = 0.0
    if ohlcv and len(ohlcv.get("opens", [])) >= 2 and len(ohlcv.get("closes", [])) >= 2:
        prev_close = ohlcv["closes"][-2]
        gap_down_pct = (ohlcv["opens"][-1] - prev_close) / prev_close * 100 if prev_close else 0.0
    atrp = _atr_pct(ohlcv) if ohlcv else 0.0
    vix_closes = get_closes(INDIA_VIX_SYMBOL)
    vix = vix_closes[-1] if vix_closes else 0.0

    breadth20, breadth50, breadth_count = _breadth()
    sector_pos5, sector_pos20, sector_count = _sector_participation()
    trend_checks = [
        current > ema20 if ema20 else False,
        current > ema50 if ema50 else False,
        current > ema200 if ema200 else False,
        ema20 > ema50 if ema50 else False,
        ema50 > ema200 if ema200 else False,
        ema20_slope > 0,
        ema50_slope > 0,
    ]
    trend_score = sum(1 for x in trend_checks if x) / len(trend_checks) * 100.0
    momentum_score = _clamp(50 + ret5 * 3.0 + ret20 * 1.5 + ret50 * 0.7)
    breadth_score = _clamp(breadth20 * 0.55 + breadth50 * 0.45)
    sector_participation_score = _clamp(sector_pos5 * 0.40 + sector_pos20 * 0.60)
    vol_score = _volatility_score(atrp, gap_down_pct, vix)
    score = round(trend_score * 0.35 + momentum_score * 0.20 + breadth_score * 0.20 + sector_participation_score * 0.15 + vol_score * 0.10, 2)
    conflict = _trend_conflict(current, ema20, ema50, ema200)
    regime = _classify(score, closes, breadth20, breadth50, atrp, gap_down_pct, vix, conflict)
    settings = REGIME_SETTINGS.get(regime, REGIME_SETTINGS["SIDEWAYS"])
    result = {
        "regime": regime,
        "score": score,
        "regime_score": score,
        "nifty_current": round(current, 2),
        "nifty_ema20": round(ema20, 2),
        "nifty_ema50": round(ema50, 2),
        "nifty_ema200": round(ema200, 2),
        "ema20_slope_pct": round(ema20_slope, 3),
        "ema50_slope_pct": round(ema50_slope, 3),
        "return_5d_pct": round(ret5, 2),
        "return_20d_pct": round(ret20, 2),
        "return_50d_pct": round(ret50, 2),
        "breadth_pct": breadth20,
        "breadth_ema20_pct": breadth20,
        "breadth_ema50_pct": breadth50,
        "breadth_count": breadth_count,
        "atr_pct": round(atrp, 2),
        "india_vix": round(vix, 2),
        "gap_down_pct": round(gap_down_pct, 2),
        "volatility_status": "HIGH" if regime == "HIGH_VOLATILITY" else "NORMAL",
        "sector_positive_5d_pct": sector_pos5,
        "sector_positive_20d_pct": sector_pos20,
        "sector_count": sector_count,
        "trend_score": round(trend_score, 2),
        "momentum_score": round(momentum_score, 2),
        "breadth_score": round(breadth_score, 2),
        "volatility_score": round(vol_score, 2),
        "sector_participation_score": round(sector_participation_score, 2),
        "fresh_buying_allowed": bool(settings["fresh_buying_allowed"]),
        "max_new_buys": int(settings["max_new_buys"]),
        "min_buy_confidence": float(settings["min_buy_confidence"]),
        "min_trade_quality_score": float(settings["min_trade_quality_score"]),
        "min_reward_risk": float(settings["min_reward_risk"]),
        "max_total_portfolio_exposure": float(settings["max_total_exposure"]),
        "max_position_size": float(settings["max_position_size"]),
        "max_sector_exposure": float(settings["max_sector_exposure"]),
        "preferred_setup_types": ";".join(settings.get("preferred_setup_types", [])),
        "restricted_setup_types": ";".join(settings.get("restricted_setup_types", [])),
        "score_multiplier": float(settings["score_multiplier"]),
    }
    _write_regime_file(result)
    _write_settings_file(regime, settings)
    return result


def _write_regime_file(r: Dict[str, object]) -> None:
    with open(MARKET_REGIME_FILE, "w") as f:
        for k, v in r.items():
            if isinstance(v, bool):
                v = "true" if v else "false"
            f.write(f"{k.upper()}={v}\n")


def _write_settings_file(regime: str, settings: Dict[str, object]) -> None:
    payload = {"regime": regime, "settings": settings}
    with open(REGIME_SETTINGS_FILE, "w") as f:
        json.dump(payload, f, indent=2)


def _parse_value(v: str):
    lv = v.strip().lower()
    if lv in ("true", "false"):
        return lv == "true"
    try:
        return float(v) if "." in v else int(v)
    except Exception:
        return v.strip()


def read_regime_file(path: str = MARKET_REGIME_FILE) -> Dict[str, object]:
    defaults = {
        "regime": "TRANSITION",
        "score": 50.0,
        "regime_score": 50.0,
        "fresh_buying_allowed": True,
        "max_new_buys": REGIME_SETTINGS["TRANSITION"]["max_new_buys"],
        "min_buy_confidence": REGIME_SETTINGS["TRANSITION"]["min_buy_confidence"],
        "min_trade_quality_score": REGIME_SETTINGS["TRANSITION"]["min_trade_quality_score"],
        "min_reward_risk": REGIME_SETTINGS["TRANSITION"]["min_reward_risk"],
        "max_total_portfolio_exposure": REGIME_SETTINGS["TRANSITION"]["max_total_exposure"],
        "max_position_size": REGIME_SETTINGS["TRANSITION"]["max_position_size"],
        "max_sector_exposure": REGIME_SETTINGS["TRANSITION"]["max_sector_exposure"],
        "score_multiplier": REGIME_SETTINGS["TRANSITION"]["score_multiplier"],
        "breadth_ema20_pct": 50.0,
        "breadth_ema50_pct": 50.0,
        "volatility_status": "NORMAL",
    }
    if not os.path.exists(path):
        return defaults
    try:
        with open(path, "r") as f:
            for line in f:
                if "=" not in line:
                    continue
                k, v = line.strip().split("=", 1)
                defaults[k.lower()] = _parse_value(v)
    except Exception:
        pass
    return defaults


def regime_score_multiplier(regime: str) -> float:
    return float(REGIME_SETTINGS.get(regime, REGIME_SETTINGS["TRANSITION"]).get("score_multiplier", 0.84))


def regime_sector_adjustment(regime: str, sector: str) -> float:
    defensive = {"FMCG", "Pharma", "Utilities", "IT"}
    cyclical = {"Capital Goods", "Defence", "Realty", "Auto", "Metals", "Finance", "Banking"}
    if regime in ("STRONG_BULL", "BULL") and sector in cyclical:
        return 3.0
    if regime in ("BEAR", "STRONG_BEAR", "HIGH_VOLATILITY") and sector in cyclical:
        return -4.0
    if regime in ("BEAR", "STRONG_BEAR", "HIGH_VOLATILITY") and sector in defensive:
        return 2.0
    return 0.0


def main() -> None:
    r = get_regime()
    print("\nMARKET REGIME")
    print("=" * 80)
    print(f"Regime          : {r['regime']}")
    print(f"Regime score    : {r['regime_score']}/100")
    print(f"Breadth 20/50   : {r['breadth_ema20_pct']}% / {r['breadth_ema50_pct']}%")
    print(f"Volatility      : ATR {r['atr_pct']}% | VIX {r['india_vix']} | {r['volatility_status']}")
    print(f"Max new buys    : {r['max_new_buys']} | Min conf {r['min_buy_confidence']} | Min TQ {r['min_trade_quality_score']}")
    print(f"Saved           : {MARKET_REGIME_FILE}, {REGIME_SETTINGS_FILE}")


if __name__ == "__main__":
    main()
