import sys
import os
import pandas as pd
import numpy as np

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.strategy import StrategyEngine
from src.indicators import calculate_indicators, calculate_trend_indicators

def test_smc_bullish_bos():
    """
    Test scenario:
    1. Establish a Swing High at Price 105.
    2. Drop to Swing Low.
    3. Rally and Close above 105 -> BUY.
    """
    
    # 1. Generate Data
    # 09:30 start
    times = pd.date_range(start="2025-01-01 09:30", periods=100, freq="5min")
    data = []
    
    # Base price movement
    # 0-30: Flat/Noise around 100
    prices = [100] * 30 
    
    # 30-45: Rally to peak 105
    # Peak at index 30+4=34?
    # Note: prices += below appends.
    
    prices += [101, 102, 103, 104, 105, 104, 103, 102, 101, 100] # Peak Index ~34 (Value 105)
    
    # 40-50: Drop to low 95
    prices += [99, 98, 97, 96, 95, 96, 97, 98, 99, 100] # Low Index ~44 (Value 95)
    
    # 50-60: Rally to Break
    prices += [101, 102, 103, 104, 104.5, 107, 107, 108, 109, 110] # Break Index ~55 (Value 107)
    
    # Fill rest
    while len(prices) < 100: prices.append(110)
    
    df = pd.DataFrame(index=times)
    df['Close'] = prices
    df['Open'] = df['Close']
    df['High'] = df['Close'] + 1 # Simple Wicks
    df['Low'] = df['Close'] - 1
    df['Volume'] = 10000
    
    # Calculate Indicators
    df = calculate_indicators(df)
    
    # Determine exact break index manually
    # Find first index where Close > 105 AFTER index 40
    # 55?
    break_indices = [i for i, x in enumerate(prices) if x > 106.5] # Find 107
    break_idx = break_indices[0] 
    
    print(f"Break Event Index: {break_idx}")
    
    df_slice = df.iloc[:break_idx+1]
    print(f"Slice Length: {len(df_slice)}")
    
    # 2. Config
    config = {
        'strategy_mode': 'SMC_SCALP',
        'trend_timeframe': '1h',
        'timeframe': '5m'
    }
    
    engine = StrategyEngine(config)
    
    # 3. Mock HTF Trend (Bullish)
    df_1h = pd.DataFrame({'Close': [120, 120], 'EMA_50': [100, 100]}, index=[times[0], times[-1]])
    
    df_15m = pd.DataFrame({'Close': [100]*5, 'ADX': [25]*5}, index=times[:5]) # Dummy 15m with Strong Trend
    
    signal = engine.analyze(
        df_5m=df_slice, 
        df_15m=df_15m, 
        df_1h=df_1h,
        daily_bias="BULLISH"
    )
    
    print("Signal Result:", signal)
    print("Action:", signal['action'])
    print("Indicator State:", signal.get('indicators'))
    
    # Assertions
    success = True
    if signal['action'] == "BUY":
        print("PASS: Correctly signaled BUY")
    else:
        print("FAIL: Did not signal BUY")
        success = False

    if "SMC Trend Continuation (BOS)" in signal['reason']:
        print("PASS: Correct Reason")
    
    if signal['indicators']['SMC_BOS'] == "BULLISH_BOS":
        print("PASS: Correct BOS Detection")
    else:
        print(f"FAIL: BOS Detection = {signal['indicators']['SMC_BOS']}")
        success = False
        
    if not success:
        sys.exit(1)

if __name__ == "__main__":
    test_smc_bullish_bos()
