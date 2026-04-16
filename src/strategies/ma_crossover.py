import pandas as pd
import pandas_ta as ta
from .base import BaseStrategy

class MaCrossoverStrategy(BaseStrategy):
    """
    Moving Average Crossover Strategy.
    
    Logic:
    1. Calculate Fast MA (e.g. 20) and Slow MA (e.g. 50).
    2. Buy Entry: Fast MA crosses ABOVE Slow MA.
    3. Sell Entry: Fast MA crosses BELOW Slow MA.
    """
    
    def __init__(self, config: dict):
        super().__init__(config)
        self.name = "MA_Crossover"
        
        # Parameters
        self.fast_period = config.get('MA_FAST', 20)
        self.slow_period = config.get('MA_SLOW', 50)
        self.ma_type = config.get('MA_TYPE', 'sma') # 'sma' or 'ema'

    def analyze(self, df_5m: pd.DataFrame, df_15m: pd.DataFrame, 
                market_regime: str = "NEUTRAL", daily_bias: str = "NEUTRAL", 
                df_1h: pd.DataFrame = None, df_daily: pd.DataFrame = None) -> dict:
        
        if len(df_5m) < self.slow_period + 5:
             return {'action': 'None', 'reason': 'Insufficient Data'}

        df = df_5m.copy()
        
        # Calculate MAs
        if self.ma_type == 'ema':
            fast_ma = ta.ema(df['Close'], length=self.fast_period)
            slow_ma = ta.ema(df['Close'], length=self.slow_period)
        else:
            fast_ma = ta.sma(df['Close'], length=self.fast_period)
            slow_ma = ta.sma(df['Close'], length=self.slow_period)
            
        if fast_ma is None or slow_ma is None:
            return {'action': 'None', 'reason': 'MA Calculation Failed'}
            
        # Current and Prev
        curr_fast = fast_ma.iloc[-1]
        prev_fast = fast_ma.iloc[-2]
        
        curr_slow = slow_ma.iloc[-1]
        prev_slow = slow_ma.iloc[-2]
        
        # Crossovers
        cross_above = (prev_fast <= prev_slow) and (curr_fast > curr_slow)
        cross_below = (prev_fast >= prev_slow) and (curr_fast < curr_slow)
        
        action = "None"
        reason = []
        
        if cross_above:
            action = "BUY"
            reason.append(f"Fast MA ({self.fast_period}) Crossed Above Slow MA ({self.slow_period})")
        elif cross_below:
            action = "SELL"
            reason.append(f"Fast MA ({self.fast_period}) Crossed Below Slow MA ({self.slow_period})")
            
        close = df.iloc[-1]['Close']
        atr = df.iloc[-1]['ATR'] if 'ATR' in df.columns else (close * 0.01) # fallback
        
        return {
            'action': action,
            'reason': "; ".join(reason),
            'current_price': float(close),
            'atr': float(atr),
            'timestamp': df.index[-1],
            'sl_price': 0.0, 
            'target_r': 2.0, 
            'indicators': {
                'Fast_MA': float(curr_fast),
                'Slow_MA': float(curr_slow)
            }
        }
