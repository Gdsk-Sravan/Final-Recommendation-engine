print("\n")
print("=" * 70)
print("DAILY SWING TRADING REPORT")
print("=" * 70)

print("\nMARKET SUMMARY")
print("-" * 40)

try:

    with open("qualified_stocks.txt", "r") as f:

        qualified = len([
            x for x in f
            if x.strip()
        ])

    with open("stocks.txt", "r") as f:

        total = len([
            x for x in f
            if x.strip()
        ])

    breadth = (
        qualified / total
    ) * 100

    print(
        f"Market Breadth : {breadth:.2f}%"
    )

except:

    print("Market Breadth : N/A")

print("\nTOP BUY NOW")
print("-" * 40)

try:

    rankings = []

    with open("fusion_scores.txt", "r") as f:

        for line in f:

            symbol, score = (
                line.strip().split(",")
            )

            rankings.append(
                (
                    symbol,
                    float(score)
                )
            )

    rankings.sort(
        key=lambda x: x[1],
        reverse=True
    )

    for stock in rankings[:3]:

        print(
            f"{stock[0]} | "
            f"Score={stock[1]:.1f}"
        )

except:

    print("No Recommendations")

print("\nWATCHLIST")
print("-" * 40)

try:

    for stock in rankings[3:6]:

        print(
            f"{stock[0]} | "
            f"Score={stock[1]:.1f}"
        )

except:

    print("No Watchlist")

print("\nAVOID")
print("-" * 40)

try:

    for stock in rankings[-3:]:

        print(
            f"{stock[0]} | "
            f"Score={stock[1]:.1f}"
        )

except:

    print("No Data")

print("\n" + "=" * 70)
print("END OF REPORT")
print("=" * 70)
