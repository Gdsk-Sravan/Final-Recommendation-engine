sectors = {

    "DEFENCE": [
        "HAL.NS",
        "BEL.NS"
    ],

    "BANKING": [
        "HDFCBANK.NS",
        "ICICIBANK.NS",
        "SBIN.NS",
        "AXISBANK.NS"
    ],

    "PHARMA": [
        "SUNPHARMA.NS",
        "DIVISLAB.NS"
    ],

    "AUTO": [
        "MARUTI.NS",
        "EICHERMOT.NS"
    ]
}

print("\nSECTOR STRENGTH")
print("=" * 60)

for sector in sectors:

    print(f"\n{sector}")

    for stock in sectors[sector]:

        print(f"  {stock}")
