"""
fusion_scanner_v7.py - Decision-quality fusion scanner.

Builds an interpretable scorecard for every technically eligible stock. It
produces final_confidence and trade_quality_score, but does not force trades.
Recommendation_engine_v6 decides BUY/WATCHLIST/REJECT using regime and
portfolio gates.
"""

import csv
import os
from typing import Dict, List

from config import (
    FUSION_INPUT_FILE,
    QUALIFIED_FILE,
    ELITE_SCORES_FILE,
    NEWS_SCORES_FILE,
    AI_NEWS_SCORES_FILE,
    FUSION_SCORES_FILE,
    CONFIDENCE_SCORES_FILE,
    NIFTY_SYMBOL,
    MIN_AVG_VOLUME,
    MIN_AVG_TRADED_VALUE,
)
from confidence_engine import compute_score_components
from data_provider import get_closes, get_volumes
from entry_quality import compute_entry_score
from market_regime import read_regime_file
from relative_strength import compute_rs
from sector_rotation import compute_sector_scores, write_sector_scores, write_sector_summary, get_sector_score_for_symbol, sector_confidence_adjustment


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def _f(v, default: float = 0.0) -> float:
    try:
        if v is None or v == "":
            return default
        return float(v)
    except Exception:
        return default


def _i(v, default: int = 0) -> int:
    try:
        return int(float(v))
    except Exception:
        return default


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


def _rsi(closes: List[float], period: int = 14) -> float:
    if len(closes) < period + 2:
        return 50.0
    gains = []
    losses = []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    ag = sum(gains[-period:]) / period
    al = sum(losses[-period:]) / period
    if al == 0:
        return 100.0
    rs = ag / al
    return 100 - 100 / (1 + rs)


def _technical_components(closes: List[float], volumes: List[float]) -> Dict[str, float]:
    if len(closes) < 60 or len(volumes) < 21:
        return {
            "trend_quality_score": 0.0, "momentum_quality_score": 0.0, "volume_participation_score": 0.0,
            "avg_volume20": 0.0, "avg_traded_value20": 0.0, "volume_ratio": 0.0,
            "price": 0.0, "ema20": 0.0, "ema50": 0.0, "ema200": 0.0, "extension_ema20_pct": 0.0,
        }
    current = closes[-1]
    ema20 = _ema(closes, 20)
    ema50 = _ema(closes, 50)
    ema200 = _ema(closes, 200)
    trend_checks = [
        current > ema20,
        current > ema50,
        current > ema200 if len(closes) >= 200 else current > ema50,
        ema20 > ema50,
        ema50 > ema200 if len(closes) >= 200 else True,
        _slope_pct(closes, 20) > 0,
        _slope_pct(closes, 50) > 0,
    ]
    trend = sum(1 for x in trend_checks if x) / len(trend_checks) * 100.0
    roc5 = _return_pct(closes, 5)
    roc10 = _return_pct(closes, 10)
    roc20 = _return_pct(closes, 20)
    roc50 = _return_pct(closes, 50)
    rsi = _rsi(closes)
    momentum = _clamp(50 + roc5 * 1.8 + roc10 * 1.1 + roc20 * 0.6 + roc50 * 0.25)
    if 45 <= rsi <= 72:
        momentum += 8
    elif rsi > 80 or rsi < 38:
        momentum -= 12
    momentum = _clamp(momentum)
    avg20 = sum(volumes[-21:-1]) / 20
    vr = volumes[-1] / avg20 if avg20 else 1.0
    volume_score = _clamp(50 + (vr - 1.0) * 45)
    avg_traded_value = avg20 * current
    extension = (current - ema20) / ema20 * 100 if ema20 else 0.0
    return {
        "trend_quality_score": round(trend, 2),
        "momentum_quality_score": round(momentum, 2),
        "volume_participation_score": round(volume_score, 2),
        "avg_volume20": round(avg20, 0),
        "avg_traded_value20": round(avg_traded_value, 0),
        "volume_ratio": round(vr, 2),
        "price": round(current, 2),
        "ema20": round(ema20, 2),
        "ema50": round(ema50, 2),
        "ema200": round(ema200, 2),
        "extension_ema20_pct": round(extension, 2),
        "rsi": round(rsi, 2),
        "roc5": round(roc5, 2),
        "roc10": round(roc10, 2),
        "roc20": round(roc20, 2),
        "roc50": round(roc50, 2),
    }


def _risk_reward_score(rr: float) -> float:
    if rr <= 0:
        return 0.0
    return _clamp(rr / 3.0 * 100)


def _liquidity_score(avg_volume: float, avg_traded_value: float) -> float:
    vol_score = _clamp(avg_volume / max(MIN_AVG_VOLUME, 1.0) * 70.0)
    if avg_volume >= MIN_AVG_VOLUME:
        vol_score = min(100.0, 70.0 + (avg_volume - MIN_AVG_VOLUME) / max(MIN_AVG_VOLUME * 4, 1.0) * 30.0)
    value_score = _clamp(avg_traded_value / max(MIN_AVG_TRADED_VALUE, 1.0) * 70.0)
    if avg_traded_value >= MIN_AVG_TRADED_VALUE:
        value_score = min(100.0, 70.0 + (avg_traded_value - MIN_AVG_TRADED_VALUE) / max(MIN_AVG_TRADED_VALUE * 5, 1.0) * 30.0)
    return round(vol_score * 0.45 + value_score * 0.55, 2)


def _event_news_score(raw_news_score: float, severity: int, black_swan: bool) -> float:
    if black_swan:
        return 0.0
    score = raw_news_score if raw_news_score else 50.0
    if severity >= 90:
        score -= 55
    elif severity >= 75:
        score -= 32
    elif severity >= 60:
        score -= 18
    elif severity >= 45:
        score -= 8
    return _clamp(score)


def _read_symbols(path: str) -> List[str]:
    if os.path.exists(path):
        with open(path, "r") as f:
            return [x.strip() for x in f if x.strip() and not x.startswith("#")]
    return []


def _input_symbols() -> List[str]:
    symbols = _read_symbols(FUSION_INPUT_FILE)
    if not symbols:
        symbols = _read_symbols(QUALIFIED_FILE)
    if not symbols:
        symbols = _read_symbols("stocks.txt")
    return list(dict.fromkeys(symbols))


def _load_elite_scores(path: str) -> Dict[str, Dict[str, object]]:
    data: Dict[str, Dict[str, object]] = {}
    paths = [path]
    if path.endswith(".csv"):
        paths.append(path.replace(".csv", ".txt"))
    else:
        paths.append(path.replace(".txt", ".csv"))
    for p in paths:
        if not os.path.exists(p):
            continue
        try:
            with open(p, "r", newline="") as f:
                first = f.readline()
                f.seek(0)
                if first.upper().startswith("SYMBOL"):
                    reader = csv.DictReader(f)
                    for row in reader:
                        sym = (row.get("SYMBOL") or "").strip()
                        if not sym:
                            continue
                        data[sym] = {
                            "elite_score": _f(row.get("ELITE_SCORE"), 25.0),
                            "win_rate": _f(row.get("WIN_RATE"), 0.0),
                            "expectancy": _f(row.get("EXPECTANCY"), 0.0),
                            "profit_factor": _f(row.get("PROFIT_FACTOR"), 0.0),
                            "max_drawdown": _f(row.get("MAX_DRAWDOWN"), 0.0),
                            "trades": _i(row.get("TRADES"), 0),
                            "best_setup_type": row.get("BEST_SETUP_TYPE", "UNKNOWN") or "UNKNOWN",
                            "setup_expectancy": _f(row.get("SETUP_EXPECTANCY"), 0.0),
                            "setup_profit_factor": _f(row.get("SETUP_PROFIT_FACTOR"), 0.0),
                            "historical_edge_status": row.get("HISTORICAL_EDGE_STATUS", "OK"),
                        }
                else:
                    for line in f:
                        parts = line.strip().split(",")
                        if len(parts) >= 2:
                            data[parts[0].strip()] = {"elite_score": _f(parts[1], 25.0), "win_rate": _f(parts[1], 0), "expectancy": 0, "profit_factor": 1.0, "max_drawdown": 0, "trades": 0, "best_setup_type": "UNKNOWN", "setup_expectancy": 0, "setup_profit_factor": 1.0, "historical_edge_status": "LEGACY"}
        except Exception:
            continue
    return data


def _load_news_scores(ai_path: str, kw_path: str) -> Dict[str, Dict[str, object]]:
    data: Dict[str, Dict[str, object]] = {}
    for p, is_ai in [(kw_path, False), (ai_path, True)]:
        if not os.path.exists(p):
            continue
        try:
            with open(p, "r", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    sym = (row.get("SYMBOL") or "").strip()
                    if not sym:
                        continue
                    old = data.get(sym, {"score": 50.0, "severity": 0, "sentiment": "Neutral", "event": "NoEvent", "black_swan": False, "summary": ""})
                    score = _f(row.get("AI_SCORE" if is_ai else "NEWS_SCORE"), old["score"])
                    sev = _i(row.get("AI_SEVERITY" if is_ai else "MAX_SEVERITY"), int(old["severity"]))
                    event = row.get("AI_EVENT_TYPE" if is_ai else "EVENT_TYPE", old["event"]) or old["event"]
                    sentiment = row.get("AI_SENTIMENT" if is_ai else "SENTIMENT", old["sentiment"]) or old["sentiment"]
                    black = _i(row.get("BLACK_SWAN"), 1 if old.get("black_swan") else 0) == 1 or "black" in str(event).lower()
                    summary = row.get("SUMMARY") or row.get("AI_SUMMARY") or row.get("HEADLINE") or old.get("summary", "")
                    data[sym] = {"score": score, "severity": sev, "sentiment": sentiment, "event": event, "black_swan": black, "summary": summary}
        except Exception:
            continue
    return data


def _portfolio_fit_score() -> float:
    # Candidate-specific concentration/correlation is handled later. Fusion uses
    # a neutral score so ranking does not fake portfolio weakness.
    return 70.0


def main() -> None:
    symbols = _input_symbols()
    if not symbols:
        print(f"[ERROR] No symbols found in {FUSION_INPUT_FILE} or {QUALIFIED_FILE}")
        return
    regime_info = read_regime_file()
    regime = str(regime_info.get("regime", "TRANSITION"))
    elite_data = _load_elite_scores(ELITE_SCORES_FILE)
    news_data = _load_news_scores(AI_NEWS_SCORES_FILE, NEWS_SCORES_FILE)
    sector_scores = compute_sector_scores()
    write_sector_scores(sector_scores)
    write_sector_summary(sector_scores)
    nifty_closes = get_closes(NIFTY_SYMBOL)

    rows: List[Dict[str, object]] = []
    skipped = 0
    for sym in symbols:
        closes = get_closes(sym)
        volumes = get_volumes(sym)
        if len(closes) < 60 or len(volumes) < 21:
            skipped += 1
            continue
        tech = _technical_components(closes, volumes)
        entry = compute_entry_score(sym)
        entry_components = entry.get("components", {})
        elite = elite_data.get(sym, {"elite_score": 25.0, "win_rate": 0.0, "expectancy": 0.0, "profit_factor": 0.0, "trades": 0, "historical_edge_status": "INSUFFICIENT"})
        news = news_data.get(sym, {"score": 50.0, "severity": 0, "sentiment": "Neutral", "event": "NoEvent", "black_swan": False, "summary": ""})
        rs = compute_rs(sym, nifty_closes) if nifty_closes else {"rs_rank_score": 50.0, "rs_momentum": 0.0, "rs_raw": 1.0}
        sector_score = get_sector_score_for_symbol(sym, sector_scores)
        sector_adj, sector, sector_class = sector_confidence_adjustment(sym, sector_scores, regime)
        rr = _f(entry.get("reward_risk"), 0.0)
        rr_score = _risk_reward_score(rr)
        liq_score = _liquidity_score(tech["avg_volume20"], tech["avg_traded_value20"])
        black_swan = bool(news.get("black_swan", False))
        event_score = _event_news_score(_f(news.get("score"), 50.0), _i(news.get("severity"), 0), black_swan)
        portfolio_fit = _portfolio_fit_score()
        score_result = compute_score_components(
            trend_quality_score=_f(entry_components.get("trend_quality_score"), tech["trend_quality_score"]),
            momentum_quality_score=_f(entry_components.get("momentum_quality_score"), tech["momentum_quality_score"]),
            volume_participation_score=_f(entry_components.get("volume_participation_score"), tech["volume_participation_score"]),
            sector_strength_score=sector_score,
            relative_strength_score=_f(rs.get("rs_rank_score"), 50.0),
            historical_edge_score=_f(elite.get("elite_score"), 25.0),
            liquidity_tradability_score=liq_score,
            event_news_risk_score=event_score,
            risk_reward_score=rr_score,
            portfolio_fit_score=portfolio_fit,
            regime=regime,
            correlation_penalty=0.0,
            ai_severity=_i(news.get("severity"), 0),
            black_swan=black_swan,
        )
        final_conf = _clamp(_f(score_result.get("final_confidence"), 0.0) + sector_adj)
        if black_swan:
            final_conf = 0.0
        trade_quality = _clamp(_f(score_result.get("trade_quality_score"), 0.0) + max(-4.0, min(4.0, sector_adj / 2)))
        row = {
            "SYMBOL": sym,
            "FINAL_CONFIDENCE": round(final_conf, 2),
            "CONFIDENCE": round(final_conf, 2),
            "GRADE": score_result.get("confidence_grade", "D"),
            "TRADE_QUALITY_SCORE": round(trade_quality, 2),
            "FUSION": round(trade_quality, 2),
            "BUY_CONFIDENCE": round(final_conf, 2),
            "TREND_QUALITY_SCORE": score_result["trend_quality_score"],
            "MOMENTUM_QUALITY_SCORE": score_result["momentum_quality_score"],
            "VOLUME_PARTICIPATION_SCORE": score_result["volume_participation_score"],
            "REGIME_ALIGNMENT_SCORE": score_result["regime_alignment_score"],
            "SECTOR_STRENGTH_SCORE": score_result["sector_strength_score"],
            "RELATIVE_STRENGTH_SCORE": score_result["relative_strength_score"],
            "HISTORICAL_EDGE_SCORE": score_result["historical_edge_score"],
            "LIQUIDITY_TRADABILITY_SCORE": score_result["liquidity_tradability_score"],
            "EVENT_NEWS_RISK_SCORE": score_result["event_news_risk_score"],
            "CORRELATION_PENALTY": score_result["correlation_penalty"],
            "PORTFOLIO_FIT_SCORE": score_result["portfolio_fit_score"],
            "RISK_REWARD_SCORE": score_result["risk_reward_score"],
            "TECH_SCORE": round((score_result["trend_quality_score"] + score_result["momentum_quality_score"] + score_result["volume_participation_score"]) / 3, 2),
            "ELITE_SCORE": _f(elite.get("elite_score"), 25.0),
            "ENTRY_SCORE": _f(entry.get("entry_score"), 0.0),
            "NEWS_SCORE": _f(news.get("score"), 50.0),
            "RS_SCORE": _f(rs.get("rs_rank_score"), 50.0),
            "RS_RAW": _f(rs.get("rs_raw"), 1.0),
            "RS_MOMENTUM": _f(rs.get("rs_momentum"), 0.0),
            "SECTOR_SCORE": sector_score,
            "SECTOR": sector,
            "SECTOR_CLASS": sector_class,
            "SETUP_TYPE": entry.get("setup_type", "UNKNOWN"),
            "ENTRY_PRICE": entry.get("entry_price", tech["price"]),
            "STOP_LOSS": entry.get("stop_loss", 0.0),
            "TARGET_1": entry.get("target_1", 0.0),
            "TARGET_2": entry.get("target_2", 0.0),
            "TRAILING_STOP": entry.get("trailing_stop", 0.0),
            "TRAILING_STOP_START": entry.get("trailing_stop_start", 0.0),
            "REWARD_RISK": rr,
            "RISK_PER_SHARE": entry.get("risk_per_share", 0.0),
            "RSI": entry.get("rsi", tech.get("rsi", 50.0)),
            "VOLUME_RATIO": tech["volume_ratio"],
            "AVG_VOLUME20": tech["avg_volume20"],
            "AVG_TRADED_VALUE20": tech["avg_traded_value20"],
            "EXTENSION_EMA20_PCT": entry.get("extension_ema20_pct", tech["extension_ema20_pct"]),
            "WIN_RATE": _f(elite.get("win_rate"), 0.0),
            "EXPECTANCY": _f(elite.get("expectancy"), 0.0),
            "PROFIT_FACTOR": _f(elite.get("profit_factor"), 0.0),
            "MAX_DRAWDOWN": _f(elite.get("max_drawdown"), 0.0),
            "TRADES": _i(elite.get("trades"), 0),
            "BEST_SETUP_TYPE": elite.get("best_setup_type", "UNKNOWN"),
            "SETUP_EXPECTANCY": _f(elite.get("setup_expectancy"), 0.0),
            "SETUP_PROFIT_FACTOR": _f(elite.get("setup_profit_factor"), 0.0),
            "HISTORICAL_EDGE_STATUS": elite.get("historical_edge_status", "OK"),
            "AI_SEVERITY": _i(news.get("severity"), 0),
            "BLACK_SWAN": 1 if black_swan else 0,
            "NEWS_EVENT": news.get("event", "NoEvent"),
            "NEWS_SENTIMENT": news.get("sentiment", "Neutral"),
            "NEWS_SUMMARY": news.get("summary", ""),
            "RISK_FLAGS": entry.get("risk_flags", "none"),
        }
        rows.append(row)

    rows.sort(key=lambda r: (_f(r["TRADE_QUALITY_SCORE"]), _f(r["FINAL_CONFIDENCE"]), _f(r["LIQUIDITY_TRADABILITY_SCORE"])), reverse=True)
    for idx, row in enumerate(rows, 1):
        row["FINAL_RANK"] = idx

    with open(FUSION_SCORES_FILE, "w") as f:
        for r in rows:
            f.write(f"{r['SYMBOL']},{float(r['TRADE_QUALITY_SCORE']):.2f},{float(r['FINAL_CONFIDENCE']):.2f}\n")

    fieldnames = [
        "FINAL_RANK", "SYMBOL", "FINAL_CONFIDENCE", "CONFIDENCE", "GRADE", "TRADE_QUALITY_SCORE", "FUSION", "BUY_CONFIDENCE",
        "TREND_QUALITY_SCORE", "MOMENTUM_QUALITY_SCORE", "VOLUME_PARTICIPATION_SCORE", "REGIME_ALIGNMENT_SCORE", "SECTOR_STRENGTH_SCORE",
        "RELATIVE_STRENGTH_SCORE", "HISTORICAL_EDGE_SCORE", "LIQUIDITY_TRADABILITY_SCORE", "EVENT_NEWS_RISK_SCORE", "CORRELATION_PENALTY",
        "PORTFOLIO_FIT_SCORE", "RISK_REWARD_SCORE", "TECH_SCORE", "ELITE_SCORE", "ENTRY_SCORE", "NEWS_SCORE", "RS_SCORE", "RS_RAW", "RS_MOMENTUM",
        "SECTOR_SCORE", "SECTOR", "SECTOR_CLASS", "SETUP_TYPE", "ENTRY_PRICE", "STOP_LOSS", "TARGET_1", "TARGET_2", "TRAILING_STOP",
        "TRAILING_STOP_START", "REWARD_RISK", "RISK_PER_SHARE", "RSI", "VOLUME_RATIO", "AVG_VOLUME20", "AVG_TRADED_VALUE20", "EXTENSION_EMA20_PCT",
        "WIN_RATE", "EXPECTANCY", "PROFIT_FACTOR", "MAX_DRAWDOWN", "TRADES", "BEST_SETUP_TYPE", "SETUP_EXPECTANCY", "SETUP_PROFIT_FACTOR",
        "HISTORICAL_EDGE_STATUS", "AI_SEVERITY", "BLACK_SWAN", "NEWS_EVENT", "NEWS_SENTIMENT", "NEWS_SUMMARY", "RISK_FLAGS",
    ]
    with open(CONFIDENCE_SCORES_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k, "") for k in fieldnames})

    print("\nFUSION SCANNER V7")
    print("=" * 100)
    print(f"Universe : {len(symbols)}")
    print(f"Processed: {len(rows)}")
    print(f"Skipped  : {skipped}")
    print(f"Regime   : {regime}")
    print(f"Saved    : {CONFIDENCE_SCORES_FILE}, {FUSION_SCORES_FILE}")
    for r in rows[:15]:
        print(f"#{r['FINAL_RANK']:02d} {r['SYMBOL']:<18} TQ={float(r['TRADE_QUALITY_SCORE']):>6.2f} Conf={float(r['FINAL_CONFIDENCE']):>6.2f} Sector={r['SECTOR']:<16} Setup={r['SETUP_TYPE']:<22} RR={r['REWARD_RISK']}")


if __name__ == "__main__":
    main()
