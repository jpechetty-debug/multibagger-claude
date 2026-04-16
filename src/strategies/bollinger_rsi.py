import pandas as pd
import pandas_ta as ta
from .base import BaseStrategy

class BollingerRsiStrategy(BaseStrategy):
    """
    Bollinger RSI Band Trading Strategy.
    
    Logic:
    1. Bollinger Bands (20, 2).
    2. RSI (14).
    3. Mean Reversion / Counter-Trend:
        - Buy: Price touches/breaks Lower Band AND RSI < 30 (Oversold).
        - Sell: Price touches/breaks Upper Band AND RSI > 70 (Overbought).
        - Exit: Price touches SMA (Middle Band).
    """
    
    def __init__(self, config: dict):
        super().__init__(config)
        self.name = "BOLLINGER_RSI"
        
        self.bb_length = 20
        self.bb_std = 2.0
        self.rsi_length = 14
        self.rsi_overbought = 70
        self.rsi_oversold = 22 # Targeting 75% Win Rate
        
    def analyze(self, df_5m: pd.DataFrame, df_15m: pd.DataFrame, 
                market_regime: str = "NEUTRAL", daily_bias: str = "NEUTRAL", 
                df_1h: pd.DataFrame = None, df_daily: pd.DataFrame = None) -> dict:
        
        if len(df_5m) < 50:
             return {'action': 'None', 'reason': 'Insufficient Data'}

        df = df_5m.copy()
        
        # Indicators
        bb = ta.bbands(df['Close'], length=self.bb_length, std=self.bb_std)
        rsi = ta.rsi(df['Close'], length=self.rsi_length)

        if bb is None or rsi is None:
             return {'action': 'None', 'reason': 'Indicator Calculation Failed'}
             
        # Extract BB columns (BBL, BBM, BBU)
        bbl_col = [c for c in bb.columns if c.startswith('BBL')][0]
        bbm_col = [c for c in bb.columns if c.startswith('BBM')][0]
        
        curr_bbl = bb.iloc[-1][bbl_col]
        curr_bbm = bb.iloc[-1][bbm_col] 
        
        curr_rsi = rsi.iloc[-1]
        curr_close = df.iloc[-1]['Close']
        curr_low = df.iloc[-1]['Low']
        
        action = "None"
        reason = []
        exit_signal = "None"
        
        # Entry Logic (High Win Rate Scalp - Long Only)
        # 1. Price <= Lower Band
        # 2. RSI < 22 (Targeting 75%)
        
        # BUY SIGNAL
        if (curr_low <= curr_bbl) and (curr_rsi < self.rsi_oversold):
            # Confirmation: Green Candle
            if df.iloc[-1]['Close'] > df.iloc[-1]['Open']:
                action = "BUY"
                reason.append(f"Mean Reversion (RSI < {self.rsi_oversold})")
        
        # SELL SIGNAL (Disabled - Low Win Rate)
                
        # Exit Logic
        if curr_close >= curr_bbm:
            exit_signal = "EXIT_BUY" # Take Profit
            
        atr = df.iloc[-1]['ATR'] if 'ATR' in df.columns else (curr_close * 0.01)
        
        return {
            'action': action,
            'exit_signal': exit_signal,
            'reason': "; ".join(reason),
            'current_price': float(curr_close),
            'atr': float(atr),
            'timestamp': df.index[-1],
            'sl_price': 0.0, 
            'target_r': 0.8, # Scalp Target (take profit quickly for high win rate)
            'indicators': {
                'RSI': float(curr_rsi),
                'BB_Lower': float(curr_bbl)
            }
        }
                
        # Sell: Price High >= Upper Band AND RSI > 70
        # (Not implemented here per user request usually implying Long, but let's add Short for completeness if symmetric)
        # Assuming Long Only due to "Stock Selection" context often implies buying. But checking if Short is desired.
        # "Trading Strategies" usually bidirectional.
        
        # Exit Logic (Mean Reversion targets Mean)
        # If Long and Price >= SMA (Middle Band) -> Exit
        if curr_close >= curr_bbm:
            exit_signal = "EXIT_BUY"
        # If Short and Price <= SMA -> Exit
        if curr_close <= curr_bbm:
            exit_signal = "EXIT_SELL"
            
        atr = df.iloc[-1]['ATR'] if 'ATR' in df.columns else (curr_close * 0.01)
        
        return {
            'action': action,
            'exit_signal': exit_signal,
            'reason': "; ".join(reason),
            'current_price': float(curr_close),
            'atr': float(atr),
            'timestamp': df.index[-1],
            'sl_price': 0.0, 
            'target_r': 1.5, # Scalp targets
            'indicators': {
                'RSI': float(curr_rsi),
                'BB_Lower': float(curr_bbl)
            }
        }
