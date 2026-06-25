from data_provider import get_closes

def ema(prices, period):

    multiplier = 2 / (period + 1)

    ema_value = sum(prices[:period]) / period

    for price in prices[period:]:

        ema_value = (
            (price - ema_value) * multiplier
            + ema_value
        )

    return ema_value


with open("qualified_stocks.txt", "r") as f:

    stocks = [x.strip() for x in f if x.strip()]


total_trades = 0

wins = 0
losses = 0

all_returns = []

winning_returns = []
losing_returns = []


for stock in stocks:

    try:

        closes = get_closes(stock)

        if len(closes) < 252:
            continue

        for i in range(252, len(closes) - 20):

            history = closes[:i + 1]

            current = history[-1]

            ema20 = ema(history, 20)
            ema50 = ema(history, 50)

            rs = (
                (current - history[-126])
                / history[-126]
            ) * 100

            high_52w = max(history[-252:])

            distance = (
                (high_52w - current)
                / high_52w
            ) * 100

            if not (
                current > ema20
                and ema20 > ema50
                and rs > 20
                and distance < 10
            ):
                continue

            entry = current

            target = entry * 1.10
            stop = entry * 0.95

            future = closes[i + 1:i + 21]

            trade_return = 0

            hit_exit = False

            for price in future:

                if price >= target:

                    trade_return = 10

                    wins += 1

                    winning_returns.append(
                        trade_return
                    )

                    hit_exit = True

                    break

                if price <= stop:

                    trade_return = -5

                    losses += 1

                    losing_returns.append(
                        abs(trade_return)
                    )

                    hit_exit = True

                    break

            if not hit_exit:

                final_price = future[-1]

                trade_return = (
                    (final_price - entry)
                    / entry
                ) * 100

                if trade_return > 0:

                    wins += 1

                    winning_returns.append(
                        trade_return
                    )

                else:

                    losses += 1

                    losing_returns.append(
                        abs(trade_return)
                    )

            total_trades += 1

            all_returns.append(
                trade_return
            )

    except Exception as e:

        print(stock, e)


avg_return = 0
avg_win = 0
avg_loss = 0
profit_factor = 0
win_rate = 0

if total_trades > 0:

    avg_return = (
        sum(all_returns)
        / len(all_returns)
    )

    win_rate = (
        wins / total_trades
    ) * 100

if winning_returns:

    avg_win = (
        sum(winning_returns)
        / len(winning_returns)
    )

if losing_returns:

    avg_loss = (
        sum(losing_returns)
        / len(losing_returns)
    )

gross_profit = sum(winning_returns)
gross_loss = sum(losing_returns)

if gross_loss > 0:

    profit_factor = (
        gross_profit
        / gross_loss
    )


print("\nSTRATEGY VALIDATION V3")
print("=" * 60)

print("Total Trades :", total_trades)
print("Wins         :", wins)
print("Losses       :", losses)

print(
    f"Win Rate     : {win_rate:.2f}%"
)

print(
    f"Avg Return   : {avg_return:.2f}%"
)

print(
    f"Average Win  : {avg_win:.2f}%"
)

print(
    f"Average Loss : {avg_loss:.2f}%"
)

print(
    f"ProfitFactor : {profit_factor:.2f}"
)

print("=" * 60)
