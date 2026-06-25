rankings = []

with open("fusion_scores_v6.txt", "r") as f:

    for line in f:

        symbol, score = line.strip().split(",")

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

BUY_THRESHOLD = 70
WATCH_THRESHOLD = 60

buy_list = []
watch_list = []
avoid_list = []

for symbol, score in rankings:

    if score >= BUY_THRESHOLD:

        buy_list.append(
            (
                symbol,
                score
            )
        )

    elif score >= WATCH_THRESHOLD:

        watch_list.append(
            (
                symbol,
                score
            )
        )

    else:

        avoid_list.append(
            (
                symbol,
                score
            )
        )

print("\nRECOMMENDATION ENGINE V5")
print("=" * 70)

print("\nTOP BUY NOW")
print("-" * 40)

if len(buy_list) == 0:

    print("No Buy Candidates")

else:

    for i, stock in enumerate(buy_list[:10], start=1):

        print(
            f"{i}. {stock[0]} | Score={stock[1]:.2f}"
        )

print("\nWATCHLIST")
print("-" * 40)

if len(watch_list) == 0:

    print("No Watchlist Stocks")

else:

    for i, stock in enumerate(watch_list[:15], start=1):

        print(
            f"{i}. {stock[0]} | Score={stock[1]:.2f}"
        )

print("\nAVOID")
print("-" * 40)

if len(avoid_list) == 0:

    print("No Avoid Stocks")

else:

    for stock in avoid_list[:10]:

        print(
            f"{stock[0]} | Score={stock[1]:.2f}"
        )

print("\n" + "=" * 70)

print(f"Total Stocks      : {len(rankings)}")
print(f"Buy Candidates    : {len(buy_list)}")
print(f"Watchlist Stocks  : {len(watch_list)}")
print(f"Avoid Stocks      : {len(avoid_list)}")

print("=" * 70)
