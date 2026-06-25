import requests
import csv

headers = {
    "User-Agent": "Mozilla/5.0"
}

stocks = []

with open("qualified_stocks.txt", "r") as f:
    stocks = [x.strip() for x in f if x.strip()]

results = []

print("\nYAHOO FUNDAMENTALS FETCHER")
print("=" * 70)

for symbol in stocks:

    try:

        url = (
            "https://query1.finance.yahoo.com"
            f"/v10/finance/quoteSummary/{symbol}"
            "?modules=financialData,defaultKeyStatistics"
        )

        response = requests.get(
            url,
            headers=headers,
            timeout=15
        )

        print(
            f"{symbol} | HTTP={response.status_code}"
        )

        data = response.json()

        result = data["quoteSummary"]["result"][0]

        financial = result.get(
            "financialData",
            {}
        )

        stats = result.get(
            "defaultKeyStatistics",
            {}
        )

        roe = (
            stats.get(
                "returnOnEquity",
                {}
            ).get("raw")
        )

        debt = (
            financial.get(
                "debtToEquity",
                {}
            ).get("raw")
        )

        revenue_growth = (
            financial.get(
                "revenueGrowth",
                {}
            ).get("raw")
        )

        profit_margin = (
            financial.get(
                "profitMargins",
                {}
            ).get("raw")
        )

        results.append([
            symbol,
            roe,
            debt,
            revenue_growth,
            profit_margin
        ])

        print(f"{symbol} OK")

    except Exception as e:

        print(
            f"{symbol} FAILED : {e}"
        )

with open(
    "yahoo_fundamental_data.csv",
    "w",
    newline=""
) as f:

    writer = csv.writer(f)

    writer.writerow([
        "Symbol",
        "ROE",
        "DebtEquity",
        "RevenueGrowth",
        "ProfitMargin"
    ])

    writer.writerows(results)

print("\nSaved yahoo_fundamental_data.csv")
print(
    f"Rows : {len(results)}"
)
