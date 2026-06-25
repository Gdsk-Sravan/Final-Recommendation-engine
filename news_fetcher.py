import requests

headers = {
    "User-Agent": "Mozilla/5.0"
}

stocks = []

with open("elite_stocks.txt", "r") as f:

    stocks = [
        x.strip()
        for x in f
        if x.strip()
    ]

print("\nNEWS FETCHER")
print("=" * 70)

with open("news_scores.txt", "w") as output:

    for symbol in stocks:

        try:

            ticker = symbol.replace(".NS", "")

            url = (
                f"https://query1.finance.yahoo.com/v1/finance/search?q={ticker}"
            )

            response = requests.get(
                url,
                headers=headers,
                timeout=10
            )

            score = 0

            if response.status_code == 200:

                score = 5

            output.write(
                f"{symbol},{score}\n"
            )

            print(
                f"{symbol} | News Score={score}"
            )

        except Exception:

            output.write(
                f"{symbol},0\n"
            )

            print(
                f"{symbol} | News Score=0"
            )

print("\nSaved news_scores.txt")
