import os
from data_provider import get_closes

print("\nRECOMMENDATION VS ACTUAL")
print("=" * 70)

if not os.path.exists("portfolio.txt"):

    print("portfolio.txt not found")
    exit()

results = []

with open("portfolio.txt", "r") as f:

    for line in f:

        try:

            symbol = line.strip().split(",")[0]

            closes = get_closes(symbol)

            if len(closes) < 6:
                continue

            entry = closes[-6]
            current = closes[-1]

            ret = (
                (current - entry)
                / entry
            ) * 100

            results.append(
                (
                    symbol,
                    ret
                )
            )

        except:
            pass

wins = 0

for symbol, ret in results:

    if ret > 0:
        wins += 1

    print(
        f"{symbol:<20} "
        f"{ret:>7.2f}%"
    )

print("\n" + "=" * 70)

if results:

    avg_return = (
        sum(
            x[1]
            for x in results
        )
        / len(results)
    )

    win_rate = (
        wins
        / len(results)
    ) * 100

    print(
        f"Average Return : "
        f"{avg_return:.2f}%"
    )

    print(
        f"Win Rate       : "
        f"{win_rate:.2f}%"
    )

print("=" * 70)
