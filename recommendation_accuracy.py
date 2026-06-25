import os
from data_provider import get_closes

HISTORY_DIR = "signal_history"

print("\nRECOMMENDATION ACCURACY")
print("=" * 70)

files = sorted(
    [
        x
        for x in os.listdir(HISTORY_DIR)
        if "fusion_scores_v6" in x
    ]
)

if not files:
    print("No history found")
    exit()

total_recommendations = 0
wins = 0

returns_5d = []
returns_20d = []

for history_file in files:

    filepath = os.path.join(
        HISTORY_DIR,
        history_file
    )

    with open(filepath, "r") as f:

        rows = [
            x.strip()
            for x in f
            if x.strip()
        ]

    top10 = rows[:10]

    for row in top10:

        try:

            symbol, score = row.split(",")

            closes = get_closes(symbol)

            if len(closes) < 21:
                continue

            ret5 = (
                (closes[-1] - closes[-6])
                / closes[-6]
            ) * 100

            ret20 = (
                (closes[-1] - closes[-21])
                / closes[-21]
            ) * 100

            returns_5d.append(ret5)
            returns_20d.append(ret20)

            total_recommendations += 1

            if ret20 > 0:
                wins += 1

        except:
            pass

print()

if total_recommendations == 0:

    print("No valid recommendations found")
    exit()

avg_5d = (
    sum(returns_5d)
    / len(returns_5d)
)

avg_20d = (
    sum(returns_20d)
    / len(returns_20d)
)

win_rate = (
    wins
    / total_recommendations
) * 100

print(f"Snapshots Analyzed : {len(files)}")
print(f"Recommendations    : {total_recommendations}")
print(f"Average 5D Return  : {avg_5d:.2f}%")
print(f"Average 20D Return : {avg_20d:.2f}%")
print(f"Win Rate           : {win_rate:.2f}%")

print("=" * 70)
