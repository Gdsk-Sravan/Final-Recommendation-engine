import csv
import os

ACTIVE_TRADES_FILE = "active_trades.csv"

if not os.path.exists(ACTIVE_TRADES_FILE):

    with open(ACTIVE_TRADES_FILE, "w", newline="") as f:

        writer = csv.writer(f)

        writer.writerow([
            "Symbol",
            "Entry",
            "Stop",
            "Target",
            "Shares",
            "Status"
        ])

        writer.writerow([
            "KIRLOSENG.NS",
            "2389.80",
            "2270.31",
            "2628.78",
            "8",
            "OPEN"
        ])

        writer.writerow([
            "TRITURBINE.NS",
            "737.30",
            "700.43",
            "811.03",
            "27",
            "OPEN"
        ])

        writer.writerow([
            "BHARATFORG.NS",
            "2103.80",
            "1998.61",
            "2314.18",
            "9",
            "OPEN"
        ])

        writer.writerow([
            "NIACL.NS",
            "212.11",
            "201.50",
            "233.32",
            "94",
            "OPEN"
        ])

        writer.writerow([
            "LLOYDSME.NS",
            "1785.60",
            "1696.32",
            "1964.16",
            "11",
            "OPEN"
        ])

        writer.writerow([
            "HSCL.NS",
            "655.05",
            "622.30",
            "720.55",
            "30",
            "OPEN"
        ])

    print("Created active_trades.csv")

print("\nTRADE MANAGER")
print("=" * 60)

with open(ACTIVE_TRADES_FILE, "r") as f:

    reader = csv.DictReader(f)

    trades = list(reader)

print(
    f"Active Trades : {len(trades)}"
)

for trade in trades:

    print(
        f"{trade['Symbol']} | "
        f"{trade['Status']}"
    )

print("=" * 60)
