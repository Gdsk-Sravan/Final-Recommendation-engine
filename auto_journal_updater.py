import csv
from datetime import datetime

from data_provider import get_closes

ACTIVE_FILE = "active_trades.csv"
JOURNAL_FILE = "trade_journal.csv"

with open(ACTIVE_FILE, "r") as f:

    reader = csv.DictReader(f)

    trades = list(reader)

remaining_trades = []

closed_count = 0

for trade in trades:

    try:

        symbol = trade["Symbol"]

        entry = float(
            trade["Entry"]
        )

        stop = float(
            trade["Stop"]
        )

        target = float(
            trade["Target"]
        )

        shares = int(
            trade["Shares"]
        )

        status = trade["Status"]

        closes = get_closes(symbol)

        if not closes:

            remaining_trades.append(
                trade
            )

            continue

        current = closes[-1]

        result = None

        if current <= stop:

            result = "STOP LOSS"

        elif current >= target:

            result = "TARGET HIT"

        if result is None:

            remaining_trades.append(
                trade
            )

            continue

        pnl_percent = (
            (current - entry)
            / entry
        ) * 100

        with open(
            JOURNAL_FILE,
            "a",
            newline=""
        ) as jf:

            writer = csv.writer(jf)

            writer.writerow([
                datetime.now().strftime(
                    "%Y-%m-%d"
                ),
                symbol,
                entry,
                stop,
                shares,
                current,
                round(
                    pnl_percent,
                    2
                ),
                result,
                "Auto Closed"
            ])

        closed_count += 1

        print(
            f"{symbol} -> {result}"
        )

    except Exception as e:

        print(trade, e)

        remaining_trades.append(
            trade
        )

with open(
    ACTIVE_FILE,
    "w",
    newline=""
) as f:

    writer = csv.DictWriter(
        f,
        fieldnames=[
            "Symbol",
            "Entry",
            "Stop",
            "Target",
            "Shares",
            "Status"
        ]
    )

    writer.writeheader()

    writer.writerows(
        remaining_trades
    )

print("\nAUTO JOURNAL UPDATER")
print("=" * 60)

print(
    f"Closed Trades : {closed_count}"
)

print(
    f"Open Trades   : {len(remaining_trades)}"
)

print("=" * 60)
