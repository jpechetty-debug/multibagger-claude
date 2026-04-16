
import logging
import time
from src.data_adapter import YFinanceAdapter
from src.utils import setup_logger

def test_batch():
    logger = setup_logger("IntradaySignals.BatchTest")
    adapter = YFinanceAdapter()
    
    symbols = ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS"] # Small test
    
    print("Testing 5m Batch Fetch...")
    start = time.time()
    data = adapter.fetch_batch_latest_candles(symbols, "5m", limit=100)
    print(f"5m Batch Fetch took {time.time() - start:.2f}s. Keys: {list(data.keys())}")
    
    print("\nTesting 1d Batch Fetch...")
    start = time.time()
    daily = adapter.fetch_batch_latest_candles(symbols, "1d", limit=100)
    print(f"1d Batch Fetch took {time.time() - start:.2f}s. Keys: {list(daily.keys())}")
    
    if not daily:
        print("ERROR: Daily batch returned empty!")
    else:
        print("PASS: Daily batch fetched.")

if __name__ == "__main__":
    test_batch()
