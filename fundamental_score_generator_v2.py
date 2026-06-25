import csv

results = []

with open(
    "fundamental_data.csv",
    "r"
) as f:

    reader = csv.DictReader(f)

    for row in reader:

        try:

            symbol = row["Symbol"]

            roe = float(row["ROE"])
            roce = float(row["ROCE"])
            debt = float(row["DebtEquity"])
            sales = float(row["SalesGrowth"])
            profit = float(row["ProfitGrowth"])

            # Scores capped at 100

            roe_score = min(
                roe * 3,
                100
            )

            roce_score = min(
                roce * 3,
                100
            )

            sales_score = min(
                sales * 4,
                100
            )

            profit_score = min(
                profit * 4,
                100
            )

            debt_score = max(
                0,
                100 - debt * 20
            )

            final_score = (

                roe_score * 0.25 +

                roce_score * 0.25 +

                sales_score * 0.20 +

                profit_score * 0.20 +

                debt_score * 0.10

            )

            results.append(
                (
                    symbol,
                    final_score
                )
            )

        except:
            pass

results.sort(
    key=lambda x: x[1],
    reverse=True
)

with open(
    "fundamental_scores.txt",
    "w"
) as f:

    for symbol, score in results:

        f.write(
            f"{symbol},{score:.2f}\n"
        )

print("\nFUNDAMENTAL SCORES")
print("=" * 60)

for symbol, score in results[:20]:

    print(
        f"{symbol} | "
        f"Score={score:.2f}"
    )

print("=" * 60)

print(
    f"Stocks Ranked : {len(results)}"
)
