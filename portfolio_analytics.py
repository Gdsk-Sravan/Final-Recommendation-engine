import csv

from config import TOTAL_CAPITAL

print("\nPORTFOLIO ANALYTICS")
print("=" * 70)

invested = 0

positions = 0

with open("active_trades.csv", "r") as f:

    reader = csv.DictReader(f)

    for trade in reader:

        entry = float(trade["Entry"])

        shares = int(trade["Shares"])

        invested += (
            entry * shares
        )

        positions += 1

cash = (
    TOTAL_CAPITAL
    - invested
)

exposure = (
    invested
    / TOTAL_CAPITAL
) * 100

print(
    f"Portfolio Capital : ₹{TOTAL_CAPITAL:.0f}"
)

print(
    f"Invested Capital  : ₹{invested:.0f}"
)

print(
    f"Cash Remaining    : ₹{cash:.0f}"
)

print(
    f"Open Positions    : {positions}"
)

print(
    f"Exposure          : {exposure:.2f}%"
)

print("=" * 70)
