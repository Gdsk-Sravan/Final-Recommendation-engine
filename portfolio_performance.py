import csv

wins = 0
losses = 0

total_profit = 0

win_amounts = []
loss_amounts = []

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

                total_profit += pnl

                if pnl > 0:

                    wins += 1

                    win_amounts.append(
                        pnl
                    )

                elif pnl < 0:

                    losses += 1

                    loss_amounts.append(
                        abs(pnl)
                    )

            except:
                pass

except FileNotFoundError:

    print(
        "trade_journal.csv not found"
    )

    exit()

total_trades = wins + losses

if total_trades == 0:

    print(
        "\nNo completed trades found"
    )

    exit()

win_rate = (
    wins
    / total_trades
) * 100

avg_win = (
    sum(win_amounts)
    / len(win_amounts)
) if win_amounts else 0

avg_loss = (
    sum(loss_amounts)
    / len(loss_amounts)
) if loss_amounts else 0

profit_factor = (
    sum(win_amounts)
    / sum(loss_amounts)
) if loss_amounts else 0

expectancy = (
    total_profit
    / total_trades
)

print("\nPORTFOLIO PERFORMANCE")
print("=" * 70)

print(
    f"Total Trades : {total_trades}"
)

print(
    f"Wins         : {wins}"
)

print(
    f"Losses       : {losses}"
)

print(
    f"Win Rate     : {win_rate:.2f}%"
)

print(
    f"Average Win  : {avg_win:.2f}"
)

print(
    f"Average Loss : {avg_loss:.2f}"
)

print(
    f"Profit Factor: {profit_factor:.2f}"
)

print(
    f"Expectancy   : {expectancy:.2f}"
)

print(
    f"Total PnL    : {total_profit:.2f}"
)

print("=" * 70)
