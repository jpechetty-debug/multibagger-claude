import pandas as pd
import numpy as np
import sys
import os

sys.path.append(os.path.join(os.getcwd(), 'src'))
from src.pattern_scanner import PatternScanner

def create_double_top_data():
    # Create price data that forms a double top
    # 0 -> 100 (Peak 1) -> 80 (Trough) -> 100 (Peak 2) -> 70
    dates = pd.date_range(end=pd.Timestamp.now(), periods=50, freq='D')
    prices = []
    
    # Peak 1
    prices.extend(range(50, 100, 5)) # 50 to 95
    prices.append(100) # Peak
    prices.extend(range(95, 80, -5)) # 95 to 85
    prices.append(80) # Trough
    
    # Peak 2
    prices.extend(range(85, 101, 5)) # 85 to 100
    prices.append(101) # Peak
    prices.extend(range(96, 70, -5)) # Fall
    
    df = pd.DataFrame(index=dates)
    df['High'] = prices
    df['Low'] = [p - 2 for p in prices]
    df['Close'] = [p - 1 for p in prices]
    
    return df

def test_pattern_scanner():
    print("Testing Pattern Scanner...")
    df = create_double_top_data()
    
    scanner = PatternScanner(tolerance=0.05)
    results = scanner.scan_pattern(df, window=2) # Small window for small dataset
    
    print("Results:", results)
    
if __name__ == "__main__":
    test_pattern_scanner()
