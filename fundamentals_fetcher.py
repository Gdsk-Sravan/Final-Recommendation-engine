import shutil

print("\nFUNDAMENTAL FETCHER")
print("=" * 70)

source_file = "fundamental_scores.txt"

try:
    with open(source_file, "r") as f:
        lines = f.readlines()

    print(f"Loaded {len(lines)} fundamental scores")

    for line in lines[:20]:
        print(line.strip())

    print("\nFundamental scores ready")

except Exception as e:
    print(f"ERROR : {e}")
