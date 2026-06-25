"""
sector_rotation.py - Data-first sector leadership and rotation engine.

The engine scores each configured sector using performance, relative strength,
breadth, highs/breakdowns, and volume participation. It is designed to detect
sector leadership even when the broader NIFTY regime is weak.
"""

import csv
import os
from typing import Dict, List, Optional, Tuple

from config import (
    SECTOR_MAP,
    SECTOR_BOOST_PTS,
    SECTOR_PENALTY_PTS,
    NIFTY_SYMBOL,
    SECTOR_SCORES_FILE,
    SECTOR_ROTATION_SUMMARY_FILE,
)
from data_provider import get_closes, get_volumes

OUTPUT_FILE = SECTOR_SCORES_FILE


def _clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


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


def _return_pct(closes: List[float], lookback: int) -> Optional[float]:
    if len(closes) < lookback + 1 or closes[-lookback - 1] == 0:
        return None
    return ((closes[-1] - closes[-lookback - 1]) / closes[-lookback - 1]) * 100


def _avg(values: List[float], default: float = 0.0) -> float:
    return sum(values) / len(values) if values else default


def _sector_metric(symbols: List[str], lookback: int) -> Tuple[float, int]:
    vals = []
    for sym in symbols:
        ret = _return_pct(get_closes(sym), lookback)
        if ret is not None:
            vals.append(ret)
    return _avg(vals), len(vals)


def _breadth(symbols: List[str], period: int) -> Tuple[float, int]:
    total = above = 0
    for sym in symbols:
        closes = get_closes(sym)
        if len(closes) < period + 5:
            continue
        total += 1
        if closes[-1] > _ema(closes, period):
            above += 1
    if total == 0:
        return 50.0, 0
    return above / total * 100, total


def _volume_participation(symbols: List[str]) -> Tuple[float, int]:
    ratios = []
    for sym in symbols:
        volumes = get_volumes(sym)
        if len(volumes) < 21:
            continue
        avg20 = _avg([v for v in volumes[-21:-1] if v is not None], 0.0)
        if avg20 > 0:
            ratios.append(volumes[-1] / avg20)
    if not ratios:
        return 50.0, 0
    avg_ratio = _avg(ratios)
    # 1.0x volume -> 50, 1.5x -> 75, 2.0x -> 100, <0.6x -> weak.
    return _clamp(50 + (avg_ratio - 1.0) * 50), len(ratios)


def _high_breakdown_stats(symbols: List[str]) -> Tuple[float, float, int]:
    total = highs = breakdowns = 0
    for sym in symbols:
        closes = get_closes(sym)
        if len(closes) < 55:
            continue
        total += 1
        if closes[-1] >= max(closes[-20:]) * 0.995:
            highs += 1
        if closes[-1] < _ema(closes, 20) and closes[-2] >= _ema(closes[:-1], 20):
            breakdowns += 1
    if total == 0:
        return 0.0, 0.0, 0
    return highs / total * 100, breakdowns / total * 100, total


def _classify(score: float, rs_accel: float, breadth20: float) -> str:
    if score >= 72 and breadth20 >= 58:
        return "LEADING"
    if score >= 58 and rs_accel > 0:
        return "IMPROVING"
    if score <= 35 or breadth20 < 30:
        return "LAGGING"
    if score <= 47 or rs_accel < -2:
        return "WEAKENING"
    return "NEUTRAL"


def compute_sector_scores() -> Dict[str, Dict]:
    nifty = get_closes(NIFTY_SYMBOL)
    nifty_ret5 = _return_pct(nifty, 5) or 0.0
    nifty_ret20 = _return_pct(nifty, 20) or 0.0
    results: Dict[str, Dict] = {}

    for sector, symbols in SECTOR_MAP.items():
        ret1, used1 = _sector_metric(symbols, 1)
        ret5, used5 = _sector_metric(symbols, 5)
        ret10, used10 = _sector_metric(symbols, 10)
        ret20, used20 = _sector_metric(symbols, 20)
        ret50, used50 = _sector_metric(symbols, 50)
        breadth20, b20_count = _breadth(symbols, 20)
        breadth50, b50_count = _breadth(symbols, 50)
        vol_score, vol_count = _volume_participation(symbols)
        pct_highs, pct_breakdowns, hb_count = _high_breakdown_stats(symbols)

        rs_vs_nifty = ret20 - nifty_ret20
        rs_short_vs_nifty = ret5 - nifty_ret5
        rs_accel = rs_short_vs_nifty - rs_vs_nifty

        perf_score = _clamp(50 + ret5 * 4 + ret20 * 2 + ret50 * 0.8)
        rs_score = _clamp(50 + rs_vs_nifty * 4 + rs_accel * 3)
        breadth_score = _clamp(breadth20 * 0.60 + breadth50 * 0.40)
        high_score = _clamp(50 + pct_highs * 0.6 - pct_breakdowns * 0.8)
        sector_score = round(
            perf_score * 0.30
            + rs_score * 0.25
            + breadth_score * 0.25
            + vol_score * 0.10
            + high_score * 0.10,
            2,
        )
        classification = _classify(sector_score, rs_accel, breadth20)
        used = max(used1, used5, used10, used20, used50, b20_count, b50_count, vol_count, hb_count)

        results[sector] = {
            "score": sector_score,
            "classification": classification,
            "stocks_used": used,
            "avg_return_pct": round(ret20, 2),
            "return_1d": round(ret1, 2),
            "return_5d": round(ret5, 2),
            "return_10d": round(ret10, 2),
            "return_20d": round(ret20, 2),
            "return_50d": round(ret50, 2),
            "rs_vs_nifty": round(rs_vs_nifty, 2),
            "rs_acceleration": round(rs_accel, 2),
            "breadth_ema20": round(breadth20, 2),
            "breadth_ema50": round(breadth50, 2),
            "volume_score": round(vol_score, 2),
            "pct_20d_highs": round(pct_highs, 2),
            "pct_breakdowns": round(pct_breakdowns, 2),
            "trend_status": classification,
        }
    return results


def get_stock_sector(symbol: str) -> Optional[str]:
    clean = symbol.strip().upper()
    for sector, stocks in SECTOR_MAP.items():
        if clean in {s.upper() for s in stocks}:
            return sector
    return None


def get_sector_score_for_symbol(symbol: str, sector_scores: Dict[str, Dict]) -> float:
    sector = get_stock_sector(symbol)
    if not sector:
        return 50.0
    return float(sector_scores.get(sector, {}).get("score", 50.0))


def sector_confidence_adjustment(symbol: str, sector_scores: Dict[str, Dict], regime: str = "SIDEWAYS") -> Tuple[float, str, str]:
    sector = get_stock_sector(symbol)
    if not sector:
        return 0.0, "Unknown", "NEUTRAL"
    info = sector_scores.get(sector, {})
    classification = info.get("classification", "NEUTRAL")
    score = float(info.get("score", 50.0))
    if classification == "LEADING":
        adj = SECTOR_BOOST_PTS + 2
    elif classification == "IMPROVING":
        adj = SECTOR_BOOST_PTS * 0.65
    elif classification == "WEAKENING":
        adj = -SECTOR_PENALTY_PTS
    elif classification == "LAGGING":
        adj = -SECTOR_PENALTY_PTS - 4
    else:
        adj = 0.0
    if regime in ("BEAR", "STRONG_BEAR") and classification not in ("LEADING", "IMPROVING"):
        adj -= 2.0
    if score >= 80:
        adj += 1.0
    return round(max(-15.0, min(15.0, adj)), 2), sector, classification


def load_sector_scores(path: str = OUTPUT_FILE) -> Dict[str, Dict]:
    data: Dict[str, Dict] = {}
    if not os.path.exists(path):
        return data
    try:
        with open(path, "r", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                sector = row.get("SECTOR", "").strip()
                if not sector:
                    continue
                data[sector] = {
                    "score": float(row.get("SECTOR_SCORE") or row.get("STRENGTH_SCORE") or 50),
                    "classification": row.get("CLASSIFICATION", "NEUTRAL"),
                    "stocks_used": int(float(row.get("STOCKS_USED") or 0)),
                    "avg_return_pct": float(row.get("RETURN_20D") or row.get("AVG_RETURN_PCT") or 0),
                    "return_1d": float(row.get("RETURN_1D") or 0),
                    "return_5d": float(row.get("RETURN_5D") or 0),
                    "return_10d": float(row.get("RETURN_10D") or 0),
                    "return_20d": float(row.get("RETURN_20D") or 0),
                    "return_50d": float(row.get("RETURN_50D") or 0),
                    "rs_vs_nifty": float(row.get("RS_VS_NIFTY") or 0),
                    "rs_acceleration": float(row.get("RS_ACCELERATION") or 0),
                    "breadth_ema20": float(row.get("BREADTH_EMA20") or 50),
                    "breadth_ema50": float(row.get("BREADTH_EMA50") or 50),
                    "volume_score": float(row.get("VOLUME_SCORE") or 50),
                    "trend_status": row.get("TREND_STATUS", row.get("CLASSIFICATION", "NEUTRAL")),
                }
    except Exception:
        return {}
    return data


def write_sector_scores(scores: Dict[str, Dict], path: str = OUTPUT_FILE) -> None:
    rows = sorted(scores.items(), key=lambda x: x[1]["score"], reverse=True)
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "SECTOR", "SECTOR_SCORE", "CLASSIFICATION", "STOCKS_USED",
            "RETURN_1D", "RETURN_5D", "RETURN_10D", "RETURN_20D", "RETURN_50D",
            "RS_VS_NIFTY", "RS_ACCELERATION", "BREADTH_EMA20", "BREADTH_EMA50",
            "VOLUME_SCORE", "PCT_20D_HIGHS", "PCT_BREAKDOWNS", "TREND_STATUS",
        ])
        for sector, info in rows:
            writer.writerow([
                sector, info["score"], info["classification"], info["stocks_used"],
                info["return_1d"], info["return_5d"], info["return_10d"], info["return_20d"], info["return_50d"],
                info["rs_vs_nifty"], info["rs_acceleration"], info["breadth_ema20"], info["breadth_ema50"],
                info["volume_score"], info["pct_20d_highs"], info["pct_breakdowns"], info["trend_status"],
            ])


def write_sector_summary(scores: Dict[str, Dict], path: str = SECTOR_ROTATION_SUMMARY_FILE) -> None:
    groups = {"LEADING": [], "IMPROVING": [], "NEUTRAL": [], "WEAKENING": [], "LAGGING": []}
    for sector, info in scores.items():
        groups.setdefault(info.get("classification", "NEUTRAL"), []).append((sector, info))
    for key in groups:
        groups[key].sort(key=lambda x: x[1].get("score", 0), reverse=True)
    lines = ["SECTOR ROTATION SUMMARY"]
    for key in ("LEADING", "IMPROVING", "WEAKENING", "LAGGING", "NEUTRAL"):
        items = groups.get(key, [])[:5]
        label = ", ".join(f"{sec}({info.get('score', 0):.1f})" for sec, info in items) or "None"
        lines.append(f"{key}: {label}")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


def main() -> None:
    scores = compute_sector_scores()
    write_sector_scores(scores)
    write_sector_summary(scores)
    print("\nSECTOR ROTATION ENGINE")
    print("=" * 90)
    print(f"{'SECTOR':<20} {'SCORE':>7} {'CLASS':<12} {'5D%':>8} {'20D%':>8} {'RS':>8} {'B20%':>8}")
    print("-" * 90)
    for sector, info in sorted(scores.items(), key=lambda x: x[1]["score"], reverse=True):
        print(f"{sector:<20} {info['score']:>7.1f} {info['classification']:<12} {info['return_5d']:>8.2f} {info['return_20d']:>8.2f} {info['rs_vs_nifty']:>8.2f} {info['breadth_ema20']:>8.1f}")
    print(f"Saved: {OUTPUT_FILE}, {SECTOR_ROTATION_SUMMARY_FILE}")


if __name__ == "__main__":
    main()
