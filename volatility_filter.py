"""volatility_filter.py - practical volatility eligibility filter."""

import csv
import os
from typing import List

from config import QUALIFIED_FILE, LOW_VOL_FILE, LOW_VOL_MAX_AVG_DAILY_MOVE_PCT
from data_provider import get_closes


def _read_symbols(path: str) -> List[str]:
    if not os.path.exists(path):
        return []
    with open(path, "r") as f:
        return [x.strip() for x in f if x.strip() and not x.startswith("#")]


def _avg_daily_move(closes: List[float], lookback: int = 120) -> float:
    if len(closes) < 2:
        return 99.0
    moves = []
    series = closes[-(lookback + 1):] if len(closes) > lookback else closes
    for i in range(1, len(series)):
        if series[i - 1]:
            moves.append(abs((series[i] - series[i - 1]) / series[i - 1] * 100))
    return sum(moves) / len(moves) if moves else 99.0


def main() -> None:
    symbols = _read_symbols(QUALIFIED_FILE)
    rows = []
    for sym in symbols:
        closes = get_closes(sym)
        if len(closes) < 60:
            rows.append({"SYMBOL": sym, "AVG_DAILY_MOVE_PCT": 99.0, "PASSED": False, "REASON": "insufficient_history"})
            continue
        vol = _avg_daily_move(closes)
        passed = vol <= LOW_VOL_MAX_AVG_DAILY_MOVE_PCT
        rows.append({"SYMBOL": sym, "AVG_DAILY_MOVE_PCT": round(vol, 2), "PASSED": passed, "REASON": "passed" if passed else "too_volatile"})

    passed_rows = [r for r in rows if r["PASSED"]]
    with open(LOW_VOL_FILE, "w") as f:
        for r in passed_rows:
            f.write(r["SYMBOL"] + "\n")
    with open("low_volatility_stocks.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["SYMBOL", "AVG_DAILY_MOVE_PCT", "PASSED", "REASON"])
        writer.writeheader()
        for r in sorted(rows, key=lambda x: x["AVG_DAILY_MOVE_PCT"]):
            writer.writerow(r)

    print("\nVOLATILITY FILTER")
    print("=" * 80)
    print(f"Input  : {len(symbols)}")
    print(f"Passed : {len(passed_rows)}")
    print(f"Saved  : {LOW_VOL_FILE}, low_volatility_stocks.csv")


if __name__ == "__main__":
    main()
