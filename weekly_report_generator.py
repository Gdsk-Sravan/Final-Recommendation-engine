import os
import csv

print("\nWEEKLY REPORT")
print("=" * 70)

# Signal History

signal_count = 0

if os.path.exists("signal_history"):

    signal_files = os.listdir(
        "signal_history"
    )

    signal_count = len(
        [
            x for x in signal_files
            if "fusion_scores_v6" in x
        ]
    )

print(
    f"Signal Snapshots : {signal_count}"
)

# Active Trades

active_trades = 0

if os.path.exists(
    "active_trades.csv"
):

    with open(
        "active_trades.csv",
        "r"
    ) as f:

        active_trades = max(
            0,
            len(f.readlines()) - 1
        )

print(
    f"Active Trades    : {active_trades}"
)

# Trade Journal

wins = 0
losses = 0

if os.path.exists(
    "trade_journal.csv"
):

    with open(
        "trade_journal.csv",
        "r"
    ) as f:

        reader = csv.DictReader(f)

        for row in reader:

            try:

                pnl = float(
                    row["PnL"]
                )

                if pnl > 0:
                    wins += 1

                elif pnl < 0:
                    losses += 1

            except:
                pass

total_trades = wins + losses

win_rate = 0

if total_trades > 0:

    win_rate = (
        wins
        / total_trades
    ) * 100

print(
    f"Closed Trades    : {total_trades}"
)

print(
    f"Win Rate         : {win_rate:.2f}%"
)

# Latest Recommendations

print("\nLATEST TOP PICKS")
print("-" * 70)

if os.path.exists(
    "fusion_scores_v6.txt"
):

    with open(
        "fusion_scores_v6.txt",
        "r"
    ) as f:

        for i, line in enumerate(f):

            if i >= 5:
                break

            print(
                line.strip()
            )

print("\n" + "=" * 70)
