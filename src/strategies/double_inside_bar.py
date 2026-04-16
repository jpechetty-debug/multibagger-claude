from .base import BaseStrategy
import pandas as pd
import pandas_ta as ta

class DoubleInsideBarStrategy(BaseStrategy):
    """
    Video Strategy: Double Inside Bar (Volatility Contraction)
    Source: https://www.youtube.com/watch?v=vcA29tR92F0
    
    Logic:
    1. Mother Bar (Index -2)
    2. Inside Bar 1 (Index -1): Contained within Mother Bar.
    3. Inside Bar 2 (Index 0): Contained within Inside Bar 1 (Double Compression).
    
    Entry:
    - Stop Entry at High/Low of Inside Bar 2.
    
    This strategy returns a 'pending' signal because we need to wait for the breakout.
    The current implementation will signal BUY/SELL if the CURRENT price breaks the level,
    or we can return a STOP_LIMIT order request.
    """
    def __init__(self, config: dict):
        super().__init__(config)
        self.name = "DOUBLE_INSIDE_BAR"
        self.target_r = 2.0 # Volatility expansion usually runs hard
        
    def analyze(self, df_5m: pd.DataFrame, df_15m: pd.DataFrame, 
                market_regime: str = "NEUTRAL", daily_bias: str = "NEUTRAL", 
                df_1h: pd.DataFrame = None, df_daily: pd.DataFrame = None) -> dict:
        
        # We need at least 3 bars
        if len(df_15m) < 3: # Preference for higher timeframe (15m/1h) as per video
             return {'action': 'None', 'reason': 'Insufficient Data'}

        # Video recommends higher timeframes. Let's use 15m as primary for this pattern.
        df = df_15m.copy()
        
        # Get last 3 completed bars (excluding current forming bar if possible, 
        # but in live trading -1 is the last COMPLETED bar usually if we use resample properly.
        # However, to detect the pattern forming NOW:
        # Mother = -3, Child = -2, Grandchild = -1 (Last Closed Candle)
        
        # Let's assume we are looking for the pattern to be completed on the LAST CLOSED BAR.
        # So we look at -3, -2, -1.
        
        b1 = df.iloc[-3] # Mother
        b2 = df.iloc[-2] # Inside 1
        b3 = df.iloc[-1] # Inside 2 (Signal Bar)
        
        action = "None"
        reason = []
        stop_entry_price = 0.0
        sl_price = 0.0
        
        # Logic: 
        # Bar 2 Inside Bar 1?
        # Bar 1 high >= Bar 2 high AND Bar 1 low <= Bar 2 low
        is_b2_inside = (b1['High'] >= b2['High']) and (b1['Low'] <= b2['Low'])
        
        # Bar 3 Inside Bar 2?
        # Bar 2 high >= Bar 3 high AND Bar 2 low <= Bar 3 low
        is_b3_inside = (b2['High'] >= b3['High']) and (b2['Low'] <= b3['Low'])
        
        if is_b2_inside and is_b3_inside:
            # Pattern Found!
            # Direction? 
            # The video says breakout can be either way.
            # But usually we follow the trend of Mother Bar or recent EMA.
            
            # Filter: Check EMA 50 Trend
            ema_50 = ta.ema(df['Close'], length=50).iloc[-1]
            
            if b3['Close'] > ema_50:
                # Bullish Bias -> Place Buy Stop at B3 High
                action = "BUY"
                stop_entry_price = b3['High'] + (b3['High'] * 0.0005) # Buffer
                sl_price = b3['Low']
                reason.append("Double Inside Bar (Bullish)")
                
            elif b3['Close'] < ema_50:
                # Bearish Bias -> Place Sell Stop at B3 Low
                action = "SELL"
                stop_entry_price = b3['Low'] - (b3['Low'] * 0.0005) # Buffer
                sl_price = b3['High']
                reason.append("Double Inside Bar (Bearish)")
        
        atr = df.iloc[-1]['ATR'] if 'ATR' in df.columns else (df.iloc[-1]['Close'] * 0.01)

        return {
            'action': action,
            'reason': "; ".join(reason),
            'current_price': df.iloc[-1]['Close'],
            'atr': atr,
            'timestamp': df.index[-1],
            'sl_price': sl_price,
            'target_r': self.target_r,
            'stop_entry_price': stop_entry_price, # Special field for Pending Orders
            'indicators': {} 
        }
