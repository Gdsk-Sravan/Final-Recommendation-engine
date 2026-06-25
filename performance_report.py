import csv
import os

print("\nPERFORMANCE REPORT")
print("=" * 60)

if not os.path.exists("trade_journal.csv"):

    print("No trade_journal.csv found")
    exit()

trades = []

with open("trade_journal.csv", "r") as f:

    reader = csv.DictReader(f)

    for row in reader:

        if row["PnLPercent"]:

            trades.append(
                float(row["PnLPercent"])
            )

if len(trades) == 0:

    print("No completed trades yet")
    print("=" * 60)
    exit()

wins = len(
    [x for x in trades if x > 0]
)

losses = len(
    [x for x in trades if x <= 0]
)

win_rate = (
    wins / len(trades)
) * 100

avg_return = (
    sum(trades)
    / len(trades)
)

gross_profit = sum(
    [x for x in trades if x > 0]
)

gross_loss = abs(
    sum(
        [x for x in trades if x < 0]
    )
)

profit_factor = 0

if gross_loss > 0:

    profit_factor = (
        gross_profit
        / gross_loss
    )

print(f"Trades        : {len(trades)}")
print(f"Wins          : {wins}")
print(f"Losses        : {losses}")
print(f"Win Rate      : {win_rate:.2f}%")
print(f"Avg Return    : {avg_return:.2f}%")
print(f"Profit Factor : {profit_factor:.2f}")

print("=" * 60)
