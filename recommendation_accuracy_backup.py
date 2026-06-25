import os
from data_provider import get_closes

HISTORY_DIR = "signal_history"

print("\nRECOMMENDATION ACCURACY")
print("=" * 70)

files = sorted(
    [
        x for x in os.listdir(
            HISTORY_DIR
        )
        if "fusion_scores_v6" in x
    ]
)

if len(files) < 2:

    print(
        "Need at least 2 days of history"
    )

    exit()

latest = files[-1]

print(
    f"Analyzing : {latest}"
)

filepath = os.path.join(
    HISTORY_DIR,
    latest
)

results = []

with open(filepath, "r") as f:

    for line in f:

        try:

            symbol, score = (
                line.strip().split(",")
            )

            score = float(score)

            closes = get_closes(
                symbol
            )

            if len(closes) < 10:
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
                    score,
                    ret
                )
            )

        except:
            pass

results.sort(
    key=lambda x: x[1],
    reverse=True
)

top10 = results[:10]

wins = 0

print()

for symbol, score, ret in top10:

    if ret > 0:
        wins += 1

    print(
        f"{symbol} | "
        f"Score={score:.2f} | "
        f"Return={ret:.2f}%"
    )

if top10:

    avg_return = (
        sum(
            x[2]
            for x in top10
        )
        / len(top10)
    )

    win_rate = (
        wins
        / len(top10)
    ) * 100

    print("\n" + "=" * 70)

    print(
        f"Top10 Avg Return : "
        f"{avg_return:.2f}%"
    )

    print(
        f"Top10 Win Rate   : "
        f"{win_rate:.2f}%"
    )

print("=" * 70)
