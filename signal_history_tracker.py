from datetime import datetime
import shutil
import os

HISTORY_DIR = "signal_history"

if not os.path.exists(
    HISTORY_DIR
):
    os.mkdir(HISTORY_DIR)

today = datetime.now().strftime(
    "%Y-%m-%d"
)

files_to_save = [

    "fusion_scores_v6.txt",

    "elite_scores_v3.txt",

    "elite_stocks_v3.txt"

]

print("\nSIGNAL HISTORY TRACKER")
print("=" * 70)

for filename in files_to_save:

    if not os.path.exists(
        filename
    ):

        print(
            f"Missing: {filename}"
        )

        continue

    destination = (
        f"{HISTORY_DIR}/"
        f"{today}_{filename}"
    )

    shutil.copy(
        filename,
        destination
    )

    print(
        f"Saved: {destination}"
    )

print("=" * 70)
