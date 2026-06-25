from data_provider import get_closes

CAPITAL = 100000
RISK_PER_TRADE = 1000

print("\nTRADE EXECUTION PLAN")
print("=" * 70)

with open("fusion_scores_v6.txt", "r") as f:

    for line in f:

        symbol, score = line.strip().split(",")

        score = float(score)

        if score < 70:
            continue

        closes = get_closes(symbol)

        if not closes:
            continue

        entry = closes[-1]

        stop = entry * 0.95

        target1 = entry * 1.10

        target2 = entry * 1.20

        risk_per_share = entry - stop

        shares = int(
            RISK_PER_TRADE
            / risk_per_share
        )

        capital_required = (
            shares * entry
        )

        print(f"\n{symbol}")

        print(f"Score           : {score:.2f}")
        print(f"Entry           : ₹{entry:.2f}")
        print(f"Stop Loss       : ₹{stop:.2f}")
        print(f"Target 1        : ₹{target1:.2f}")
        print(f"Target 2        : ₹{target2:.2f}")
        print(f"Shares          : {shares}")
        print(f"Capital Needed  : ₹{capital_required:.0f}")

        print("-" * 70)
