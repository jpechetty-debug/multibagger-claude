import pandas as pd
from .base import BaseStrategy

class StochMacdStrategy(BaseStrategy):
    """
    Stoch RSI + MACD + Volume Strategy:
    Simple oscillator based strategy w/ Volume confirmation.
    """
    
    def __init__(self, config: dict):
        super().__init__(config)
        self.name = "STOCH_MACD"

    def analyze(self, df_5m: pd.DataFrame, df_15m: pd.DataFrame, 
                market_regime: str = "NEUTRAL", daily_bias: str = "NEUTRAL", 
                df_1h: pd.DataFrame = None, df_daily: pd.DataFrame = None) -> dict:
        
        last_5m = df_5m.iloc[-1]
        timestamp = last_5m.name
        
        # Defaults
        action = "None"
        reason = []
        target_r = 2.0
        sl_price = 0.0
        stop_entry_price = 0.0
        
        close = last_5m['Close']
        atr = last_5m.get('ATR', 0)
        
        # Indicators
        stoch_k = last_5m.get('Stoch_K', 50)
        prev_stoch_k = df_5m.iloc[-2].get('Stoch_K', 50)
        
        macd = last_5m.get('MACD', 0)
        macd_signal = last_5m.get('MACD_Signal', 0)
        
        vol = last_5m.get('Volume', 0)
        vol_ma = last_5m.get('Vol_SMA', 1)
        
        # Conditions
        # 1. Stoch K Crossover 20 (Bullish) or Crossunder 80 (Bearish)
        bull_crossover = (prev_stoch_k < 20) and (stoch_k >= 20)
        bear_crossunder = (prev_stoch_k > 80) and (stoch_k <= 80)
        
        # 2. MACD Filter
        macd_bullish = macd > macd_signal
        macd_bearish = macd < macd_signal
        
        # 3. Volume Spike ( > 1.5x Average)
        vol_spike = vol > (vol_ma * 1.5)
        
        if bull_crossover and macd_bullish and vol_spike:
            action = "BUY"
            reason.append(f"Stoch+MACD BUY: K={stoch_k:.1f} crossed 20 | MACD Bullish | Vol Spike {vol/vol_ma:.1f}x")
            sl_price = close * 0.99 # 1% SL
            target_r = 2.0 
            stop_entry_price = 0

        elif bear_crossunder and macd_bearish and vol_spike:
            action = "SELL"
            reason.append(f"Stoch+MACD SELL: K={stoch_k:.1f} crossed 80 | MACD Bearish | Vol Spike {vol/vol_ma:.1f}x")
            sl_price = close * 1.01
            target_r = 2.0
            stop_entry_price = 0

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
                'Stoch_K': float(stoch_k),
                'MACD': float(macd),
                'Vol_Ratio': float(vol / vol_ma if vol_ma > 0 else 0)
            }
        }
