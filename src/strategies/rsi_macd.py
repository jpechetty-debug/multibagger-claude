import pandas as pd
from .base import BaseStrategy

class RsiMacdStrategy(BaseStrategy):
    """
    RSI + MACD Strategy (Elite v3 - Bounce Logic):
    - Trend Alignment (1H EMA 50)
    - Momentum Strength (ADX > 25)
    - Deep Pullback Requirement (RVOL > 1.2)
    - RSI Bounce: Recently < 40/60, now crossing 50.
    """
    
    def __init__(self, config: dict):
        super().__init__(config)
        self.name = "RSI_MACD"

    def analyze(self, df_5m: pd.DataFrame, df_15m: pd.DataFrame, 
                market_regime: str = "NEUTRAL", daily_bias: str = "NEUTRAL", 
                df_1h: pd.DataFrame = None, df_daily: pd.DataFrame = None) -> dict:
        
        # Ensure sufficient history
        if len(df_5m) < 50:
             return {'action': 'None', 'reason': 'Insufficient Data'}

        # Get latest
        last_5m = df_5m.iloc[-1]
        timestamp = last_5m.name
        
        # Defaults
        action = "None"
        reason = []
        target_r = 1.5 
        stop_entry_price = 0.0
        sl_price = 0.0
        
        close = last_5m['Close']
        atr = last_5m.get('ATR', 0)
        
        # --- 1. Confluence Filters ---
        
        # A. Trend Alignment (1H EMA 50)
        htf_trend = "NEUTRAL"
        if df_1h is not None and not df_1h.empty:
            ema50_1h = df_1h.iloc[-1].get('EMA_50')
            if ema50_1h is not None and ema50_1h > 0:
                if close > ema50_1h: htf_trend = "BULLISH"
                elif close < ema50_1h: htf_trend = "BEARISH"

        # B. Trend Strength (15m ADX)
        adx = 0
        if df_15m is not None and not df_15m.empty:
            adx_val = df_15m.iloc[-1].get('ADX')
            if adx_val is not None:
                adx = float(adx_val)
        
        strong_trend = adx > 20 # Relaxed slightly to 20 to allow early trend entries
        
        # C. Volume Confirmation (RVOL)
        # C. Volume Confirmation (RVOL)
        rvol = 0.0
        vol_sma = df_5m['Volume'].rolling(20).mean().iloc[-1]
        
        # Check if vol_sma is valid (not None and not 0)
        if vol_sma is not None and vol_sma > 0:
             rvol = last_5m['Volume'] / vol_sma
             
        high_vol = rvol > 1.0 
        
        # --- 2. Indicators ---
        def safe_get(series, key, default):
            return float(series.get(key, default))

        rsi = safe_get(last_5m, 'RSI', 50)
        # prev_rsi = safe_get(df_5m.iloc[-2], 'RSI', 50)
        
        # MACD
        macd = safe_get(last_5m, 'MACD', 0)
        macd_signal = safe_get(last_5m, 'MACD_Signal', 0)
        hist = safe_get(last_5m, 'MACD_Hist', 0)
        
        # --- 3. Entry Logic ---
        
        valid_buy = False
        valid_sell = False
        
        # Lookback for Deep Pullback (Last 5 bars)
        recent_rsi = df_5m['RSI'].tail(5)
        
        # Scenario A: Trend Pullback Buy (Bounce)
        if htf_trend == "BULLISH":
             was_oversold = (recent_rsi < 45).any()
             rsi_cross_up = (df_5m['RSI'].iloc[-2] < 50) and (rsi >= 50)
             momentum_ok = hist > 0
             candle_confirm = close > df_5m.iloc[-1]['Open'] # Green Candle
             
             if was_oversold and rsi_cross_up and momentum_ok and high_vol and candle_confirm:
                 valid_buy = True
                 reason.append("Trend Bounce Buy (Confirmed)")

        # Scenario B: Trend Pullback Sell (Rejection)
        elif htf_trend == "BEARISH":
             was_overbought = (recent_rsi > 55).any()
             rsi_cross_down = (df_5m['RSI'].iloc[-2] > 50) and (rsi <= 50)
             momentum_ok = hist < 0
             candle_confirm = close < df_5m.iloc[-1]['Open'] # Red Candle
             
             if was_overbought and rsi_cross_down and momentum_ok and high_vol and candle_confirm:
                 valid_sell = True
                 reason.append("Trend Rejection Sell (Confirmed)")

        # --- 4. Execution ---
        # Target R reduced to 0.8 for Maximum Hit Rate (Quick Scalp)
        target_r = 0.8
        
        if valid_buy:
            action = "BUY"
            reason.append(f"ADX={adx:.1f}")
            recent_low = df_5m['Low'].tail(5).min()
            sl_price = recent_low - (atr * 0.5)
            # Safety
            if (close - sl_price)/close > 0.01: sl_price = close * 0.99
            if sl_price >= close: sl_price = close * 0.995
                
        elif valid_sell:
            action = "SELL"
            reason.append(f"ADX={adx:.1f}")
            recent_high = df_5m['High'].tail(5).max()
            sl_price = recent_high + (atr * 0.5)
            if (sl_price - close)/close > 0.01: sl_price = close * 1.01
            if sl_price <= close: sl_price = close * 1.005
            
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
                'RSI': float(rsi),
                'MACD': float(macd),
                'ADX': float(adx)
            }
        }
