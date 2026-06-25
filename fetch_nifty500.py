import requests

url = "https://archives.nseindia.com/content/indices/ind_nifty500list.csv"

response = requests.get(url)

lines = response.text.splitlines()

with open("stocks.txt", "w") as f:

    for line in lines[1:]:

        cols = line.split(",")

        if len(cols) > 2:

            symbol = cols[2].strip()

            if symbol:
                f.write(symbol + ".NS\n")

print("Nifty 500 downloaded")
