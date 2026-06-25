import csv

best_trade = None
worst_trade = None

wins = []
losses = []

try:

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

                if best_trade is None or pnl > best_trade:
                    best_trade = pnl

                if worst_trade is None or pnl < worst_trade:
                    worst_trade = pnl

                if pnl > 0:
                    wins.append(pnl)

                elif pnl < 0:
                    losses.append(abs(pnl))

            except:
                pass

except:

    print("No trade data found")
    exit()

print("\nTRADE STATISTICS")
print("=" * 70)

print(f"Best Trade      : {best_trade}")
print(f"Worst Trade     : {worst_trade}")

if wins:
    print(
        f"Average Win     : "
        f"{sum(wins)/len(wins):.2f}"
    )

if losses:
    print(
        f"Average Loss    : "
        f"{sum(losses)/len(losses):.2f}"
    )

if wins and losses:

    print(
        f"Win/Loss Ratio  : "
        f"{(sum(wins)/len(wins))/(sum(losses)/len(losses)):.2f}"
    )

print("=" * 70)
