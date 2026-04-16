import pandas as pd
from .base import BaseStrategy
from ..smart_money import find_swings, detect_structure_break, detect_liquidity_sweep, detect_three_drives, detect_divergence, detect_order_blocks, detect_imbalance

class SMCStrategy(BaseStrategy):
    """
    SMC Price Action Scalper:
    Uses "Smart Money Concepts" logic: BOS, Sweeps, Order Blocks.
    """
    
    def __init__(self, config: dict):
        super().__init__(config)
        self.name = "SMC_SCALP"

    def analyze(self, df_5m: pd.DataFrame, df_15m: pd.DataFrame, 
                market_regime: str = "NEUTRAL", daily_bias: str = "NEUTRAL", 
                df_1h: pd.DataFrame = None, df_daily: pd.DataFrame = None) -> dict:
        
        # Ensure sufficient history for peaks/troughs
        if len(df_5m) < 50:
             return {'action': 'None', 'reason': 'Insufficient Data'}

        last_5m = df_5m.iloc[-1]
        timestamp = last_5m.name
        
        # 1. HTF Trend (1H) - Primary Bias
        htf_trend = "NEUTRAL"
        if df_1h is not None and not df_1h.empty:
            last_1h = df_1h.iloc[-1]
            ema50_1h = last_1h.get('EMA_50', 0)
            if ema50_1h > 0:
                htf_trend = "BULLISH" if last_1h['Close'] > ema50_1h else "BEARISH"

        # 2. SMC Parsing
        # Helper: Calculate Swings on the 5m Data (copy to avoid mutation)
        df_smc = find_swings(df_5m.copy())
        
        bos = detect_structure_break(df_smc)
        sweep = detect_liquidity_sweep(df_smc)
        pattern = detect_three_drives(df_smc)
        div = detect_divergence(df_smc)
        
        # New: OB and FVG
        ob = detect_order_blocks(df_smc)
        df_smc = detect_imbalance(df_smc)
        last_fvg_bullish = df_smc.iloc[-1]['FVG_Bullish']
        last_fvg_bearish = df_smc.iloc[-1]['FVG_Bearish']
        
        # 3. Filters
        bias_bullish = (htf_trend == "BULLISH")
        bias_bearish = (htf_trend == "BEARISH")
        
        close = last_5m['Close']
        high = last_5m['High']
        low = last_5m['Low']
        atr = last_5m.get('ATR', 0)
        
        vwap = last_5m.get('VWAP', 0)
        above_vwap = close > vwap
        below_vwap = close < vwap
        
        # Use 15m ADX for Trend Strength (calculated in calculate_trend_indicators)
        adx = 0
        if df_15m is not None and not df_15m.empty:
            adx = df_15m.iloc[-1].get('ADX', 0)
            
        strong_trend = adx > 25 

        # 4. Signal Logic
        action = "None"
        reason = []
        target_r = 3.0 
        sl_price = 0.0
        stop_entry_price = 0.0
        
        signal_valid = False
        signal_type = ""
        
        # TIME FILTER: Only trade 09:30 - 14:30
        current_time = timestamp.time()
        time_ok = (current_time.hour > 9 or (current_time.hour == 9 and current_time.minute >= 30)) and (current_time.hour < 14 or (current_time.hour == 14 and current_time.minute <= 30))
        
        if not time_ok:
            return {'action': 'None', 'reason': 'Outside Trading Hours'}
        
        # ENTRY CONFIRMATION: Current Candle Color
        is_green = close > df_5m.iloc[-1]['Open']
        is_red = close < df_5m.iloc[-1]['Open']
        
        if bias_bullish:
            # BOS
            if bos['type'] == 'BULLISH_BOS' and above_vwap and strong_trend and is_green:
                signal_valid = True
                signal_type = "SMC Trend Continuation (BOS)"
                
            # OB Retest + GREEN Candle Confirmation
            elif ob['type'] == 'BULLISH_OB':
                if low <= ob['top'] and close >= ob['bottom'] and is_green:
                     signal_valid = True
                     signal_type = "SMC Order Block Retest"
            
            # FVG + Impulse
            elif last_fvg_bullish and is_green:
                if strong_trend:
                    signal_valid = True
                    signal_type = "SMC Bullish Impulse (FVG)"
                
            if signal_valid:
                action = "BUY"
                reason.append(f"{signal_type} | HTF {htf_trend} | ADX {adx:.1f}")
                
                # SL: Below recent Swing Low or Candle Low
                recent_low = df_smc['Swing_Low_Price'].ffill().iloc[-1]
                if pd.isna(recent_low) or recent_low > close:
                     recent_low = low - atr 
                sl_price = recent_low - (atr * 0.2) # We tightened SL slightly as we have confirmation
                
        # SELL SIGNAL
        else:
            if bias_bearish:
                if bos['type'] == 'BEARISH_BOS' and below_vwap and strong_trend and is_red:
                    signal_valid = True
                    signal_type = "SMC Trend Continuation (BOS)"

                # OB Retest + RED Candle
                elif ob['type'] == 'BEARISH_OB':
                    if high >= ob['bottom'] and close <= ob['top'] and is_red:
                        signal_valid = True
                        signal_type = "SMC Order Block Retest"
                        
                # FVG + Impulse
                elif last_fvg_bearish and is_red:
                    if strong_trend:
                        signal_valid = True
                        signal_type = "SMC Bearish Impulse (FVG)"
                    
            if signal_valid:
                action = "SELL"
                reason.append(f"{signal_type} | HTF {htf_trend} | ADX {adx:.1f}")
                
                recent_high = df_smc['Swing_High_Price'].ffill().iloc[-1]
                if pd.isna(recent_high) or recent_high < close:
                     recent_high = high + atr
                sl_price = recent_high + (atr * 0.2) # Tightened SL

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
                'SMC_BOS': bos['type'],
                'SMC_Sweep': sweep['type'],
                'HTF_Trend': htf_trend
            }
        }
