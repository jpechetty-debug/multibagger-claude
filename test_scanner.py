import yaml
import logging
from src.market_scanner import MarketScanner
from src.utils import setup_logger

def test_scanner():
    setup_logger("IntradaySignals")
    print("Testing Market Scanner...")
    
    with open("config/config.yaml", "r") as f:
        config = yaml.safe_load(f)
        
    scanner = MarketScanner(config)
    
    # Use the symbols from config
    universe = config['symbols']
    
    print(f"Scanning {len(universe)} symbols...")
    top_stocks = scanner.scan(universe)
    
    print("\n=== Result ===")
    print(top_stocks)
    
    if len(top_stocks) > 0 and len(top_stocks) <= config['scanner_limit']:
        print("✅ SUCCESS: Scanner returned stocks.")
    else:
        print("❌ FAILURE: Scanner returned invalid number of stocks.")

if __name__ == "__main__":
    test_scanner()
