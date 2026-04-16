import pandas as pd
import yaml
import sys
import os
import pandas_ta as ta
from datetime import datetime
import logging

# Add src to path
sys.path.append(os.path.join(os.getcwd(), 'src'))

from src.strategies import MaCrossoverStrategy, EmaMacdMfiStrategy, SuperTrendRsiPsarStrategy, SmaPsarStrategy, BollingerRsiStrategy, MacdTrendlineStrategy
from src.strategy import StrategyEngine

# Setup Mock Data
def create_mock_data():
    dates = pd.date_range(end=datetime.now(), periods=200, freq='5min')
    df = pd.DataFrame(index=dates)
    df['Open'] = 100.0
    df['High'] = 105.0
    df['Low'] = 95.0
    df['Close'] = 100.0 + (pd.Series(range(200)).values * 0.1) # Uptrend using numpy array assignment
    df['Volume'] = 1000
    df['ATR'] = 1.0
    
    # Induce signals
    # 1. MA Crossover: Fast > Slow (Data is uptrending so this should happen naturally)
    # 2. EMA/MACD/MFI: Ensure conditions met
    
    return df

def test_strategy(strategy_name, strategy_cls, config={}):
    print(f"\nTesting {strategy_name}...")
    
    # Config
    full_config = {'strategy_mode': strategy_name, **config}
    strategy = strategy_cls(full_config)
    
    # Data
    df_5m = create_mock_data()
    # Create artificial crossover for MA
    if strategy_name == 'MA_CROSSOVER':
        # Drop price at end to cause cross down? Or start low end high for cross up
        pass 
        
    df_15m = df_5m.resample('15min').agg({'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'}).dropna()
    
    # Run Analyze
    try:
        signal = strategy.analyze(df_5m, df_15m)
        print(f"Result: {signal['action']}")
        print(f"Reason: {signal['reason']}")
        print(f"Indicators: {signal['indicators']}")
    except Exception as e:
        print(f"FAILED: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # Test MA Crossover
    test_strategy('MA_CROSSOVER', MaCrossoverStrategy, {'MA_FAST': 10, 'MA_SLOW': 30})
    
    # Test EMA MACD MFI
    test_strategy('EMA_MACD_MFI', EmaMacdMfiStrategy, {})
    
    # Test SuperTrend RSI PSAR
    test_strategy('SUPERTREND_RSI_PSAR', SuperTrendRsiPsarStrategy, {})
    
    # Test SMA PSAR
    test_strategy('SMA_PSAR', SmaPsarStrategy, {'SMA_FAST': 20, 'SMA_SLOW': 40})
    
    # Test Bollinger RSI
    test_strategy('BOLLINGER_RSI', BollingerRsiStrategy, {})
    
    # Test MACD Trendline
    test_strategy('MACD_TRENDLINE', MacdTrendlineStrategy, {})
