import os

from sector_map import SECTORS

HISTORY_DIR = "signal_history"

sector_counts = {}

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

                sector = SECTORS.get(
                    symbol,
                    "Unknown"
                )

                sector_counts[
                    sector
                ] = (
                    sector_counts.get(
                        sector,
                        0
                    ) + 1
                )

            except:
                pass

ranked = sorted(
    sector_counts.items(),
    key=lambda x: x[1],
    reverse=True
)

print("\nRECOMMENDATION HEATMAP")
print("=" * 70)

for sector, count in ranked:

    print(
        f"{sector:<25} "
        f"{count}"
    )

print("=" * 70)
