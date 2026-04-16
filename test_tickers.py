import yfinance as yf
print("Testing tickers...")
tickers = ["ZOMATO.NS", "TATAMOTORS.NS", "RELIANCE.NS"]
for t in tickers:
    d = yf.download(t, period="1d", interval="5m", progress=False)
    print(f"{t}: {len(d)} rows")
