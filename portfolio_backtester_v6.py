from historical_ranker import get_historical_score
from data_provider import get_closes

with open("low_volatility_stocks.txt", "r") as f:

    stocks = [x.strip() for x in f if x.strip()]

all_returns = []

equity = 100000

peak_equity = equity

max_drawdown = 0

print("\nPORTFOLIO BACKTESTER V6")
print("=" * 60)

for day_index in range(260, 441, 20):

    rankings = []

    for stock in stocks:

        try:

            closes = get_closes(stock)

            if len(closes) <= day_index + 20:
                continue

            score = get_historical_score(
                stock,
                day_index
            )

            if score is None:
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

    top5 = rankings[:5]

    returns = []

    for symbol, score in top5:

        closes = get_closes(symbol)

        entry = closes[day_index]

        exit_price = closes[day_index + 20]

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

    equity = equity * (
        1 + avg_return / 100
    )

    if equity > peak_equity:

        peak_equity = equity

    drawdown = (
        (peak_equity - equity)
        / peak_equity
    ) * 100

    if drawdown > max_drawdown:

        max_drawdown = drawdown

    print(
        f"Day {day_index} "
        f"| Return={avg_return:.2f}% "
        f"| Equity={equity:.0f}"
    )

print("\n" + "=" * 60)

wins = len(
    [x for x in all_returns if x > 0]
)

losses = len(
    [x for x in all_returns if x <= 0]
)

overall_return = (
    sum(all_returns)
    / len(all_returns)
)

win_rate = (
    wins
    / len(all_returns)
) * 100

print(f"Tests          : {len(all_returns)}")
print(f"Wins           : {wins}")
print(f"Losses         : {losses}")
print(f"Average Return : {overall_return:.2f}%")
print(f"Win Rate       : {win_rate:.2f}%")
print(f"Max Drawdown   : {max_drawdown:.2f}%")

print("=" * 60)

