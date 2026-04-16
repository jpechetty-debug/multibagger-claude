import pandas as pd
import numpy as np
import sys
import os

# Ensure root is in path (should be by default, but explicit is safe)
sys.path.append(os.getcwd())

from src.strategies.rsi_macd_crossover import RsiMacdCrossoverStrategy
import pandas_ta as ta
import src.strategies.rsi_macd_crossover as module_under_test

def verify_rsi_macd():
    print("Verifying RSI MACD Crossover Strategy...")
    
    # 1. Setup Config
    config = {
        'TIMEPERIOD_FAST': 12,
        'TIMEPERIOD_SLOW': 26,
        'TIMEPERIOD_SIGNAL': 9,
        'TIMEPERIOD_RSI': 14,
        'OVERSOLD_VALUE': 30,
        'OVERBOUGHT_VALUE': 70
    }
    
    strategy = RsiMacdCrossoverStrategy(config)
    
    # 2. Mock Data
    # We need enough data for MACD (26+9) and RSI (14) -> ~50 points minimum
    # Let's create 100 points
    dates = pd.date_range(start='2024-01-01', periods=100, freq='5min')
    df = pd.DataFrame(index=dates)
    df['Close'] = 100.0
    df['High'] = 101.0
    df['Low'] = 99.0
    df['Open'] = 100.0
    df['Volume'] = 1000
    df['ATR'] = 1.0 # Mock ATR
    
    # 3. Inject signals by Mocking pandas_ta in the STRATEGY scope (or just relying on data)
    # It's hard to generate price data that exactly triggers RSI(MACD_Signal) crossover without a solver.
    # So we will monkeypatch/mock pandas_ta calls INSIDE the execution to force specific values.
    # This ensures we test the LOGIC of the strategy class, which is the goal.
    
    # We need to mock ta.macd and ta.rsi in the correct module.
    
    original_macd = module_under_test.ta.macd
    original_rsi = module_under_test.ta.rsi
    
    # Test Scenario 1: Buy Signal (Cross Above Oversold)
    # Prev RSI = 25, Curr RSI = 35 (Crosses 30 Up)
    print("\n--- Test Scenario 1: Buy Entry ---")
    
    def mock_macd_1(*args, **kwargs):
        # Return dataframe with MACDs column
        return pd.DataFrame({'MACDs': np.zeros(100)}) # Dummy
        
    def mock_rsi_entry_buy(*args, **kwargs):
        # Return series where last 2 values trigger buy
        s = pd.Series(np.zeros(100))
        s.iloc[-2] = 25.0
        s.iloc[-1] = 35.0
        return s
        
    module_under_test.ta.macd = mock_macd_1
    module_under_test.ta.rsi = mock_rsi_entry_buy
    
    result = strategy.analyze(df, None)
    print(f"Result Action: {result.get('action')}")
    print(f"Reason: {result.get('reason')}")
    
    if result.get('action') == 'BUY':
        print("PASS: Detected Buy Signal")
    else:
        print("FAIL: Did not detect Buy Signal")

    # Test Scenario 2: Sell Entry (Cross Below Overbought)
    # Prev RSI = 75, Curr RSI = 65 (Crosses 70 Down)
    print("\n--- Test Scenario 2: Sell Entry ---")
    
    def mock_rsi_entry_sell(*args, **kwargs):
        s = pd.Series(np.zeros(100))
        s.iloc[-2] = 75.0
        s.iloc[-1] = 65.0
        return s
        
    module_under_test.ta.rsi = mock_rsi_entry_sell
    
    result = strategy.analyze(df, None)
    print(f"Result Action: {result.get('action')}")
    
    if result.get('action') == 'SELL':
        print("PASS: Detected Sell Signal")
    else:
        print("FAIL: Did not detect Sell Signal")

    # Test Scenario 3: Buy Exit (Cross Above Overbought)
    # Prev RSI = 65, Curr RSI = 75 (Crosses 70 Up)
    print("\n--- Test Scenario 3: Buy Exit ---")
    
    def mock_rsi_exit_buy(*args, **kwargs):
        s = pd.Series(np.zeros(100))
        s.iloc[-2] = 65.0
        s.iloc[-1] = 75.0
        return s
        
    module_under_test.ta.rsi = mock_rsi_exit_buy
    
    result = strategy.analyze(df, None)
    print(f"Result Exit Signal: {result.get('exit_signal')}")
    
    if result.get('exit_signal') == 'EXIT_BUY':
        print("PASS: Detected Buy Exit")
    else:
        print("FAIL: Did not detect Buy Exit")

    # Restore
    module_under_test.ta.macd = original_macd
    module_under_test.ta.rsi = original_rsi
    print("\nVerification Complete.")

if __name__ == "__main__":
    verify_rsi_macd()
