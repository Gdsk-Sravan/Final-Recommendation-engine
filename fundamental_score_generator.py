import csv

print("\nFUNDAMENTAL SCORE GENERATOR")
print("=" * 70)

results = []

with open("fundamental_data.csv", "r") as f:

    reader = csv.DictReader(f)

    for row in reader:

        score = 0

        if float(row["ROE"]) > 15:
            score += 20

        if float(row["ROCE"]) > 15:
            score += 20

        if float(row["DebtEquity"]) < 0.5:
            score += 20

        if float(row["SalesGrowth"]) > 10:
            score += 20

        if float(row["ProfitGrowth"]) > 10:
            score += 20

        results.append(
            (
                row["Symbol"],
                score
            )
        )

with open("fundamental_scores.txt", "w") as f:

    for symbol, score in results:

        f.write(
            f"{symbol},{score}\n"
        )

        print(
            f"{symbol} | Score={score}"
        )

print("\nSaved fundamental_scores.txt")
