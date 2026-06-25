news_scores = {
    "HAL.NS": 10,
    "DIVISLAB.NS": 5,
    "BAJFINANCE.NS": 0,
    "ADANIPORTS.NS": 5,
    "LT.NS": 5
}

print("\nNEWS ENGINE")
print("=" * 60)

for stock, score in news_scores.items():

    sentiment = "NEUTRAL"

    if score > 0:
        sentiment = "POSITIVE"

    if score < 0:
        sentiment = "NEGATIVE"

    print(
        f"{stock} | News Score={score} | {sentiment}"
    )
