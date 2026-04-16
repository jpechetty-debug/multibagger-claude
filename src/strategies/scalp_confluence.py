from .base import BaseStrategy
import pandas as pd
import pandas_ta as ta

class ScalpConfluenceStrategy(BaseStrategy):
    """
    Video Strategy: Scalp Confluence (Rhythm & Flow)
    Source: https://www.youtube.com/watch?v=9xiqt5Dg0Ds
    
    Components:
    1. SuperTrend (Trend Direction)
    2. MACD (Momentum Trigger)
    3. Bollinger Bands Midline (SMA 20) (Value/Breakout)
    
    Logic:
    - Buy: SuperTrend is BULLISH (Close > ST) AND Price > BB Midline AND MACD Histogram > 0 (or spread positive).
    - Sell: SuperTrend is BEARISH (Close < ST) AND Price < BB Midline AND MACD Histogram < 0.
    """
    def __init__(self, config: dict):
        super().__init__(config)
        self.name = "SCALP_CONFLUENCE"
        self.st_length = 10
        self.st_multiplier = 3.0
        self.bb_length = 20
        self.bb_std = 2.0
        
    def analyze(self, df_5m: pd.DataFrame, df_15m: pd.DataFrame, 
                market_regime: str = "NEUTRAL", daily_bias: str = "NEUTRAL", 
                df_1h: pd.DataFrame = None, df_daily: pd.DataFrame = None) -> dict:
        
        if len(df_5m) < 50:
             return {'action': 'None', 'reason': 'Insufficient Data'}

        df = df_5m.copy()
        
        # 1. SuperTrend
        st = ta.supertrend(df['High'], df['Low'], df['Close'], length=self.st_length, multiplier=self.st_multiplier)
        if st is None: return {'action': 'None', 'reason': 'Indicator Error'}
        
        # ST Columns are usually SUPERT_7_3.0, SUPERTd_7_3.0 etc.
        # Let's find columns dynamically
        st_val_col = [c for c in st.columns if c.startswith('SUPERT_')][0]
        st_dir_col = [c for c in st.columns if c.startswith('SUPERTd_')][0] # 1 = Bullish, -1 = Bearish
        
        df['st_dir'] = st[st_dir_col]
        
        # 2. Bollinger Bands
        bb = ta.bbands(df['Close'], length=self.bb_length, std=self.bb_std)
        bbm_col = [c for c in bb.columns if c.startswith('BBM')][0]
        df['bbm'] = bb[bbm_col]
        
        # 3. MACD
        macd = ta.macd(df['Close'])
        macd_col = [c for c in macd.columns if c.startswith('MACD_')][0]
        signal_col = [c for c in macd.columns if c.startswith('MACDs_')][0]
        hist_col = [c for c in macd.columns if c.startswith('MACDh_')][0]
        
        df['macd_hist'] = macd[hist_col]
        
        # Analysis
        curr = df.iloc[-1]
        
        action = "None"
        reason = []
        
        # BUY Logic
        # 1. SuperTrend Bullish (1)
        # 2. Close > BB Midline
        # 3. MACD Hist > 0 (Momentum Up)
        if (curr['st_dir'] == 1) and (curr['Close'] > curr['bbm']) and (curr['macd_hist'] > 0):
            # Optional: Check if crossover JUST happened for freshness?
            # Video implies flow, so current state is key.
            action = "BUY"
            reason.append("SuperTrend Bullish + Above BB Mid + MACD Pos")
            
        # SELL Logic
        # 1. SuperTrend Bearish (-1)
        # 2. Close < BB Midline
        # 3. MACD Hist < 0
        elif (curr['st_dir'] == -1) and (curr['Close'] < curr['bbm']) and (curr['macd_hist'] < 0):
            action = "SELL"
            reason.append("SuperTrend Bearish + Below BB Mid + MACD Neg")
            
        atr = df.iloc[-1]['ATR'] if 'ATR' in df.columns else (curr['Close'] * 0.01)

        return {
            'action': action,
            'reason': "; ".join(reason),
            'current_price': curr['Close'],
            'atr': atr,
            'timestamp': df.index[-1],
            'sl_price': 0.0, # Use Default Risk Engine (1.5 ATR)
            'indicators': {} 
        }
