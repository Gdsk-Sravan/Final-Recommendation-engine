import csv

from config import TOTAL_CAPITAL

positions = []

with open("active_trades.csv", "r") as f:

    reader = csv.DictReader(f)

    for trade in reader:

        entry = float(
            trade["Entry"]
        )

        shares = int(
            trade["Shares"]
        )

        current_value = (
            entry * shares
        )

        positions.append({
            "symbol": trade["Symbol"],
            "entry": entry,
            "shares": shares,
            "value": current_value
        })

total_required = sum(
    x["value"]
    for x in positions
)

scale_factor = (
    TOTAL_CAPITAL
    / total_required
)

print("\nPORTFOLIO ALLOCATOR")
print("=" * 70)

allocated_total = 0

for position in positions:

    adjusted_value = (
        position["value"]
        * scale_factor
    )

    adjusted_shares = int(
        adjusted_value
        / position["entry"]
    )

    final_value = (
        adjusted_shares
        * position["entry"]
    )

    allocated_total += final_value

    print(
        f"{position['symbol']} | "
        f"Shares={adjusted_shares} | "
        f"Capital=₹{final_value:.0f}"
    )

print("\n" + "=" * 70)

print(
    f"Original Required : ₹{total_required:.0f}"
)

print(
    f"Allocated Capital : ₹{allocated_total:.0f}"
)

print(
    f"Cash Remaining    : ₹{TOTAL_CAPITAL - allocated_total:.0f}"
)

print("=" * 70)
