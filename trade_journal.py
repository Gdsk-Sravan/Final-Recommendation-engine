import csv
import os

FILENAME = "trade_journal.csv"

if not os.path.exists(FILENAME):

    with open(FILENAME, "w", newline="") as f:

        writer = csv.writer(f)

        writer.writerow([
            "Date",
            "Symbol",
            "Entry",
            "StopLoss",
            "Shares",
            "Exit",
            "PnLPercent",
            "Result",
            "Notes"
        ])

    print("Created trade_journal.csv")

else:

    print("trade_journal.csv already exists")

print("\nTRADE JOURNAL READY")
print("=" * 60)

with open(FILENAME, "r") as f:

    rows = list(csv.reader(f))

print(
    f"Total Trades Logged : {max(0, len(rows)-1)}"
)

print("=" * 60)
