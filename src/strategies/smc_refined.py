import pandas as pd
import numpy as np
import pandas_ta as ta
from .base import BaseStrategy
from ..smart_money import find_swings, detect_order_blocks, detect_imbalance

class SmcRefinedStrategy(BaseStrategy):
    """
    SMC Refined Strategy (Video Logic):
    1. Identify Market Shift (BOS).
    2. Identify the Demand/Supply Zone (Order Block) that originated the move.
    3. Entry on Pullback to that Zone.
    """
    
    def __init__(self, config: dict):
        super().__init__(config)
        self.name = "SMC_REFINED"
        self.swing_length = 5

    def analyze(self, df_5m: pd.DataFrame, df_15m: pd.DataFrame, 
                market_regime: str = "NEUTRAL", daily_bias: str = "NEUTRAL", 
                df_1h: pd.DataFrame = None, df_daily: pd.DataFrame = None) -> dict:
        
        if len(df_5m) < 100:
             return {'action': 'None', 'reason': 'Insufficient Data'}

        # We need to find the *last* valid BOS event in history to define our current "Trading Range"
        # Since 'detect_structure_break' only checks the last candle, we need to scan manually or be clever.
        
        df = df_5m.copy()
        
        # 1. Calculate Swings
        df = find_swings(df, length=self.swing_length)
        
        # 2. Find Swing Points
        swings_high = df[df['Swing_High']]
        swings_low = df[df['Swing_Low']]
        
        if len(swings_high) < 2 or len(swings_low) < 2:
             return {'action': 'None', 'reason': 'No Structure'}
             
        # 3. Identify the LAST CONFIRMED BOS
        # We iterate backwards from the current bar to find where a Close broke a previous Swing.
        # This is expensive to do every bar in Python loops.
        # Approximation: Check the last 50 bars for a break event.
        
        current_close = df.iloc[-1]['Close']
        current_idx = df.index[-1]
        
        action = "None"
        reason = []
        target_r = 3.0
        sl_price = 0.0
        
        # Let's find the most recent structure.
        # Bullish Scenario:
        # Last major event was a Break of Structure UP (Close > Prev Swing High).
        # We are now waiting for price to drop into the OB that created that BOS.
        
        # Get last 2 Swing Highs relative to NOW
        # Note: Swing Highs are marked at index - 2.
        
        # Fast Logic:
        # Get the highest Swing High in the last N bars... 
        # Better: Filter swings that happened before now.
        
        recent_highs = swings_high.tail(5) # Last 5 Swing Highs
        recent_lows = swings_low.tail(5)   # Last 5 Swing Lows
        
        # Detect Bullish Trend State:
        # Check if the Latest Swing High is higher than the one before?
        # A BOS happens when Price closes above a Swing High.
        
        # Find the most recent candle that closed above a Swing High.
        # This defines the "Market Shift".
        
        # Let's look at the movement from the Last Swing Low.
        last_swing_low_row = recent_lows.iloc[-1]
        last_swing_low_idx = last_swing_low_row.name
        last_swing_low_price = last_swing_low_row['Swing_Low_Price']
        
        # Did this Low lead to a Break of Structure?
        # i.e. Did price go from this Low to break a PREVIOUS High?
        
        # Check Highs BEFORE this Low.
        highs_before_low = swings_high[swings_high.index < last_swing_low_idx]
        if not highs_before_low.empty:
            prev_swing_high_price = highs_before_low.iloc[-1]['Swing_High_Price']
            
            # Check if price AFTER the Low broke this High
            price_after_low = df[df.index > last_swing_low_idx]
            if not price_after_low.empty:
                max_close_after = price_after_low['Close'].max()
                
                if max_close_after > prev_swing_high_price:
                    # VALID BULLISH BOS DETECTED
                    # The Move: Last Swing Low -> New High.
                    # The Demand Zone: The Order Block at the Last Swing Low.
                    
                    # 4. Check for Pullback to Order Block
                    # We expect price to come back near Last Swing Low.
                    
                    # Identify OB at the Low
                    # Simple Proxy: The sequence of candles around the Swing Low.
                    # Specifically the last Down Candle before the explosive Up Move.
                    # Let's scan a small window around the Swing Low index.
                    
                    # Logic: We are BUYING the DIP.
                    # Current Price should be LOWER than the Breakout High, but HIGHER than the Low.
                    
                    # Are we in the zone?
                    # Zone Top ~ Swing Low + ATR? Or find actual OB?
                    # Let's use `detect_order_blocks` logic locally.
                    
                    # Get slice around the low
                    loc_idx = df.index.get_loc(last_swing_low_idx)
                    # Look at candles around there (e.g. -2 to +2 relative to low point?)
                    # The low point itself might be the wick. The OB is explicitly the "Down Candle"
                    
                    # Fallback: Use Fib retracement as "Demand Zone" proxy from video (Golden Zone)?
                    # Video says "Demand Zone". Simplest is the Swing Low area.
                    
                    zone_bottom = last_swing_low_price
                    # Estimate Zone Top as 50% of the leg? No, that's equilibrium.
                    # Estimate Zone Top as Swing Low + 2*ATR (rough OB size)
                    atr = df.iloc[-1].get('ATR', current_close * 0.002) # Default small if missing
                    zone_top = zone_bottom + (atr * 1.5)
                    
                    # Entry Condition:
                    # 1. Price is currently inside [Zone Bottom, Zone Top]
                    # 2. Bullish Rejection (Hammer, Green candle) - optional confirmation
                    
                    if zone_bottom <= df.iloc[-1]['Low'] <= zone_top:
                        # We are in the zone!
                        # Check confirmation: Current candle is Green?
                         if df.iloc[-1]['Close'] > df.iloc[-1]['Open']:
                             action = "BUY"
                             reason.append("Retest of Demand Zone (Origin of BOS)")
                             sl_price = zone_bottom - (atr * 0.5) # Stop below the zone
                             
        # Bearish Scenario (Reverse Logic)
        last_swing_high_row = recent_highs.iloc[-1]
        last_swing_high_idx = last_swing_high_row.name
        last_swing_high_price = last_swing_high_row['Swing_High_Price']
        
        lows_before_high = swings_low[swings_low.index < last_swing_high_idx]
        if not lows_before_high.empty:
            prev_swing_low_price = lows_before_high.iloc[-1]['Swing_Low_Price']
            
            price_after_high = df[df.index > last_swing_high_idx]
            if not price_after_high.empty:
                min_close_after = price_after_high['Close'].min()
                
                if min_close_after < prev_swing_low_price:
                    # VALID BEARISH BOS
                    # Supply Zone: Around Last Swing High
                    atr = df.iloc[-1].get('ATR', current_close * 0.002)
                    zone_top = last_swing_high_price
                    zone_bottom = zone_top - (atr * 1.5)
                    
                    if zone_bottom <= df.iloc[-1]['High'] <= zone_top:
                        if df.iloc[-1]['Close'] < df.iloc[-1]['Open']: # Red candle
                            action = "SELL"
                            reason.append("Retest of Supply Zone (Origin of BOS)")
                            sl_price = zone_top + (atr * 0.5)

        return {
            'action': action,
            'reason': "; ".join(reason),
            'current_price': float(current_close),
            'atr': float(atr if 'atr' in vars() else 0.0),
            'timestamp': df.index[-1],
            'sl_price': float(sl_price),
            'target_r': 3.0, # High R:R for SMC
            'stop_entry_price': 0.0,
            'indicators': {
                'MarketStructure': 'Analyzed'
            }
        }
