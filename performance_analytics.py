wins = 0
losses = 0

total_profit = 0

trades = 0

print("\nPERFORMANCE ANALYTICS")
print("=" * 70)

try:

    with open("trade_journal.txt", "r") as f:

        for line in f:

            parts = line.strip().split(",")

            if len(parts) != 3:
                continue

            symbol = parts[0]

            entry = float(parts[1])

            exit_price = float(parts[2])

            pnl = (
                (exit_price - entry)
                / entry
            ) * 100

            trades += 1

            total_profit += pnl

            if pnl > 0:

                wins += 1

            else:

                losses += 1

            print(
                f"{symbol} | "
                f"P&L={pnl:.2f}%"
            )

except:

    print("No Trade Journal Found")

if trades > 0:

    win_rate = (
        wins / trades
    ) * 100

    avg_return = (
        total_profit / trades
    )

    print("\nSUMMARY")
    print("=" * 70)

    print(f"Trades       : {trades}")
    print(f"Wins         : {wins}")
    print(f"Losses       : {losses}")
    print(f"Win Rate     : {win_rate:.2f}%")
    print(f"Avg Return   : {avg_return:.2f}%")
