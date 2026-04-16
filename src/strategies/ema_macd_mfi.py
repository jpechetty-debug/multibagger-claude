import pandas as pd
import pandas_ta as ta
from .base import BaseStrategy

class EmaMacdMfiStrategy(BaseStrategy):
    """
    50 EMA, MACD, and MFI Strategy.
    
    Logic:
    1. Trend Filter: 50 EMA. 
       - Bullish if Close > 50 EMA.
       - Bearish if Close < 50 EMA.
    2. Momentum: MACD (12, 26, 9).
       - Bullish if MACD Line > Signal Line.
       - Bearish if MACD Line < Signal Line.
    3. Volume/Flow: MFI (14).
       - Buy Condition: MFI < 80 (Not Overbought) - loosen constraint? Or maybe MFI > 50?
       - Strict User Request: "50 EMA, MACD and MFI Strategy".
       - Common Interpretation:
         - Buy: Price > 50 EMA, MACD > Signal, MFI > 40 (buying pressure) and < 80.
         - Sell: Price < 50 EMA, MACD < Signal, MFI < 60 (selling pressure) and > 20.
    """
    
    def __init__(self, config: dict):
        super().__init__(config)
        self.name = "EMA_MACD_MFI"
        
        self.ema_period = 50
        self.macd_fast = 12
        self.macd_slow = 26
        self.macd_signal = 9
        self.mfi_period = 14
        
        self.mfi_overbought = 80
        self.mfi_oversold = 20

    def analyze(self, df_5m: pd.DataFrame, df_15m: pd.DataFrame, 
                market_regime: str = "NEUTRAL", daily_bias: str = "NEUTRAL", 
                df_1h: pd.DataFrame = None, df_daily: pd.DataFrame = None) -> dict:
        
        if len(df_5m) < 60:
             return {'action': 'None', 'reason': 'Insufficient Data'}

        df = df_5m.copy()
        
        # 1. EMA 50
        ema_50 = ta.ema(df['Close'], length=self.ema_period)
        
        # 2. MACD
        macd_df = ta.macd(df['Close'], fast=self.macd_fast, slow=self.macd_slow, signal=self.macd_signal)
        # MACD_12_26_9, MACDh_12_26_9 (Hist), MACDs_12_26_9 (Signal)
        
        # 3. MFI
        mfi = ta.mfi(df['High'], df['Low'], df['Close'], df['Volume'], length=self.mfi_period)
        
        if ema_50 is None or macd_df is None or mfi is None:
            return {'action': 'None', 'reason': 'Indicator Calculation Failed'}
            
        # Get Latest Values
        curr_close = df.iloc[-1]['Close']
        curr_ema = ema_50.iloc[-1]
        
        macd_col = [c for c in macd_df.columns if c.startswith('MACD_')][0]
        sig_col = [c for c in macd_df.columns if c.startswith('MACDs')][0]
        
        curr_macd = macd_df.iloc[-1][macd_col]
        curr_sig = macd_df.iloc[-1][sig_col]
        
        curr_mfi = mfi.iloc[-1]
        
        action = "None"
        reason = []
        
        # Buy Logic
        # 1. Trend: Close > EMA 50
        # 2. Momentum: MACD > Signal
        # 3. MFI: Not Overbought (< 80) and showing strength (> 40?) -> Let's use < 80 as safety
        if (curr_close > curr_ema) and (curr_macd > curr_sig) and (curr_mfi < self.mfi_overbought):
            # Check for fresh crossover of MACD for better entry timing? 
            # Or just continuous condition? User asked for strategy, usually means entry signals.
            # Let's check if MACD crossed recently or just condition holds. 
            # For backtest safety, let's require MACD Cross OR Price crossing EMA recently.
            # Simpler: Just check conditions.
            
            # To avoid spamming buys, check previous candle did NOT meet criteria?
            # Or simplified: if Previous MACD < Previous Signal (Crossover)
            prev_macd = macd_df.iloc[-2][macd_col]
            prev_sig = macd_df.iloc[-2][sig_col]
            
            if prev_macd <= prev_sig: # Fresh MACD Crossover
                action = "BUY"
                reason.append("Close > 50EMA + MACD Bullish Cross + MFI Safe")
        
        # Sell Logic
        elif (curr_close < curr_ema) and (curr_macd < curr_sig) and (curr_mfi > self.mfi_oversold):
            prev_macd = macd_df.iloc[-2][macd_col]
            prev_sig = macd_df.iloc[-2][sig_col]
            
            if prev_macd >= prev_sig: # Fresh MACD Crossover Down
                action = "SELL"
                reason.append("Close < 50EMA + MACD Bearish Cross + MFI Safe")
                
        atr = df.iloc[-1]['ATR'] if 'ATR' in df.columns else (curr_close * 0.01)
        
        return {
            'action': action,
            'reason': "; ".join(reason),
            'current_price': float(curr_close),
            'atr': float(atr),
            'timestamp': df.index[-1],
            'sl_price': 0.0, 
            'target_r': 2.0, 
            'indicators': {
                'EMA_50': float(curr_ema),
                'MACD': float(curr_macd),
                'MFI': float(curr_mfi)
            }
        }
