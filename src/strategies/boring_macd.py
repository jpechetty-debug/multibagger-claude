import pandas as pd
from .base import BaseStrategy

class ImanRetracementStrategy(BaseStrategy):
    """
    Iman Retracement Strategy (Video 8):
    1. Identify Impulse Candle (Body > 1.5 * ATR).
    2. Entry: Limit order at 25% Retracement Level of that candle.
    3. Target: Re-test of Extrema (High/Low).
    4. Stop: 50% Retracement Level.
    """
    
    def __init__(self, config: dict):
        super().__init__(config)
        self.name = "IMAN_RETRACEMENT"

    def analyze(self, df_5m: pd.DataFrame, df_15m: pd.DataFrame, 
                market_regime: str = "NEUTRAL", daily_bias: str = "NEUTRAL", 
                df_1h: pd.DataFrame = None, df_daily: pd.DataFrame = None) -> dict:
        
        # Ensure sufficient history
        if len(df_5m) < 20:
             return {'action': 'None', 'reason': 'Insufficient Data'}

        last_5m = df_5m.iloc[-1]
        timestamp = last_5m.name
        
        action = "None"
        reason = []
        target_r = 2.0 # Target 2R (Phase 4 Optimization)
        sl_price = 0.0
        stop_entry_price = 0.0
        
        close = last_5m['Close']
        open_p = last_5m['Open']
        high = last_5m['High']
        low = last_5m['Low']
        atr = last_5m.get('ATR', 0)
        
        # 0. Trend Filter (Phase 4): Align with 1H EMA 50
        htf_trend = "NEUTRAL"
        if df_1h is not None and not df_1h.empty:
            if 'EMA_50' in df_1h.columns:
                 ema_1h = df_1h.iloc[-1]['EMA_50']
                 # Check if EMA is valid
                 if ema_1h > 0:
                     if close > ema_1h: htf_trend = "BULLISH"
                     elif close < ema_1h: htf_trend = "BEARISH"

        # We need to check if the PREVIOUS candle was an Impulse, and CURRENT candle hit the entry
        # OR if we are identifying a setup to enter LIMIT?
        # The bot engine processes 'Market' orders mostly. 
        # So we check if Current Price is IN the zone of the Previous Impulse.
        
        prev_candle = df_5m.iloc[-2]
        prev_body = abs(prev_candle['Close'] - prev_candle['Open'])
        
        # 1. Identity Impulse (Previous Candle)
        # Using ATR multiplier for "Large Candle"
        is_impulse = prev_body > (atr * 1.5)
        
        if not is_impulse:
             return {'action': 'None', 'reason': 'No Impulse'}
             
        # 2. Determine Levels
        # Bullish Impulse
        if prev_candle['Close'] > prev_candle['Open']:
            impulse_high = prev_candle['High']
            impulse_low = prev_candle['Low']
            impulse_range = impulse_high - impulse_low
            
            entry_level = impulse_high - (impulse_range * 0.25) # 25% Retracement from High
            stop_level = impulse_high - (impulse_range * 0.50) # 50% Retracement
            target_level = impulse_high # Re-test High
            
            # Check if Current Low touched Entry Level
            # And Close is above Stop Level (valid setup)
            # Check if Current Low touched Entry Level
            # And Close is above Stop Level (valid setup)
            if low <= entry_level and close > stop_level:
                # Trend Filter Check
                if htf_trend == "BULLISH": # Only Buy in Bullish Trend
                    action = "BUY"
                    reason.append(f"Impulse Buy: Retraced to {entry_level:.2f}")
                    sl_price = stop_level
                    target_r = 2.0 
                
        # Bearish Impulse
        elif prev_candle['Close'] < prev_candle['Open']:
            impulse_high = prev_candle['High']
            impulse_low = prev_candle['Low']
            impulse_range = impulse_high - impulse_low
            
            entry_level = impulse_low + (impulse_range * 0.25) # 25% up from Low
            stop_level = impulse_low + (impulse_range * 0.50)
            target_level = impulse_low
            
            if high >= entry_level and close < stop_level:
                # Trend Filter Check
                if htf_trend == "BEARISH": # Only Sell in Bearish Trend
                    action = "SELL"
                    reason.append(f"Impulse Sell: Retraced to {entry_level:.2f}")
                    sl_price = stop_level
                    target_r = 2.0

        # --- Execution ---
        
        if action != "None":
             # Safety checks for SL
             if action == "BUY":
                 if sl_price >= close: sl_price = close * 0.995
             elif action == "SELL":
                 if sl_price <= close: sl_price = close * 1.005

        return {
            'action': action,
            'reason': "; ".join(reason),
            'current_price': float(close),
            'atr': float(atr),
            'timestamp': timestamp,
            'sl_price': float(sl_price),
            'target_r': float(target_r),
            'stop_entry_price': float(stop_entry_price),
            'indicators': {
                'Impulse_Body': float(prev_body),
                'ATR': float(atr)
            }
        }
