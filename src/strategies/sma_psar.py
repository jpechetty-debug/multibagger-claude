import pandas as pd
import pandas_ta as ta
from .base import BaseStrategy

class SmaPsarStrategy(BaseStrategy):
    """
    20 & 40 Simple Moving Average and Parabolic SAR Strategy.
    
    Logic:
    1. Trend Identification: 20 SMA > 40 SMA (Bullish), 20 < 40 (Bearish).
    2. Entry Trigger: Parabolic SAR Flip.
       - Buy: Trend is Bullish AND Price > PSAR (fresh flip preferred).
       - Sell: Trend is Bearish AND Price < PSAR.
    """
    
    def __init__(self, config: dict):
        super().__init__(config)
        self.name = "SMA_PSAR"
        
        self.sma_fast = 20
        self.sma_slow = 40
        self.psar_af = 0.02
        self.psar_max = 0.2

    def analyze(self, df_5m: pd.DataFrame, df_15m: pd.DataFrame, 
                market_regime: str = "NEUTRAL", daily_bias: str = "NEUTRAL", 
                df_1h: pd.DataFrame = None, df_daily: pd.DataFrame = None) -> dict:
        
        if len(df_5m) < 50:
             return {'action': 'None', 'reason': 'Insufficient Data'}

        df = df_5m.copy()
        
        # Indicators
        sma20 = ta.sma(df['Close'], length=self.sma_fast)
        sma40 = ta.sma(df['Close'], length=self.sma_slow)
        psar_df = ta.psar(df['High'], df['Low'], df['Close'], af0=self.psar_af, af=self.psar_af, max_af=self.psar_max)
        
        if sma20 is None or sma40 is None or psar_df is None:
             return {'action': 'None', 'reason': 'Indicator Calculation Failed'}
             
        # PSAR Extraction
        psar_long_col = [c for c in psar_df.columns if c.startswith('PSARl_')][0]
        psar_short_col = [c for c in psar_df.columns if c.startswith('PSARs_')][0]
        
        curr_psar_l = psar_df.iloc[-1][psar_long_col]
        
        # Logic
        curr_s20 = sma20.iloc[-1]
        curr_s40 = sma40.iloc[-1]
        
        is_uptrend = curr_s20 > curr_s40
        is_downtrend = curr_s20 < curr_s40
        
        psar_bullish = pd.notna(curr_psar_l) # Price > PSAR
        
        # Check previous candle for Flip
        prev_psar_l = psar_df.iloc[-2][psar_long_col]
        psar_flipped_bullish = pd.isna(prev_psar_l) and pd.notna(curr_psar_l)
        
        prev_psar_s = psar_df.iloc[-2][psar_short_col]
        # Current PSAR Short (active) means psar_l is NaN
        psar_flipped_bearish = pd.isna(prev_psar_s) and pd.isna(curr_psar_l) 
        
        action = "None"
        reason = []
        
        if is_uptrend and psar_bullish:
            # We can enter on Trend Continuation or Fresh Flip
            # Strategy: Enter if Trend is Up and PSAR just flipped Bullish OR Price dips near PSAR?
            # User said "Strategy", usually means standard entry.
            # Let's enforce Fresh Flip OR strong momentum. 
            # Sticking to Fresh Flip + Trend alignment is safer for robots.
            if psar_flipped_bullish:
                action = "BUY"
                reason.append("20SMA > 40SMA & PSAR Bullish Flip")
                
        elif is_downtrend and (not psar_bullish):
            if psar_flipped_bearish:
                action = "SELL"
                reason.append("20SMA < 40SMA & PSAR Bearish Flip")
                
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
                'SMA20': float(curr_s20),
                'SMA40': float(curr_s40),
                'PSAR_Bullish': bool(psar_bullish)
            }
        }
