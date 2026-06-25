"""
elite_backtest_v3.py - Expectancy, risk, and setup-specific backtest engine.

The score is not win-rate driven. It emphasises expectancy, profit factor,
drawdown, and setup-specific behaviour. Backtests are still approximations and
include simple transaction cost/slippage assumptions for realism.
"""

import csv
import os
from typing import Dict, List, Tuple

from config import (
    QUALIFIED_FILE,
    ELITE_SCORES_FILE,
    ELITE_STOCKS_FILE,
    BACKTEST_TARGET_PCT,
    BACKTEST_STOP_PCT,
    BACKTEST_MAX_HOLD,
    BACKTEST_MIN_BARS,
    BACKTEST_WARMUP,
    BACKTEST_MIN_TRADES,
)
from data_provider import get_ohlcv

TARGET_PCT = BACKTEST_TARGET_PCT
STOP_PCT = BACKTEST_STOP_PCT
MAX_HOLD = BACKTEST_MAX_HOLD
MIN_BARS = BACKTEST_MIN_BARS
WARMUP = BACKTEST_WARMUP
MIN_TRADES = BACKTEST_MIN_TRADES
SLIPPAGE_PCT = 0.15
COST_PCT = 0.12

SETUP_TYPES = [
    "BREAKOUT",
    "BASE_BREAKOUT",
    "RANGE_BREAKOUT",
    "PULLBACK_TO_EMA20",
    "PULLBACK_TO_EMA50",
    "MOMENTUM_CONTINUATION",
    "MEAN_REVERSION",
]


def _ema(prices: List[float], period: int, end: int = None) -> float:
    series = prices if end is None else prices[:end + 1]
    if not series:
        return 0.0
    if len(series) < period:
        return series[-1]
    mult = 2 / (period + 1)
    val = sum(series[:period]) / period
    for p in series[period:]:
        val = (p - val) * mult + val
    return val


def _return_pct(closes: List[float], idx: int, lookback: int) -> float:
    if idx - lookback < 0 or closes[idx - lookback] == 0:
        return 0.0
    return ((closes[idx] - closes[idx - lookback]) / closes[idx - lookback]) * 100


def _volume_ratio(volumes: List[float], idx: int) -> float:
    if idx < 20:
        return 1.0
    avg = sum(volumes[idx - 20:idx]) / 20
    return volumes[idx] / avg if avg else 1.0


def _setup_at(closes: List[float], highs: List[float], lows: List[float], volumes: List[float], idx: int) -> str:
    if idx < 60:
        return "NONE"
    price = closes[idx]
    ema20 = _ema(closes, 20, idx)
    ema50 = _ema(closes, 50, idx)
    high20 = max(highs[idx - 20:idx])
    high50 = max(highs[idx - 50:idx])
    vr = _volume_ratio(volumes, idx)
    dist20 = abs((price - ema20) / ema20 * 100) if ema20 else 99
    dist50 = abs((price - ema50) / ema50 * 100) if ema50 else 99
    roc10 = _return_pct(closes, idx, 10)
    if price > high50 and vr >= 1.25:
        return "BASE_BREAKOUT"
    if price > high20 and vr >= 1.05:
        return "RANGE_BREAKOUT"
    if dist20 <= 3 and price >= ema20 and ema20 >= ema50:
        return "PULLBACK_TO_EMA20"
    if dist50 <= 4 and price >= ema50 and ema20 >= ema50:
        return "PULLBACK_TO_EMA50"
    if price > ema20 and ema20 > ema50 and roc10 > 2:
        return "MOMENTUM_CONTINUATION"
    if price < ema20 and roc10 > 0 and price > min(lows[max(0, idx-20):idx]) * 1.03:
        return "MEAN_REVERSION"
    return "NONE"


def _simulate_trades(closes: List[float], highs: List[float], lows: List[float], volumes: List[float], setup_filter: str = None) -> List[Dict]:
    trades = []
    n = min(len(closes), len(highs), len(lows), len(volumes))
    for j in range(max(WARMUP, 60), n - MAX_HOLD):
        setup = _setup_at(closes, highs, lows, volumes, j)
        if setup_filter and setup != setup_filter:
            continue
        if setup == "NONE" and setup_filter is None:
            # Generic historical edge still only tests reasonable long setups.
            continue
        entry = closes[j] * (1 + SLIPPAGE_PCT / 100)
        if entry <= 0:
            continue
        target = entry * (1 + TARGET_PCT / 100)
        stop = entry * (1 - STOP_PCT / 100)
        outcome = None
        holding = MAX_HOLD
        exit_reason = "TIME"
        for k in range(1, MAX_HOLD + 1):
            idx = j + k
            hit_target = highs[idx] >= target
            hit_stop = lows[idx] <= stop
            if hit_stop:
                outcome = -STOP_PCT - COST_PCT - SLIPPAGE_PCT
                holding = k
                exit_reason = "STOP"
                break
            if hit_target:
                outcome = TARGET_PCT - COST_PCT - SLIPPAGE_PCT
                holding = k
                exit_reason = "TARGET"
                break
        if outcome is None:
            exit_price = closes[j + MAX_HOLD] * (1 - SLIPPAGE_PCT / 100)
            outcome = ((exit_price - entry) / entry) * 100 - COST_PCT
        trades.append({"return_pct": outcome, "setup": setup, "holding_days": holding, "exit_reason": exit_reason})
    return trades


def _metrics(trades: List[Dict]) -> Dict:
    returns = [t["return_pct"] for t in trades]
    if not returns:
        return {}
    n = len(returns)
    wins = [r for r in returns if r > 0]
    losses = [r for r in returns if r <= 0]
    win_rate = len(wins) / n * 100
    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = sum(losses) / len(losses) if losses else 0.0
    profit_factor = (sum(wins) / abs(sum(losses))) if losses and sum(losses) != 0 else (99.0 if wins else 0.0)
    expectancy = sum(returns) / n
    rr = avg_win / abs(avg_loss) if avg_loss != 0 else 0.0
    equity = 100.0
    peak = 100.0
    drawdowns = []
    cw = cl = max_cw = max_cl = 0
    for r in returns:
        equity *= (1 + r / 100)
        peak = max(peak, equity)
        drawdowns.append((peak - equity) / peak * 100 if peak else 0.0)
        if r > 0:
            cw += 1
            cl = 0
        else:
            cl += 1
            cw = 0
        max_cw = max(max_cw, cw)
        max_cl = max(max_cl, cl)
    return {
        "trades": n,
        "win_rate": round(win_rate, 2),
        "expectancy": round(expectancy, 4),
        "profit_factor": round(profit_factor, 3),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "risk_reward": round(rr, 2),
        "max_drawdown": round(max(drawdowns), 2) if drawdowns else 0.0,
        "avg_drawdown": round(sum(drawdowns) / len(drawdowns), 2) if drawdowns else 0.0,
        "max_consec_wins": max_cw,
        "max_consec_losses": max_cl,
        "avg_holding_days": round(sum(t["holding_days"] for t in trades) / n, 1),
    }


def _score(m: Dict) -> float:
    if not m:
        return 0.0
    exp_score = max(0, min(100, ((m["expectancy"] + 2.5) / 8.5) * 100))
    pf_score = max(0, min(100, ((m["profit_factor"] - 0.75) / 2.25) * 100))
    dd_score = max(0, min(100, 100 - m["max_drawdown"] * 2.2))
    wr_score = max(0, min(100, m["win_rate"]))
    streak_penalty = min(20, m["max_consec_losses"] * 2)
    return round(exp_score * 0.38 + pf_score * 0.30 + dd_score * 0.20 + wr_score * 0.12 - streak_penalty, 2)


def _best_setup(closes, highs, lows, volumes) -> Tuple[str, Dict]:
    best_setup = "UNKNOWN"
    best_metrics = {}
    best_score = -1.0
    for setup in SETUP_TYPES:
        trades = _simulate_trades(closes, highs, lows, volumes, setup)
        m = _metrics(trades)
        if not m or m["trades"] < max(4, MIN_TRADES // 2):
            continue
        s = _score(m)
        if s > best_score:
            best_score = s
            best_setup = setup
            best_metrics = m
    return best_setup, best_metrics


def _read_symbols() -> List[str]:
    if not os.path.exists(QUALIFIED_FILE):
        return []
    with open(QUALIFIED_FILE, "r") as f:
        return [x.strip() for x in f if x.strip()]


def main() -> None:
    symbols = _read_symbols()
    results = []
    skipped = 0
    print("\nELITE BACKTEST V3")
    print("=" * 90)
    for i, sym in enumerate(symbols, 1):
        print(f"[{i}/{len(symbols)}] {sym}", end=" ... ")
        ohlcv = get_ohlcv(sym)
        if not ohlcv or len(ohlcv.get("closes", [])) < MIN_BARS:
            print("SKIP")
            skipped += 1
            continue
        closes = ohlcv["closes"]
        highs = ohlcv["highs"]
        lows = ohlcv["lows"]
        volumes = ohlcv.get("volumes", [0] * len(closes))
        trades = _simulate_trades(closes, highs, lows, volumes)
        if len(trades) < MIN_TRADES:
            print(f"SKIP ({len(trades)} trades)")
            skipped += 1
            continue
        m = _metrics(trades)
        elite = _score(m)
        best_setup, best = _best_setup(closes, highs, lows, volumes)
        hist_status = "OK" if m["trades"] >= MIN_TRADES else "INSUFFICIENT"
        row = {
            "SYMBOL": sym,
            "ELITE_SCORE": elite,
            "WIN_RATE": m["win_rate"],
            "EXPECTANCY": m["expectancy"],
            "PROFIT_FACTOR": m["profit_factor"],
            "AVG_WIN": m["avg_win"],
            "AVG_LOSS": m["avg_loss"],
            "RISK_REWARD": m["risk_reward"],
            "MAX_DRAWDOWN": m["max_drawdown"],
            "AVG_DRAWDOWN": m["avg_drawdown"],
            "MAX_CONSEC_WINS": m["max_consec_wins"],
            "MAX_CONSEC_LOSSES": m["max_consec_losses"],
            "AVG_HOLDING_DAYS": m["avg_holding_days"],
            "TRADES": m["trades"],
            "BEST_SETUP_TYPE": best_setup,
            "SETUP_WIN_RATE": best.get("win_rate", 0.0),
            "SETUP_EXPECTANCY": best.get("expectancy", 0.0),
            "SETUP_PROFIT_FACTOR": best.get("profit_factor", 0.0),
            "SETUP_AVG_HOLDING_DAYS": best.get("avg_holding_days", 0.0),
            "HISTORICAL_EDGE_STATUS": hist_status,
        }
        results.append(row)
        print(f"Score={elite:.1f} WR={m['win_rate']:.1f}% Exp={m['expectancy']:.2f}% PF={m['profit_factor']:.2f} Best={best_setup}")

    results.sort(key=lambda r: r["ELITE_SCORE"], reverse=True)
    fields = [
        "SYMBOL", "ELITE_SCORE", "WIN_RATE", "EXPECTANCY", "PROFIT_FACTOR",
        "AVG_WIN", "AVG_LOSS", "RISK_REWARD", "MAX_DRAWDOWN", "AVG_DRAWDOWN",
        "MAX_CONSEC_WINS", "MAX_CONSEC_LOSSES", "AVG_HOLDING_DAYS", "TRADES",
        "BEST_SETUP_TYPE", "SETUP_WIN_RATE", "SETUP_EXPECTANCY", "SETUP_PROFIT_FACTOR",
        "SETUP_AVG_HOLDING_DAYS", "HISTORICAL_EDGE_STATUS",
    ]
    with open(ELITE_SCORES_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in results:
            writer.writerow(row)
    with open(ELITE_STOCKS_FILE, "w") as f:
        for row in results:
            f.write(row["SYMBOL"] + "\n")

    # Setup and regime summary files are intentionally simple but auditable.
    with open("setup_performance.csv", "w", newline="") as f:
        setup_fields = ["SYMBOL", "SETUP_TYPE", "TRADES", "WIN_RATE", "EXPECTANCY", "PROFIT_FACTOR", "AVG_HOLDING_DAYS"]
        writer = csv.DictWriter(f, fieldnames=setup_fields)
        writer.writeheader()
        for sym_row in results:
            sym = sym_row["SYMBOL"]
            ohlcv = get_ohlcv(sym)
            if not ohlcv:
                continue
            closes = ohlcv["closes"]; highs = ohlcv["highs"]; lows = ohlcv["lows"]; volumes = ohlcv.get("volumes", [0] * len(closes))
            for setup in SETUP_TYPES:
                mt = _metrics(_simulate_trades(closes, highs, lows, volumes, setup))
                if mt:
                    writer.writerow({"SYMBOL": sym, "SETUP_TYPE": setup, "TRADES": mt["trades"], "WIN_RATE": mt["win_rate"], "EXPECTANCY": mt["expectancy"], "PROFIT_FACTOR": mt["profit_factor"], "AVG_HOLDING_DAYS": mt["avg_holding_days"]})

    with open("regime_performance.csv", "w", newline="") as f:
        reg_fields = ["SYMBOL", "REGIME_BUCKET", "ELITE_SCORE", "EXPECTANCY", "PROFIT_FACTOR", "TRADES", "STATUS"]
        writer = csv.DictWriter(f, fieldnames=reg_fields)
        writer.writeheader()
        for row in results:
            writer.writerow({"SYMBOL": row["SYMBOL"], "REGIME_BUCKET": "UNASSIGNED", "ELITE_SCORE": "", "EXPECTANCY": "", "PROFIT_FACTOR": "", "TRADES": row["TRADES"], "STATUS": "regime_attribution_requires_walk_forward_regime_map"})

    print(f"Processed: {len(results)} | Skipped: {skipped}")
    print(f"Saved    : {ELITE_SCORES_FILE}, {ELITE_STOCKS_FILE}")


if __name__ == "__main__":
    main()
