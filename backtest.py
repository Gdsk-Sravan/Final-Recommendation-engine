import requests

headers = {
    "User-Agent": "Mozilla/5.0"
}

stocks = []

with open("qualified_stocks.txt", "r") as f:
    stocks = [x.strip() for x in f if x.strip()]

for symbol in stocks:

    try:

        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=2y&interval=1d"

        response = requests.get(url, headers=headers)

        data = response.json()

        closes = data["chart"]["result"][0]["indicators"]["quote"][0]["close"]

        closes = [x for x in closes if x is not None]

        trades = 0
        wins = 0

        for i in range(60, len(closes) - 20):

            entry = closes[i]

            target = entry * 1.05

            future = closes[i+1:i+21]

            trades += 1

            if max(future) >= target:
                wins += 1

        if trades > 0:

            win_rate = (wins / trades) * 100

            print(
                f"{symbol} | "
                f"Trades={trades} | "
                f"WinRate={win_rate:.2f}%"
            )

    except:
        pass
