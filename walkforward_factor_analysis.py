from historical_ranker import get_historical_score
from data_provider import get_closes

print("\nWALKFORWARD FACTOR ANALYSIS")
print("=" * 70)

test_days = [
    260,
    280,
    300,
    320,
    340,
    360,
    380,
    400
]

all_returns = []

for day_index in test_days:

    rankings = []

    with open("qualified_stocks.txt", "r") as f:

        stocks = [
            x.strip()
            for x in f
            if x.strip()
        ]

    for stock in stocks:

        try:

            score = get_historical_score(
                stock,
                day_index
            )

            if score is None:
                continue

            closes = get_closes(stock)

            if len(closes) <= day_index + 20:
                continue

            rankings.append(
                (
                    stock,
                    score
                )
            )

        except:
            pass

    rankings.sort(
        key=lambda x: x[1],
        reverse=True
    )

    top10 = rankings[:10]

    returns = []

    for symbol, score in top10:

        closes = get_closes(symbol)

        entry = closes[day_index]

        exit_price = closes[
            day_index + 20
        ]

        trade_return = (
            (exit_price - entry)
            / entry
        ) * 100

        returns.append(
            trade_return
        )

    if not returns:
        continue

    avg_return = (
        sum(returns)
        / len(returns)
    )

    all_returns.append(
        avg_return
    )

    print(
        f"Day {day_index} | "
        f"Top10 Return = "
        f"{avg_return:.2f}%"
    )

print("\n" + "=" * 70)

if all_returns:

    overall = (
        sum(all_returns)
        / len(all_returns)
    )

    wins = len(
        [
            x
            for x in all_returns
            if x > 0
        ]
    )

    win_rate = (
        wins
        / len(all_returns)
    ) * 100

    print(
        f"Tests          : {len(all_returns)}"
    )

    print(
        f"Average Return : {overall:.2f}%"
    )

    print(
        f"Win Rate       : {win_rate:.2f}%"
    )

print("=" * 70)
