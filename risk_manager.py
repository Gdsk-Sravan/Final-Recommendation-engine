from data_provider import get_closes

from config import TOTAL_CAPITAL
RISK_PER_TRADE_PERCENT = 1

stocks = []

with open("fusion_scores_v6.txt", "r") as f:

    for line in f:

        symbol, score = line.strip().split(",")

        score = float(score)

        if score >= 70:

            stocks.append(symbol)

print("\nRISK MANAGER")
print("=" * 70)

for symbol in stocks:

    try:

        closes = get_closes(symbol)

        if len(closes) < 20:
            continue

        entry = closes[-1]

        stop = entry * 0.95

        risk_per_share = (
            entry - stop
        )

        max_risk = (
            TOTAL_CAPITAL
            * RISK_PER_TRADE_PERCENT
            / 100
        )

        shares = int(
            max_risk
            / risk_per_share
        )

        capital_required = (
            shares
            * entry
        )

        print(
            f"{symbol}"
        )

        print(
            f"Entry           : ₹{entry:.2f}"
        )

        print(
            f"Stop Loss       : ₹{stop:.2f}"
        )

        print(
            f"Risk/Share      : ₹{risk_per_share:.2f}"
        )

        print(
            f"Shares          : {shares}"
        )

        print(
            f"Capital Needed  : ₹{capital_required:.0f}"
        )

        print("-" * 70)

    except Exception as e:

        print(symbol, e)
