
import pandas as pd
import pandas_ta as ta
import logging

class RelativeVolumeStrategy:
    """
    Implements the "RV Strategy" (Relative Volume Breakout).
    Logic:
    1. Consolidation (Optional): Stock has been ranging.
    2. Breakout: Price crosses above Resistance (e.g., 20-day High).
    3. RVOL: Volume is significantly higher than average (e.g., > 2.0x).
    """

    def __init__(self, config):
        self.logger = logging.getLogger("IntradaySignals.RVStrategy")
        self.config = config
        self.rvol_threshold = config.get("swing_trading", {}).get("strategy_settings", {}).get("rvol_threshold", 2.0)
        self.lookback = config.get("swing_trading", {}).get("strategy_settings", {}).get("breakout_lookback", 20)

    def analyze(self, df: pd.DataFrame) -> dict:
        """
        Analyzes the dataframe for RVOL Breakout Setup.
        """
        signal = {
            "action": "None",
            "reason": "",
            "stop_loss": 0.0,
            "target": 0.0,
            "atr": 0.0,
            "current_price": 0.0
        }

        if df.empty or len(df) < 50:
            return signal

        # 1. Calculate Indicators
        # RVOL
        vol_sma = ta.sma(df['Volume'], length=20)
        if vol_sma is None or vol_sma.empty: return signal
        
        # Avoid division by zero
        vol_sma = vol_sma.replace(0, 1) 
        rvol = df['Volume'] / vol_sma
        
        # ATR
        atr = ta.atr(df['High'], df['Low'], df['Close'], length=14)
        if atr is None: return signal

        # Donchian Channel (Breakout Levels)
        # rolling max of high (excluding current bar usually, but for breakout we check current close vs prev max)
        # shift(1) to get "Previous N days High"
        rolling_high = df['High'].rolling(self.lookback).max().shift(1)
        
        # 2. Check Conditions (Latest Bar)
        current_bar = df.iloc[-1]
        prev_high = rolling_high.iloc[-1]
        current_rvol = rvol.iloc[-1]
        current_atr = atr.iloc[-1]
        
        signal['current_price'] = current_bar['Close']
        signal['atr'] = current_atr
        
        # Condition A: Breakout (Close > Previous N-day High)
        breakout = current_bar['Close'] > prev_high
        
        # Condition B: High Relative Volume
        high_rvol = current_rvol > self.rvol_threshold
        
        # Condition C: Bullish Candle (Close > Open)
        bullish = current_bar['Close'] > current_bar['Open']
        
        if breakout and high_rvol and bullish:
            signal['action'] = "BUY"
            signal['reason'] = f"RV Breakout: Close {current_bar['Close']:.2f} > {prev_high:.2f} & RVOL {current_rvol:.1f}x"
            
            # Stop Loss: Low of the breakout candle or ATR based
            # Strategy: Low of candle is safer for breakout failure
            signal['sl_price'] = current_bar['Low'] - (current_atr * 0.5) 
            
            # Target: 2R
            risk = current_bar['Close'] - signal['sl_price']
            signal['tp_price'] = current_bar['Close'] + (risk * 2.0)
            signal['target_r'] = 2.0
            
            self.logger.info(f"RV Signal Found: {signal['reason']}")

        return signal
