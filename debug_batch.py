
from src.data_adapter import YFinanceAdapter
import logging

# Setup Logging to Console
logging.basicConfig(level=logging.INFO)

def test_batch():
    adapter = YFinanceAdapter()
    
    # Test with a few symbols first
    symbols = ["RELIANCE.NS", "TCS.NS", "INFY.NS"]
    print(f"Testing Batch with: {symbols}")
    
    res = adapter.fetch_batch_latest_candles(symbols, "5m")
    print(f"Result Keys: {list(res.keys())}")
    
    if res:
        print(f"Sample Data (RELIANCE): \n{res.get('RELIANCE.NS').head()}")
    else:
        print("Result is EMPTY.")

if __name__ == "__main__":
    test_batch()
