import pandas as pd
import pandas_ta as ta
from .base import BaseStrategy
from .rsi_macd import RsiMacdStrategy

class CombinedStrategy(BaseStrategy):
    """
    Combined 'Trident' Strategy:
    1. Iman Retracement (Primary - 59% WR)
    2. RSI_MACD (Secondary - 46% WR)
    3. Dhan Scalp (Tertiary - 43% WR)
    """
    
    def __init__(self, config: dict):
        super().__init__(config)
        self.name = "COMBINED"
        # Instantiate sub-strategies
        self.rsi_strategy = RsiMacdStrategy(config)

    def analyze(self, df_5m: pd.DataFrame, df_15m: pd.DataFrame, 
                market_regime: str = "NEUTRAL", daily_bias: str = "NEUTRAL", 
                df_1h: pd.DataFrame = None, df_daily: pd.DataFrame = None) -> dict:
        
        # --- 1. Check Primary: Iman Retracement ---
        iman_res = self._check_iman(df_5m)
        if iman_res['action'] != 'None':
            return iman_res
            
        # --- 2. Check Secondary: RSI_MACD ---
        # Delegate to existing class
        rsi_res = self.rsi_strategy.analyze(df_5m, df_15m, market_regime, daily_bias, df_1h, df_daily)
        if rsi_res['action'] != 'None':
            # Tag the reason
            rsi_res['reason'] = f"[RSI] {rsi_res['reason']}"
            return rsi_res

        # --- 3. Check Tertiary: Dhan Scalp ---
        dhan_res = self._check_dhan(df_5m)
        if dhan_res['action'] != 'None':
            return dhan_res
            
        return {'action': 'None', 'reason': 'No Signal'}

    def _check_iman(self, df_5m):
        """Iman Retracement Logic"""
        if len(df_5m) < 20: return {'action': 'None'}
        
        last_5m = df_5m.iloc[-1]
        timestamp = last_5m.name
        close = last_5m['Close']
        low = last_5m['Low']
        high = last_5m['High']
        atr = last_5m.get('ATR', 0)
        
        prev_candle = df_5m.iloc[-2]
        prev_body = abs(prev_candle['Close'] - prev_candle['Open'])
        
        # Impulse Check
        if prev_body > (atr * 1.5):
            # Bullish Impulse
            if prev_candle['Close'] > prev_candle['Open']:
                impulse_high = prev_candle['High']
                range_len = impulse_high - prev_candle['Low']
                entry = impulse_high - (range_len * 0.25)
                stop = impulse_high - (range_len * 0.50)
                
                if low <= entry and close > stop:
                    return {
                        'action': 'BUY',
                        'reason': f"[IMAN] Retracement Buy {entry:.2f}",
                        'current_price': float(close),
                        'atr': float(atr),
                        'timestamp': timestamp,
                        'sl_price': float(stop),
                        'target_r': 1.0,
                        'stop_entry_price': 0.0,
                        'indicators': {'Strategy': 'Iman'}
                    }
                    
            # Bearish Impulse
            elif prev_candle['Close'] < prev_candle['Open']:
                impulse_low = prev_candle['Low']
                range_len = prev_candle['High'] - impulse_low
                entry = impulse_low + (range_len * 0.25)
                stop = impulse_low + (range_len * 0.50)
                
                if high >= entry and close < stop:
                    return {
                        'action': 'SELL',
                        'reason': f"[IMAN] Retracement Sell {entry:.2f}",
                        'current_price': float(close),
                        'atr': float(atr),
                        'timestamp': timestamp,
                        'sl_price': float(stop),
                        'target_r': 1.0, 
                        'stop_entry_price': 0.0,
                        'indicators': {'Strategy': 'Iman'}
                    }
        return {'action': 'None'}

    def _check_dhan(self, df_5m):
        """Dhan Scalp Logic (Ichimoku + MACD)"""
        if len(df_5m) < 50: return {'action': 'None'}
        
        last = df_5m.iloc[-1]
        timestamp = last.name
        close = last['Close']
        atr = last.get('ATR', 0)
        macd = last.get('MACD', 0)
        sig = last.get('MACD_Signal', 0)
        
        # Ichimoku (9, 26)
        try:
            # Quick calc if not in columns, or assume indicators.py adds them
            # We implemented this before. Let's do a quick calc to be safe.
            high9 = df_5m['High'].rolling(9).max()
            low9 = df_5m['Low'].rolling(9).min()
            tenkan = (high9 + low9) / 2
            
            high26 = df_5m['High'].rolling(26).max()
            low26 = df_5m['Low'].rolling(26).min()
            kijun = (high26 + low26) / 2
            
            t_val = tenkan.iloc[-1]
            k_val = kijun.iloc[-1]
            
            # Logic
            bullish = (t_val > k_val) and (macd > sig)
            bearish = (t_val < k_val) and (macd < sig)
            
            # Safe entry (near Kijun)
            dist = abs(close - k_val) / k_val
            safe = dist < 0.01
            
            if bullish and safe:
                # But check if we are already in Iman or RSI? 
                # This function is only called if others failed.
                return {
                    'action': 'BUY',
                    'reason': "[DHAN] Ichimoku Trend Buy",
                    'current_price': float(close),
                    'atr': float(atr),
                    'timestamp': timestamp,
                    'sl_price': float(k_val), # SL at Kijun
                    'target_r': 1.0,
                    'stop_entry_price': 0.0,
                    'indicators': {'Strategy': 'Dhan'}
                }
            elif bearish and safe:
                return {
                    'action': 'SELL',
                    'reason': "[DHAN] Ichimoku Trend Sell",
                    'current_price': float(close),
                    'atr': float(atr),
                    'timestamp': timestamp,
                    'sl_price': float(k_val),
                    'target_r': 1.0,
                    'stop_entry_price': 0.0,
                    'indicators': {'Strategy': 'Dhan'}
                }
                
        except Exception:
            pass
            
        return {'action': 'None'}
