import pandas as pd
import numpy as np
import sys
import os

# Ensure root in path
sys.path.append(os.getcwd())

from src.strategies.boring_macd import ImanRetracementStrategy

def verify_iman_optimized():
    print("Verifying Optimized Iman Retracement Strategy (Phase 4)...")
    
    # Setup
    config = {}
    strategy = ImanRetracementStrategy(config)
    
    # Mock Data
    dates = pd.date_range(start='2024-01-01', periods=25, freq='5min')
    df = pd.DataFrame(index=dates)
    
    # Default State
    df['Open'] = 100.0
    df['High'] = 100.5
    df['Low'] = 99.5
    df['Close'] = 100.0
    df['Volume'] = 1000
    df['ATR'] = 1.0
    
    # 1H Data for Trend Filter
    dates_1h = pd.date_range(start='2024-01-01', periods=5, freq='1h') # Cover range
    df_1h = pd.DataFrame(index=dates_1h)
    df_1h['Close'] = 100.0
    # EMA 50
    df_1h['EMA_50'] = 90.0 # Bullish Trend (Close > EMA)
    
    # --- Test Case 1: Valid Bullish Setup (Trend Aligned) ---
    print("\n--- Test 1: Bullish Setup (Trend Aligned) ---")
    
    # Prev Candle: Bullish Impulse
    # Open=100, Close=102 (Body=2, ATR=1 -> 2 > 1.5 ATR = YES)
    # High=102.5, Low=99.5
    # Range = 3
    # Entry (25% Retrace from High) = 102.5 - (3 * 0.25) = 102.5 - 0.75 = 101.75
    # Stop (50%) = 102.5 - 1.5 = 101.0
    
    df.iloc[-2, df.columns.get_loc('Open')] = 100.0
    df.iloc[-2, df.columns.get_loc('Close')] = 102.0
    df.iloc[-2, df.columns.get_loc('High')] = 102.5
    df.iloc[-2, df.columns.get_loc('Low')] = 99.5
    df.iloc[-2, df.columns.get_loc('ATR')] = 1.0
    
    # Current Candle: Retrace to Entry
    # Low <= 101.75
    # Close > 101.0
    df.iloc[-1, df.columns.get_loc('Open')] = 102.0
    df.iloc[-1, df.columns.get_loc('High')] = 102.5
    df.iloc[-1, df.columns.get_loc('Low')] = 101.5 # Hits 101.75
    df.iloc[-1, df.columns.get_loc('Close')] = 102.2 # Close above Stop
    
    # 1H Trend: Bullish (EMA < Close)
    # 5m Close ~ 102. EMA 50 in 1H = 90. True.
    
    res = strategy.analyze(df, None, df_1h=df_1h) # df_1h passed
    print(f"Action: {res['action']}")
    print(f"Target R: {res['target_r']}")
    
    if res['action'] == 'BUY' and res['target_r'] == 2.0:
        print("PASS: Bullish Setup identified with Target 2.0R")
    else:
        print(f"FAIL: Expected BUY with 2.0R. Got {res['action']} R={res['target_r']}")
        print(f"Reason: {res.get('reason')}")

    # --- Test Case 2: Bearish Setup (Trend Counter - Should Fail) ---
    print("\n--- Test 2: Bearish Setup against Bullish Trend (Should Ignore) ---")
    # Same Market (Bullish Trend 1H EMA=90 < Close=100)
    
    # Prev Candle: Bearish Impulse
    # Open=102, Close=100 (Body=2)
    # High=102.5, Low=99.5
    # Entry (25% up from Low) = 99.5 + 0.75 = 100.25
    
    df_bear = df.copy()
    df_bear.iloc[-2, df.columns.get_loc('Open')] = 102.0
    df_bear.iloc[-2, df.columns.get_loc('Close')] = 100.0
    
    # Current Candle: Retrace Up
    # High >= 100.25
    df_bear.iloc[-1, df.columns.get_loc('High')] = 100.5
    df_bear.iloc[-1, df.columns.get_loc('Low')] = 99.0
    df_bear.iloc[-1, df.columns.get_loc('Close')] = 99.5
    
    # Expect NO SELL because Trend is Bullish
    res = strategy.analyze(df_bear, None, df_1h=df_1h)
    print(f"Action: {res['action']}")
    
    if res['action'] == 'None':
         print("PASS: Counter-trend Sell ignored")
    else:
         print(f"FAIL: Executed Counter-trend trade! Action: {res['action']}")

    print("\nVerification Complete.")

if __name__ == "__main__":
    verify_iman_optimized()
