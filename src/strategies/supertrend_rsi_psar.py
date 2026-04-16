import pandas as pd
import pandas_ta as ta
from .base import BaseStrategy

class SuperTrendRsiPsarStrategy(BaseStrategy):
    """
    SuperTrend (7,3), (7,4) + RSI + Parabolic SAR Strategy.
    
    Logic:
    1. SuperTrend 1 (7, 3) -> Trend Direction.
    2. SuperTrend 2 (7, 4) -> Trend Confirmation (less noise).
    3. RSI (14) -> Momentum. Buy > 50, Sell < 50 (Trend Following).
    4. Parabolic SAR -> Trailing Stop / Confirmation.
       - Buy: Price > SAR.
       - Sell: Price < SAR.
       
    Entry:
    - ALL conditions must align.
    - Buy: ST1 Open Long, ST2 Open Long, RSI > 50, Price > SAR.
    - Sell: ST1 Open Short, ST2 Open Short, RSI < 50, Price < SAR.
    """
    
    def __init__(self, config: dict):
        super().__init__(config)
        self.name = "SuperTrend_RSI_PSAR"
        
        # SuperTrend Params
        self.st1_length = 7
        self.st1_multiplier = 3
        self.st2_length = 7
        self.st2_multiplier = 4
        
        # RSI Params
        self.rsi_length = 14
        
        # SAR Params
        self.sar_af = 0.02
        self.sar_max = 0.2

    def analyze(self, df_5m: pd.DataFrame, df_15m: pd.DataFrame, 
                market_regime: str = "NEUTRAL", daily_bias: str = "NEUTRAL", 
                df_1h: pd.DataFrame = None, df_daily: pd.DataFrame = None) -> dict:
        
        if len(df_5m) < 50:
             return {'action': 'None', 'reason': 'Insufficient Data'}

        df = df_5m.copy()
        
        # 1. SuperTrends
        st1 = ta.supertrend(df['High'], df['Low'], df['Close'], length=self.st1_length, multiplier=self.st1_multiplier)
        st2 = ta.supertrend(df['High'], df['Low'], df['Close'], length=self.st2_length, multiplier=self.st2_multiplier)
        
        # 2. RSI
        rsi = ta.rsi(df['Close'], length=self.rsi_length)
        
        # 3. PSAR
        # pandas-ta psar returns columns like PSARl_0.02_0.2, PSARs_0.02_0.2... depending on implementation
        # Or just one column combined? -> It actually returns 'PSARl...' (long) and 'PSARs...' (short) often separate NaNs
        # Actually in recent pandas-ta, it returns 'PSARl...' (Long Support) and 'PSARs...' (Short Resistance)
        # We need to coalesce them to find the active SAR value.
        psar_df = ta.psar(df['High'], df['Low'], df['Close'], af0=self.sar_af, af=self.sar_af, max_af=self.sar_max)
        
        if st1 is None or st2 is None or rsi is None or psar_df is None:
             return {'action': 'None', 'reason': 'Indicator Calculation Failed'}
             
        # Identify Columns
        # Supertrend returns [SUPERT_..., SUPERTd_..., SUPERTl_..., SUPERTs_...]
        # We care about trend direction 'SUPERTd_...' (1 = Buy, -1 = Sell)
        st1_dir_col = [c for c in st1.columns if c.startswith('SUPERTd_')][0]
        st2_dir_col = [c for c in st2.columns if c.startswith('SUPERTd_')][0]
        
        curr_st1 = st1.iloc[-1][st1_dir_col]
        curr_st2 = st2.iloc[-1][st2_dir_col]
        
        curr_rsi = rsi.iloc[-1]
        
        # PSAR Logic
        # Combine PSARl and PSARs
        # If PSARl is not NaN, that's the SAR (below price).
        # If PSARs is not NaN, that's the SAR (above price).
        psar_long_col = [c for c in psar_df.columns if c.startswith('PSARl_')][0]
        psar_short_col = [c for c in psar_df.columns if c.startswith('PSARs_')][0]
        
        curr_psar_l = psar_df.iloc[-1][psar_long_col]
        curr_psar_s = psar_df.iloc[-1][psar_short_col]
        
        # Determine active SAR
        if pd.notna(curr_psar_l):
            curr_sar = curr_psar_l
            sar_bullish = True
        else:
            curr_sar = curr_psar_s
            sar_bullish = False
            
        action = "None"
        reason = []
        
        # BUY Logic
        # ST1 = 1 (Bullish), ST2 = 1 (Bullish), RSI > 50, SAR Bullish (Price > SAR)
        if (curr_st1 == 1) and (curr_st2 == 1) and (curr_rsi > 50) and sar_bullish:
            # Check Trigger (fresh signal)
            # Either ST1 or ST2 flipped recently? Or RSI crossed 50?
            # Let's check if prev ST1 OR prev ST2 was Bearish (-1)
            prev_st1 = st1.iloc[-2][st1_dir_col]
            prev_st2 = st2.iloc[-2][st2_dir_col]
            
            if (prev_st1 == -1) or (prev_st2 == -1):
                action = "BUY"
                reason.append("SuperTrend Double Bullish Flip + RSI > 50 + PSAR Bullish")
                
        # SELL Logic
        elif (curr_st1 == -1) and (curr_st2 == -1) and (curr_rsi < 50) and (not sar_bullish):
            prev_st1 = st1.iloc[-2][st1_dir_col]
            prev_st2 = st2.iloc[-2][st2_dir_col]
            
            if (prev_st1 == 1) or (prev_st2 == 1):
                action = "SELL"
                reason.append("SuperTrend Double Bearish Flip + RSI < 50 + PSAR Bearish")
                
        close = df.iloc[-1]['Close']
        atr = df.iloc[-1]['ATR'] if 'ATR' in df.columns else (close * 0.01)
        
        return {
            'action': action,
            'reason': "; ".join(reason),
            'current_price': float(close),
            'atr': float(atr),
            'timestamp': df.index[-1],
            'sl_price': float(curr_sar) if pd.notna(curr_sar) else 0.0, # Use PSAR as SL
            'target_r': 2.0, 
            'indicators': {
                'ST1': int(curr_st1),
                'ST2': int(curr_st2),
                'RSI': float(curr_rsi),
                'PSAR': float(curr_sar)
            }
        }
