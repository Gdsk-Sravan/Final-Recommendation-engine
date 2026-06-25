import csv

from data_provider import get_closes

print("\nPORTFOLIO TRACKER")
print("=" * 70)

with open("active_trades.csv", "r") as f:

    reader = csv.DictReader(f)

    trades = list(reader)

for trade in trades:

    try:

        symbol = trade["Symbol"]

        entry = float(
            trade["Entry"]
        )

        stop = float(
            trade["Stop"]
        )

        target = float(
            trade["Target"]
        )

        status = trade["Status"]

        closes = get_closes(symbol)

        if not closes:
            continue

        current = closes[-1]

        pnl = (
            (current - entry)
            / entry
        ) * 100

        stop_distance = (
            (current - stop)
            / current
        ) * 100

        target_distance = (
            (target - current)
            / current
        ) * 100

        live_status = status

        if current <= stop:

            live_status = "STOP LOSS HIT"

        elif current >= target:

            live_status = "TARGET HIT"

        print(f"\n{symbol}")

        print(
            f"Entry      : ₹{entry:.2f}"
        )

        print(
            f"Current    : ₹{current:.2f}"
        )

        print(
            f"P&L        : {pnl:.2f}%"
        )

        print(
            f"Stop Dist  : {stop_distance:.2f}%"
        )

        print(
            f"Target Dist: {target_distance:.2f}%"
        )

        print(
            f"Status     : {live_status}"
        )

        print("-" * 70)

    except Exception as e:

        print(trade, e)
