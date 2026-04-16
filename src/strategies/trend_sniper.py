import pandas as pd
from .base import BaseStrategy

class TrendSniperStrategy(BaseStrategy):
    """
    Trend Sniper Strategy:
    Uses 15m Trend + 5m Momentum + Price Action Triggers.
    Classic Trend Following.
    """
    
    def __init__(self, config: dict):
        super().__init__(config)
        self.name = "Trend Sniper"

    def analyze(self, df_5m: pd.DataFrame, df_15m: pd.DataFrame, 
                market_regime: str = "NEUTRAL", daily_bias: str = "NEUTRAL", 
                df_1h: pd.DataFrame = None, df_daily: pd.DataFrame = None) -> dict:
        
        # Ensure sufficient history
        if len(df_5m) < 20 or len(df_15m) < 5:
             return {'action': 'None', 'reason': 'Insufficient Data'}

        # Get latest
        last_5m = df_5m.iloc[-1]
        last_15m = df_15m.iloc[-1]
        timestamp = last_5m.name
        
        # Helper to safely get numeric values
        def get_safe(series, key, default=0.0):
            val = series.get(key)
            if val is None or pd.isna(val):
                return default
            return val

        # 0. Time Filter
        current_time = timestamp.time()
        start_time = pd.to_datetime("09:30").time()
        end_time = pd.to_datetime("15:00").time()
        
        if not (start_time <= current_time <= end_time):
             return {'action': 'None', 'reason': 'Outside Trading Window'}

        # Defaults
        action = "None"
        reason = []
        target_r = 2.0
        stop_entry_price = 0.0
        sl_price = 0.0
        
        # Indicators 5m
        close = last_5m['Close']
        high = last_5m['High']
        low = last_5m['Low']
        atr = get_safe(last_5m, 'ATR', 0)
        rsi = get_safe(last_5m, 'RSI', 50)
        rvol = get_safe(last_5m, 'RVOL', 1.0)
        
        # Bollinger Bands
        bbu = get_safe(last_5m, 'BBU', float('inf'))
        bbl = get_safe(last_5m, 'BBL', 0)
        
        # Patterns
        is_bull_engulf = bool(last_5m.get('Pattern_Bullish_Engulfing', False))
        is_hammer = bool(last_5m.get('Pattern_Hammer', False))
        is_bear_engulf = bool(last_5m.get('Pattern_Bearish_Engulfing', False))
        is_shooting_star = bool(last_5m.get('Pattern_Shooting_Star', False))
        
        # 1. HTF Trend (1H) - Optional Alignment
        htf_trend = "NEUTRAL"
        if df_1h is not None and not df_1h.empty:
            last_1h = df_1h.iloc[-1]
            ema50_1h = get_safe(last_1h, 'EMA_50', 0)
            if ema50_1h > 0:
                htf_trend = "BULLISH" if last_1h['Close'] > ema50_1h else "BEARISH"

        # 2. MTF Trend (15m) - Primary Filter
        trend_15m = "NEUTRAL"
        ema50_15m = get_safe(last_15m, 'EMA_50', 0)
        macd_15m = get_safe(last_15m, 'MACD', 0)
        macd_sig_15m = get_safe(last_15m, 'MACD_Signal', 0)
        close_15m = last_15m['Close']
        
        # Safe comparisons
        if close_15m > ema50_15m and macd_15m > macd_sig_15m:
            trend_15m = "BULLISH"
        elif close_15m < ema50_15m and macd_15m < macd_sig_15m:
            trend_15m = "BEARISH"
            
        # 3. Regime Filter (ADX 15m)
        adx_15m = get_safe(last_15m, 'ADX', 15)
        
        # Using 25 as trend strength threshold
        if adx_15m < 25:
            # We enforce trend following, so we might skip if ranging?
            # Or pass "RANGE" to logic.
            # Original code only traded if regime == "TREND" (implicit in if adx > 25 checks or similar)
            # The original code had `regime = "TREND" if adx_15m > 25 else "RANGE"`
            # And `if regime == "TREND":` block.
            return {'action': 'None', 'reason': f'Low ADX ({adx_15m:.1f}) - Choppy Market'}

        # 4. Signal Logic
        
        # BUY Logic
        if trend_15m == "BULLISH":
            # Alignment Check
            if daily_bias == "BULLISH" and htf_trend == "BULLISH":
                # Trigger
                if (is_bull_engulf or is_hammer):
                    # Filter 1: Volume
                    if rvol > 1.5:
                        # Filter 2: RSI
                        if 55 < rsi < 75:
                            # Filter 3: Value
                            if close < bbu:
                                action = "BUY"
                                reason.append(f"Trend Sniper BUY: Strong Momentum | RSI {rsi:.1f} | RVOL {rvol:.1f}")
                                sl_price = low - (atr * 1.5)
                                stop_entry_price = high + (atr * 0.1)

        # SELL Logic
        elif trend_15m == "BEARISH":
            # Alignment Check
            if daily_bias == "BEARISH" and htf_trend == "BEARISH":
                # Trigger
                if (is_bear_engulf or is_shooting_star):
                    # Filter 1: Volume
                    if rvol > 1.5:
                        # Filter 2: RSI
                        if 25 < rsi < 45:
                            # Filter 3: Value
                            if close > bbl:
                                action = "SELL"
                                reason.append(f"Trend Sniper SELL: Strong Momentum | RSI {rsi:.1f} | RVOL {rvol:.1f}")
                                sl_price = high + (atr * 1.5)
                                stop_entry_price = low - (atr * 0.1)

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
                'RVOL': float(rvol),
                'Trend_15m': trend_15m,
                'HTF_Trend': htf_trend,
                'ADX_15m': float(adx_15m)
            }
        }
