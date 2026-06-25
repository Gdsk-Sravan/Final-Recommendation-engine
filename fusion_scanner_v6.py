from data_provider import get_closes, get_volumes

def ema(prices, period):

    multiplier = 2 / (period + 1)

    ema_value = sum(prices[:period]) / period

    for price in prices[period:]:

        ema_value = (
            (price - ema_value) * multiplier
            + ema_value
        )

    return ema_value


history_scores = {}

with open("elite_scores_v3.txt", "r") as f:

    for line in f:

        symbol, score = line.strip().split(",")

        history_scores[symbol] = float(score)


with open("low_volatility_stocks.txt", "r") as f:

    stocks = [x.strip() for x in f if x.strip()]


results = []

for symbol in stocks:

    try:

        closes = get_closes(symbol)

        volumes = get_volumes(symbol)

        if len(closes) < 252:
            continue

        if len(volumes) < 20:
            continue

        current = closes[-1]

        ema20 = ema(closes, 20)

        ema50 = ema(closes, 50)

        trend_score = 0

        if current > ema20:

            trend_score += 50

        if ema20 > ema50:

            trend_score += 50

        rs = (
            (current - closes[-126])
            / closes[-126]
        ) * 100

        rs_score = min(
            max(rs, 0),
            100
        )

        high_52w = max(
            closes[-252:]
        )

        distance = (
            (high_52w - current)
            / high_52w
        ) * 100

        high_score = 100

        if distance > 20:

            high_score = 0

        elif distance > 10:

            high_score = 50

        avg_volume = (
            sum(volumes[-20:])
            / 20
        )

        latest_volume = volumes[-1]

        volume_ratio = (
            latest_volume
            / avg_volume
        )

        volume_score = 0

        if volume_ratio >= 2:

            volume_score = 100

        elif volume_ratio >= 1.5:

            volume_score = 75

        elif volume_ratio >= 1.2:

            volume_score = 50

        history_score = history_scores.get(
            symbol,
            0
        )

        final_score = (
            trend_score * 0.30 +
            rs_score * 0.25 +
            high_score * 0.15 +
            volume_score * 0.15 +
            history_score * 0.15
        )

        results.append({
            "symbol": symbol,
            "score": final_score,
            "history": history_score,
            "rs": rs,
            "volume_ratio": volume_ratio
        })

    except:
        pass


results.sort(
    key=lambda x: x["score"],
    reverse=True
)

with open("fusion_scores_v6.txt", "w") as f:

    for stock in results:

        f.write(
            f"{stock['symbol']},{stock['score']:.2f}\n"
        )

print("\nFUSION SCANNER V6")
print("=" * 60)

for i, stock in enumerate(results[:20], start=1):

    print(
        f"{i}. "
        f"{stock['symbol']} "
        f"| Score={stock['score']:.2f} "
        f"| Hist={stock['history']:.2f} "
        f"| RS={stock['rs']:.2f}% "
        f"| Vol={stock['volume_ratio']:.2f}x"
    )

print("\nSaved fusion_scores_v6.txt")
