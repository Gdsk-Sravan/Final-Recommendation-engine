import csv

fundamental_symbols = set()

with open(
    "fundamental_data.csv",
    "r"
) as f:

    reader = csv.DictReader(f)

    for row in reader:

        fundamental_symbols.add(
            row["Symbol"]
        )

qualified = []

with open(
    "qualified_stocks.txt",
    "r"
) as f:

    qualified = [
        x.strip()
        for x in f
        if x.strip()
    ]

covered = 0

missing = []

for stock in qualified:

    if stock in fundamental_symbols:

        covered += 1

    else:

        missing.append(stock)

print("\nFUNDAMENTAL COVERAGE")
print("=" * 60)

print(
    f"Qualified Stocks : {len(qualified)}"
)

print(
    f"Covered          : {covered}"
)

print(
    f"Missing          : {len(missing)}"
)

print(
    f"Coverage %       : {(covered/len(qualified))*100:.2f}%"
)

print("\nFIRST 20 MISSING")

for stock in missing[:20]:

    print(stock)

print("=" * 60)
