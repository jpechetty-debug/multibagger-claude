
import pandas as pd
import logging
from .indicators import calculate_daily_levels

class LevelStrategy:
    """
    Level-to-Level Trading Strategy.
    Enters on reversals at Key Levels (PDH, PDL, VWAP).
    """
    def __init__(self, config):
        self.logger = logging.getLogger("IntradaySignals.LevelStrategy")
        self.config = config
        self.level_buffer = 0.002 # 0.2% tolerance for "touching" a level
        self.target_r = 2.0
        
    def analyze(self, df_intraday: pd.DataFrame, df_daily: pd.DataFrame) -> dict:
        signal = {
            "action": "None",
            "reason": "",
            "stop_loss": 0.0,
            "target": 0.0,
            "current_price": 0.0
        }
        
        if df_intraday.empty or len(df_intraday) < 5:
            return signal
            
        # Get Levels
        levels = calculate_daily_levels(df_daily)
        if not levels:
            return signal
            
        pdh = levels['PDH']
        pdl = levels['PDL']
        
        # Get Intraday Data
        last_bar = df_intraday.iloc[-1]
        close = last_bar['Close']
        open_p = last_bar['Open']
        high = last_bar['High']
        low = last_bar['Low']
        vwap = last_bar.get('VWAP', 0)
        
        # Patterns (Calculated in indicators.py)
        is_hammer = last_bar.get('Pattern_Hammer', False)
        is_shooting_star = last_bar.get('Pattern_Shooting_Star', False)
        bullish_engulfing = last_bar.get('Pattern_Bullish_Engulfing', False)
        bearish_engulfing = last_bar.get('Pattern_Bearish_Engulfing', False)
        
        signal['current_price'] = close
        
        # Logic: Reversal at Support (PDL)
        # Price is near PDL (within buffer) AND Bullish Pattern
        dist_pdl = abs(low - pdl) / pdl
        if dist_pdl < self.level_buffer and (is_hammer or bullish_engulfing):
            signal['action'] = "BUY"
            signal['reason'] = f"Level Buy: Reversal at PDL ({pdl:.2f}) | Pattern: {'Hammer' if is_hammer else 'Engulfing'}"
            signal['stop_loss'] = low - (low * 0.001) # Just below candle low
            signal['target'] = vwap if vwap > close else pdh # Target VWAP or PDH
            return signal
            
        # Logic: Reversal at Resistance (PDH)
        dist_pdh = abs(high - pdh) / pdh
        if dist_pdh < self.level_buffer and (is_shooting_star or bearish_engulfing):
            signal['action'] = "SELL"
            signal['reason'] = f"Level Sell: Reversal at PDH ({pdh:.2f}) | Pattern: {'Shooting Star' if is_shooting_star else 'Engulfing'}"
            signal['stop_loss'] = high + (high * 0.001)
            signal['target'] = vwap if vwap < close else pdl
            return signal
            
        # Logic: VWAP Bounce (Trend Continuation)
        # If trend is up (Close > PDH?), buy at VWAP?
        # Video focused on PDH/PDL. We'll stick to that for now.
        
        return signal
