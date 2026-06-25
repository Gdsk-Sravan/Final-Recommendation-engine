import os

HISTORY_DIR = "signal_history"

counts = {}

for file in os.listdir(HISTORY_DIR):

    if "fusion_scores_v6" not in file:
        continue

    with open(
        os.path.join(
            HISTORY_DIR,
            file
        ),
        "r"
    ) as f:

        for line in f:

            try:

                symbol, score = (
                    line.strip().split(",")
                )

                counts[symbol] = (
                    counts.get(
                        symbol,
                        0
                    ) + 1
                )

            except:
                pass

ranked = sorted(
    counts.items(),
    key=lambda x: x[1],
    reverse=True
)

print("\nRECOMMENDATION LEADERBOARD")
print("=" * 70)

for symbol, count in ranked[:20]:

    print(
        f"{symbol} | "
        f"Appearances={count}"
    )

print("=" * 70)
