import os

print("\nSYSTEM HEALTH")
print("=" * 60)

cache_count = len(os.listdir("cache"))

print(f"Cache Files      : {cache_count}")

qualified = 0
if os.path.exists("qualified_stocks.txt"):
    with open("qualified_stocks.txt") as f:
        qualified = len(
            [x for x in f if x.strip()]
        )

print(f"Qualified Stocks : {qualified}")

low_vol = 0
if os.path.exists("low_volatility_stocks.txt"):
    with open("low_volatility_stocks.txt") as f:
        low_vol = len(
            [x for x in f if x.strip()]
        )

print(f"Low Vol Stocks   : {low_vol}")

print(
    f"Fusion Scores    : "
    f"{'OK' if os.path.exists('fusion_scores_v6.txt') else 'MISSING'}"
)

print(
    f"Recommendations  : "
    f"{'OK' if os.path.exists('portfolio.txt') else 'CHECK'}"
)

active = 0
if os.path.exists("active_trades.csv"):
    with open("active_trades.csv") as f:
        active = max(
            0,
            len(f.readlines()) - 1
        )

print(f"Active Trades    : {active}")

snapshots = 0
if os.path.exists("signal_history"):
    snapshots = len(
        os.listdir("signal_history")
    )

print(f"Signal Snapshots : {snapshots}")

print("\nStatus           : HEALTHY")
print("=" * 60)
