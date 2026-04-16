from src.data_adapter import YFinanceAdapter
from src.utils import setup_logger
import pandas as pd

# Setup
adapter = YFinanceAdapter()
symbol = "BAJAJHLDNG.NS" # The one from the screenshot with +34583%

print(f"Fetching data for {symbol}...")
df = adapter.fetch_latest_candles(symbol, "5m", limit=300)

if not df.empty:
    print("\n--- Data Sample (Last 5) ---")
    print(df.tail(5))
    
    close = df.iloc[-1]['Close']
    vol = df.iloc[-1]['Volume']
    
    print(f"\nLast Price: {close}")
    print(f"Last Volume: {vol}")
    
    if vol > close and vol > 10000 and close < 10000:
         print("\n[Check] Columns look correct (Vol > Price for this stock).")
    else:
         print("\n[Check] Please verify columns manually above.")

else:
    print("Failed to fetch data.")
