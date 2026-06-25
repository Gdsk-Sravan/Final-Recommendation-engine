from data_provider import get_closes

from config import TOTAL_CAPITAL
RISK_PER_TRADE_PERCENT = 1

ATR_PERIOD = 14
ATR_MULTIPLIER = 2

MAX_POSITION_PERCENT = 20

stocks = []

with open("fusion_scores_v6.txt", "r") as f:

    for line in f:

        symbol, score = line.strip().split(",")

        if float(score) >= 70:

            stocks.append(symbol)

print("\nATR RISK MANAGER V2")
print("=" * 70)

max_position_value = (
    TOTAL_CAPITAL
    * MAX_POSITION_PERCENT
    / 100
)

for symbol in stocks:

    try:

        closes = get_closes(symbol)

        if len(closes) < ATR_PERIOD + 1:
            continue

        entry = closes[-1]

        ranges = []

        for i in range(-ATR_PERIOD, 0):

            daily_range = abs(
                closes[i]
                - closes[i - 1]
            )

            ranges.append(
                daily_range
            )

        atr = (
            sum(ranges)
            / len(ranges)
        )

        stop = (
            entry
            - (atr * ATR_MULTIPLIER)
        )

        risk_per_share = (
            entry
            - stop
        )

        max_risk = (
            TOTAL_CAPITAL
            * RISK_PER_TRADE_PERCENT
            / 100
        )

        risk_based_shares = int(
            max_risk
            / risk_per_share
        )

        capital_based_shares = int(
            max_position_value
            / entry
        )

        shares = min(
            risk_based_shares,
            capital_based_shares
        )

        capital_required = (
            shares
            * entry
        )

        target = (
            entry
            + (risk_per_share * 2)
        )

        print(f"\n{symbol}")

        print(
            f"Entry          : ₹{entry:.2f}"
        )

        print(
            f"ATR            : ₹{atr:.2f}"
        )

        print(
            f"Stop Loss      : ₹{stop:.2f}"
        )

        print(
            f"Target         : ₹{target:.2f}"
        )

        print(
            f"Shares         : {shares}"
        )

        print(
            f"Capital Needed : ₹{capital_required:.0f}"
        )

        print("-" * 70)

    except Exception as e:

        print(symbol, e)

print("\n" + "=" * 70)
print("ATR RISK ANALYSIS COMPLETE")
print("=" * 70)
