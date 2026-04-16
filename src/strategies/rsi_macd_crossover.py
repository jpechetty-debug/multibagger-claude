import pandas as pd
import pandas_ta as ta
from .base import BaseStrategy

class RsiMacdCrossoverStrategy(BaseStrategy):
    """
    RSI MACD Crossover Strategy.
    
    Logic:
    1. Calculate MACD (Fast, Slow, Signal).
    2. Calculate RSI on the MACD SIGNAL line (not Close).
    3. Buy Entry: RSI(Signal) crosses ABOVE Oversold (default 30).
    4. Sell Entry: RSI(Signal) crosses BELOW Overbought (default 70).
    5. Buy Exit: RSI(Signal) crosses ABOVE Overbought.
    6. Sell Exit: RSI(Signal) crosses BELOW Oversold.
    """
    
    def __init__(self, config: dict):
        super().__init__(config)
        self.name = "RSI_MACD_Crossover"
        
        # Parameters
        self.fast_period = config.get('TIMEPERIOD_FAST', 12)
        self.slow_period = config.get('TIMEPERIOD_SLOW', 26)
        self.signal_period = config.get('TIMEPERIOD_SIGNAL', 9)
        self.rsi_period = config.get('TIMEPERIOD_RSI', 14)
        self.oversold = config.get('OVERSOLD_VALUE', 30)
        self.overbought = config.get('OVERBOUGHT_VALUE', 70)

    def analyze(self, df_5m: pd.DataFrame, df_15m: pd.DataFrame, 
                market_regime: str = "NEUTRAL", daily_bias: str = "NEUTRAL", 
                df_1h: pd.DataFrame = None, df_daily: pd.DataFrame = None) -> dict:
        
        if len(df_5m) < max(self.slow_period + self.signal_period, self.rsi_period) + 20:
             return {'action': 'None', 'reason': 'Insufficient Data'}

        # We operate on 5m entries by default from the prompt context (usually intraday)
        # But allow flexibility if needed. Using df_5m as primary.
        df = df_5m.copy()
        
        # 1. MACD
        # pandas-ta macd returns a DataFrame with columns: MACD_..., MACDh_..., MACDs_...
        # We need the Signal line (MACDs)
        macd_df = ta.macd(df['Close'], fast=self.fast_period, slow=self.slow_period, signal=self.signal_period)
        
        if macd_df is None or macd_df.empty:
            return {'action': 'None', 'reason': 'MACD Calculation Failed'}
            
        # Identify columns dynamically
        # MACDs is the Signal Line
        sig_col = [c for c in macd_df.columns if c.startswith('MACDs')][0]
        macd_signal_line = macd_df[sig_col]
        
        # 2. RSI of MACD Signal
        # fillna(0) to handle initial NaNs so RSI can calculate
        # However, RSI needs valid data.
        rsi_val = ta.rsi(macd_signal_line, length=self.rsi_period)
        
        if rsi_val is None:
             return {'action': 'None', 'reason': 'RSI Calculation Failed'}
             
        # Get current and previous values
        current_rsi = rsi_val.iloc[-1]
        prev_rsi = rsi_val.iloc[-2]
        
        # Detect Crossovers
        # Cross Above Oversold (30): Prev <= 30, Curr > 30
        crossover_above_oversold = (prev_rsi <= self.oversold) and (current_rsi > self.oversold)
        
        # Cross Below Overbought (70): Prev >= 70, Curr < 70
        crossover_below_overbought = (prev_rsi >= self.overbought) and (current_rsi < self.overbought)
        
        # Cross Above Overbought (70): Prev <= 70, Curr > 70
        crossover_above_overbought = (prev_rsi <= self.overbought) and (current_rsi > self.overbought)
        
        # Cross Below Oversold (30): Prev >= 30, Curr < 30
        crossover_below_oversold = (prev_rsi >= self.oversold) and (current_rsi < self.oversold)
        
        action = "None"
        reason = []
        
        # Entry Logic
        if crossover_above_oversold:
            action = "BUY"
            reason.append("RSI(MACD_Sig) Cross Above Oversold")
            
        elif crossover_below_overbought:
            action = "SELL"
            reason.append("RSI(MACD_Sig) Cross Below Overbought")
            
        # Exit Signal Logic (To be handled by the bot engine usually, but we can return 'EXIT' or similar if the interface supports it)
        # The BaseStrategy interface typically returns 'BUY' or 'SELL' for entries. 
        # Exits are often handled by checking current position.
        # However, the user request specifically had logic for "strategy_select_instruments_for_exit".
        # The standard analyze() returns an Action. If we are already in a position, the Engine might check this?
        # Standard Bot Engine usually calls `analyze` to get entry signals. 
        # Specialized Exit Logic might need to be exposed or we treat it as an opposing signal?
        
        # In many systems:
        # If Long and we get "SELL", we Exit/Flip?
        # If Action is "EXIT_BUY" or "EXIT_SELL"?
        
        # Looking at user's code:
        # Select for Exit -> if (oversold_crossover == -1 (Cross Below 30)) and Type is SELL -> Exit
        # Select for Exit -> if (overbought_crossover == 1 (Cross Above 70)) and Type is BUY -> Exit
        
        # If we follow the standard interface:
        # We can add a custom key in the dict like 'force_exit': True/False?
        # Or returns 'EXIT_BUY' / 'EXIT_SELL'?
        # Let's check BaseStrategy again. It documents 'BUY' | 'SELL' | 'None'.
        # But usually 'SELL' when Long = Exit? 
        # User logic has specific exit conditions that are NOT just Entry signals.
        # E.g. Exit Sell (Short) when RSI crosses BELOW 30.
        # But Entry Buy is when RSI crosses ABOVE 30.
        # So Entry Buy != Exit Sell condition.
        
        # We will add 'exit_signal' to the return dict.
        
        exit_signal = "None"
        if crossover_above_overbought:
            exit_signal = "EXIT_BUY" # Exit Longs
        elif crossover_below_oversold:
            exit_signal = "EXIT_SELL" # Exit Shorts
            
        close = df_5m.iloc[-1]['Close']
        atr = df_5m.iloc[-1]['ATR'] if 'ATR' in df_5m.columns else 0.0
        
        return {
            'action': action,
            'exit_signal': exit_signal, # augmented return
            'reason': "; ".join(reason),
            'current_price': float(close),
            'atr': float(atr),
            'timestamp': df_5m.index[-1],
            'sl_price': 0.0, # Strategy specific or Engine calculation
            'target_r': 2.0, # Default
            'stop_entry_price': 0.0,
            'indicators': {
                'RSI_MACD_Signal': float(current_rsi),
                'MACD_Signal': float(macd_signal_line.iloc[-1])
            }
        }
