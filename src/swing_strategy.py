import pandas as pd
import numpy as np
from .indicators import calculate_indicators, calculate_trend_indicators
from .rv_strategy import RelativeVolumeStrategy

class SwingStrategyEngine:
    """
    Swing Trading Strategy Engine for daily/4-hour timeframes.
    Implements trend following, breakout, and pullback strategies.
    """
    def __init__(self, config: dict):
        self.config = config
        swing_config = config.get('swing_trading', {})
        
        self.strategy_mode = swing_config.get('strategy_mode', 'TREND_FOLLOWING')
        self.stop_loss_atr_multiplier = swing_config.get('stop_loss_atr_multiplier', 2.5)
        self.target_r = swing_config.get('target_r', 4.0)
        self.max_hold_days = swing_config.get('max_hold_days', 15)
        
        # Initialize sub-strategies
        if self.strategy_mode == 'RV_STRATEGY':
            self.rv_engine = RelativeVolumeStrategy(config)
        else:
            self.rv_engine = None
        
    def analyze(self, df_daily: pd.DataFrame, df_4h: pd.DataFrame = None) -> dict:
        """
        Analyzes daily and 4-hour data to generate swing trading signals.
        
        Args:
            df_daily: Daily candlestick data with indicators
            df_4h: Optional 4-hour data for entry timing
            
        Returns:
            Signal dictionary with action, reason, prices, etc.
        """
        # Validate data
        if len(df_daily) < 60:
            return {'action': 'None', 'reason': 'Insufficient daily data (need 60+ bars)'}
            
        # Get latest candles
        last_daily = df_daily.iloc[-1]
        prev_daily = df_daily.iloc[-2]
        timestamp = last_daily.name
        
        # Extract key data
        close = last_daily['Close']
        high = last_daily['High']
        low = last_daily['Low']
        volume = last_daily['Volume']
        
        # Indicators
        ema20 = last_daily.get('EMA_20', 0)
        ema50 = last_daily.get('EMA_50', 0)
        ema200 = last_daily.get('EMA_200', 0)
        
        prev_ema20 = prev_daily.get('EMA_20', 0)
        prev_ema50 = prev_daily.get('EMA_50', 0)
        
        rsi = last_daily.get('RSI', 50)
        atr = last_daily.get('ATR', 0)
        adx = last_daily.get('ADX', 15)
        
        macd = last_daily.get('MACD', 0)
        macd_signal = last_daily.get('MACD_Signal', 0)
        
        bbu = last_daily.get('BBU', float('inf'))
        bbl = last_daily.get('BBL', 0)
        
        vol_sma = last_daily.get('Vol_SMA', 1)
        
        # Initialize signal
        action = "None"
        reason = []
        sl_price = 0.0
        stop_entry_price = 0.0
        
        # ================================================================
        # STRATEGY 1: TREND FOLLOWING (Primary)
        # ================================================================
        if self.strategy_mode == 'TREND_FOLLOWING':
            # Determine trend
            trend = "NEUTRAL"
            if ema20 > ema50 > ema200 and close > ema50:
                trend = "BULLISH"
            elif ema20 < ema50 < ema200 and close < ema50:
                trend = "BEARISH"
                
            # Check for EMA crossover
            golden_cross = (prev_ema20 <= prev_ema50) and (ema20 > ema50)
            death_cross = (prev_ema20 >= prev_ema50) and (ema20 < ema50)
            
            # MACD confirmation
            macd_bullish = macd > macd_signal and macd > 0
            macd_bearish = macd < macd_signal and macd < 0
            
            # Strength filter
            strong_trend = adx > 25
            
            # Volume confirmation
            volume_confirm = volume > (vol_sma * 1.5)
            
            # BUY SIGNAL: Golden Cross + Confirmation
            if golden_cross and macd_bullish and strong_trend:
                if 40 < rsi < 70:  # Not overbought
                    action = "BUY"
                    reason.append(f"Trend Following BUY: Golden Cross | ADX {adx:.1f} | RSI {rsi:.1f}")
                    
                    # Stop Loss: Below recent swing low or 2.5 ATR
                    recent_low = df_daily['Low'].tail(10).min()
                    sl_price = max(recent_low - (atr * 0.5), close - (atr * self.stop_loss_atr_multiplier))
                    
                    # Entry: Use 4h confirmation if available, else market
                    stop_entry_price = 0  # Market entry for now
                    
            # SELL SIGNAL: Death Cross + Confirmation
            elif death_cross and macd_bearish and strong_trend:
                if 30 < rsi < 60:  # Not oversold
                    action = "SELL"
                    reason.append(f"Trend Following SELL: Death Cross | ADX {adx:.1f} | RSI {rsi:.1f}")
                    
                    # Stop Loss: Above recent swing high or 2.5 ATR
                    recent_high = df_daily['High'].tail(10).max()
                    sl_price = min(recent_high + (atr * 0.5), close + (atr * self.stop_loss_atr_multiplier))
                    
                    stop_entry_price = 0
                    
            # Pullback in Established Trend
            elif trend == "BULLISH" and not golden_cross:
                # Look for pullback to support
                near_ema50 = abs(close - ema50) / ema50 < 0.02  # Within 2% of EMA50
                rsi_pullback = 40 < rsi < 55
                
                if near_ema50 and rsi_pullback and macd_bullish:
                    action = "BUY"
                    reason.append(f"Pullback BUY: Trend Support at EMA50 | RSI {rsi:.1f}")
                    sl_price = ema50 - (atr * self.stop_loss_atr_multiplier)
                    stop_entry_price = 0
                    
            elif trend == "BEARISH" and not death_cross:
                # Look for rally to resistance
                near_ema50 = abs(close - ema50) / ema50 < 0.02
                rsi_rally = 45 < rsi < 60
                
                if near_ema50 and rsi_rally and macd_bearish:
                    action = "SELL"
                    reason.append(f"Rally SELL: Trend Resistance at EMA50 | RSI {rsi:.1f}")
                    sl_price = ema50 + (atr * self.stop_loss_atr_multiplier)
                    stop_entry_price = 0
                    
        # ================================================================
        # STRATEGY 2: BREAKOUT
        # ================================================================
        elif self.strategy_mode == 'BREAKOUT':
            # Calculate 20-day high/low for consolidation range
            lookback = 20
            range_high = df_daily['High'].tail(lookback).max()
            range_low = df_daily['Low'].tail(lookback).min()
            range_size = (range_high - range_low) / range_low
            
            # Check if in consolidation (tight range)
            in_consolidation = range_size < 0.10  # Less than 10% range
            
            # Volume spike for breakout confirmation
            volume_breakout = volume > (vol_sma * 2.0)  # 2x average
            
            # Bullish Breakout
            if close > range_high and in_consolidation and volume_breakout:
                if rsi < 75:  # Not too overbought
                    action = "BUY"
                    reason.append(f"Breakout BUY: Above {lookback}d Range | Vol {volume/vol_sma:.1f}x | RSI {rsi:.1f}")
                    
                    # Stop Loss: Just below breakout level
                    sl_price = range_high - (atr * 1.0)
                    stop_entry_price = range_high + (atr * 0.2)  # Stop limit slightly above
                    
            # Bearish Breakdown
            elif close < range_low and in_consolidation and volume_breakout:
                if rsi > 25:  # Not too oversold
                    action = "SELL"
                    reason.append(f"Breakdown SELL: Below {lookback}d Range | Vol {volume/vol_sma:.1f}x | RSI {rsi:.1f}")
                    
                    sl_price = range_low + (atr * 1.0)
                    stop_entry_price = range_low - (atr * 0.2)

                    
        # ================================================================
        # STRATEGY 4: RV STRATEGY (Separate Module)
        # ================================================================
        elif self.strategy_mode == 'RV_STRATEGY' and self.rv_engine:
            rv_signal = self.rv_engine.analyze(df_daily)
            if rv_signal['action'] != 'None':
                action = rv_signal['action']
                reason.append(rv_signal['reason'])
                sl_price = rv_signal.get('sl_price', 0.0)
                # RV strategy calculates target price, but engine expects target_r usage
                # We can rely on engine's target_r or use calculated price?
                # Engine usually manages exits.
                pass

        elif self.strategy_mode == 'PULLBACK':
            # Identify trend first
            uptrend = ema20 > ema50 and close > ema200
            downtrend = ema20 < ema50 and close < ema200
            
            # In uptrend, buy dips
            if uptrend:
                # RSI oversold but not extreme
                rsi_dip = 35 < rsi < 45
                
                # Price near lower Bollinger Band
                near_lower_bb = close < (bbl * 1.02)
                
                # MACD still positive (trend intact)
                trend_intact = macd > 0
                
                if rsi_dip and near_lower_bb and trend_intact:
                    action = "BUY"
                    reason.append(f"Pullback BUY: Dip in Uptrend | RSI {rsi:.1f} | Near BB Low")
                    
                    sl_price = bbl - (atr * 1.5)
                    stop_entry_price = 0
                    
            # In downtrend, sell rallies
            elif downtrend:
                # RSI overbought but not extreme
                rsi_rally = 55 < rsi < 65
                
                # Price near upper Bollinger Band
                near_upper_bb = close > (bbu * 0.98)
                
                # MACD still negative
                trend_intact = macd < 0
                
                if rsi_rally and near_upper_bb and trend_intact:
                    action = "SELL"
                    reason.append(f"Rally SELL: Bounce in Downtrend | RSI {rsi:.1f} | Near BB High")
                    
                    sl_price = bbu + (atr * 1.5)
                    stop_entry_price = 0
                    
        # Return signal
        return {
            'action': action,
            'reason': "; ".join(reason),
            'current_price': close,
            'atr': atr,
            'timestamp': timestamp,
            'sl_price': sl_price,
            'target_r': self.target_r,
            'stop_entry_price': stop_entry_price,
            'indicators': {
                'EMA20': ema20,
                'EMA50': ema50,
                'EMA200': ema200,
                'RSI': rsi,
                'ADX': adx,
                'MACD': macd,
                'Volume_Ratio': volume / vol_sma if vol_sma > 0 else 0
            }
        }
