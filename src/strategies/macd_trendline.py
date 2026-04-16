import pandas as pd
import pandas_ta as ta
from .base import BaseStrategy
import numpy as np

class MacdTrendlineStrategy(BaseStrategy):
    """
    MACD Trendline Trading Strategy.
    
    Logic:
    "Pattern on Indicator" Strategy.
    1. Calculate MACD line.
    2. Identify Pivot Highs/Lows on the MACD Line (not Price).
    3. Buy: MACD Line breaks ABOVE a recent Pivot High (Resistance on MACD).
    4. Sell: MACD Line breaks BELOW a recent Pivot Low (Support on MACD).
    
    This simulates "Trendline Breakout" on the indicator itself.
    """
    
    def __init__(self, config: dict):
        super().__init__(config)
        self.name = "MACD_TRENDLINE"
        
        self.fast = 12
        self.slow = 26
        self.signal = 9
        
    def analyze(self, df_5m: pd.DataFrame, df_15m: pd.DataFrame, 
                market_regime: str = "NEUTRAL", daily_bias: str = "NEUTRAL", 
                df_1h: pd.DataFrame = None, df_daily: pd.DataFrame = None) -> dict:
        
        if len(df_5m) < 60:
             return {'action': 'None', 'reason': 'Insufficient Data'}

        df = df_5m.copy()
        
        # MACD
        macd_df = ta.macd(df['Close'], fast=self.fast, slow=self.slow, signal=self.signal)
        if macd_df is None:
             return {'action': 'None', 'reason': 'Indicator Calculation Failed'}
             
        macd_col = [c for c in macd_df.columns if c.startswith('MACD_')][0]
        macd_line = macd_df[macd_col]
        
        # Find Pivots on MACD Line
        # We look back 20 periods to find the highest point that is NOT the current point
        # A simple breakout logic: Current MACD > Max(MACD[1:10]) ?
        # A "Trendline" break usually implies a descending resistance line is broken.
        # Approximation: MACD crosses above Highest MACD of last N bars?
        
        lookback = 15
        
        # Recent MACD series excluding current
        recent_macd = macd_line.iloc[-lookback-1:-1] 
        recent_max = recent_macd.max()
        recent_min = recent_macd.min()
        
        curr_macd = macd_line.iloc[-1]
        prev_macd = macd_line.iloc[-2]
        
        action = "None"
        reason = []
        
        # Buy: Bullish Breakout
        # Previous MACD was below recent Max, Current MACD is above.
        # implies breaking a resistance level on the indicator.
        if (prev_macd <= recent_max) and (curr_macd > recent_max):
            # Additional trend filter? User said MACD Trendline.
            # Usually implies divergences too, but let's stick to Breakout.
            # To be safe, check if MACD is above Signal line too?
            # Let's trust pure MACD price action.
            action = "BUY"
            reason.append("MACD Line Breakout above recent Pivot High")
            
        elif (prev_macd >= recent_min) and (curr_macd < recent_min):
            action = "SELL"
            reason.append("MACD Line Breakdown below recent Pivot Low")
            
        close = df.iloc[-1]['Close']
        atr = df.iloc[-1]['ATR'] if 'ATR' in df.columns else (close * 0.01)
        
        return {
            'action': action,
            'reason': "; ".join(reason),
            'current_price': float(close),
            'atr': float(atr),
            'timestamp': df.index[-1],
            'sl_price': 0.0, 
            'target_r': 2.0, 
            'indicators': {
                'MACD': float(curr_macd),
                'MACD_RecentMax': float(recent_max)
            }
        }
