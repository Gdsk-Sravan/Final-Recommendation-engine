from data_provider import get_closes

stocks = []

with open("qualified_stocks.txt", "r") as f:
    stocks = [x.strip() for x in f if x.strip()]

results = []

for i, symbol in enumerate(stocks):

    print(f"[{i+1}/{len(stocks)}] {symbol}")

    try:

        closes = get_closes(symbol)

        if len(closes) < 120:
            continue

        trades = 0
        wins = 0

        for j in range(60, len(closes) - 20):

            entry = closes[j]

            target = entry * 1.05

            future = closes[j + 1:j + 21]

            trades += 1

            if max(future) >= target:
                wins += 1

        if trades > 0:

            win_rate = (wins / trades) * 100

            results.append({
                "symbol": symbol,
                "win_rate": win_rate
            })

    except Exception as e:
        print(symbol, e)

results.sort(
    key=lambda x: x["win_rate"],
    reverse=True
)

with open("elite_stocks.txt", "w") as f:

    for stock in results[:10]:
        f.write(stock["symbol"] + "\n")

with open("elite_scores.txt", "w") as f:

    for stock in results[:10]:
        f.write(
            f"{stock['symbol']},{stock['win_rate']:.2f}\n"
        )

print("\nELITE STOCKS")
print("=" * 60)

for stock in results[:10]:

    print(
        f"{stock['symbol']} | WinRate={stock['win_rate']:.2f}%"
    )

print("\nSaved elite_stocks.txt")
print("Saved elite_scores.txt")
