import pandas as pd
import yfinance as yf
import logging
from datetime import datetime, timedelta

class SwingScanner:
    """
    Scans the market for swing trading candidates.
    Runs once daily, looks for trending stocks with breakout/pullback setups.
    """
    def __init__(self, config: dict):
        self.logger = logging.getLogger("IntradaySignals.SwingScanner")
        self.config = config
        swing_config = config.get('swing_trading', {})
        self.limit = swing_config.get('scanner_limit', 10)
        
    def scan(self, universe: list) -> list:
        """
        Scans the provided list of symbols and returns the Top N swing candidates.
        
        Criteria:
        - Price above 50-day MA (uptrend)
        - Average volume > 500K shares
        - Recent consolidation or pullback
        - RSI not overbought (< 70)
        
        Returns:
            List of symbol strings ranked by strength score
        """
        self.logger.info(f"Scanning {len(universe)} symbols for Top {self.limit} Swing Candidates...")
        
        if not universe:
            self.logger.warning("Empty universe provided to swing scanner.")
            return []

        try:
            # Batch download daily data for the universe
            tickers = " ".join(universe)
            
            # Fetch 90 days of daily data
            df = yf.download(tickers, period="90d", group_by='ticker', progress=False, auto_adjust=False)
            
            if df.empty:
                self.logger.error("Swing scanner returned no data.")
                return []

            results = []
            is_multi = isinstance(df.columns, pd.MultiIndex)
            
            for symbol in universe:
                try:
                    # Extract symbol data
                    if is_multi:
                        try:
                            sym_df = df[symbol].dropna()
                        except KeyError:
                            continue
                    else:
                        sym_df = df.dropna()
                        if universe[0] != symbol:
                            continue
                    
                    if len(sym_df) < 60:  # Need at least 60 days
                        continue
                        
                    # Calculate indicators
                    sym_df = self._calculate_swing_indicators(sym_df)
                    
                    # Get latest values
                    latest = sym_df.iloc[-1]
                    close = latest['Close']
                    
                    ema50 = latest.get('EMA_50', 0)
                    ema200 = latest.get('EMA_200', 0)
                    rsi = latest.get('RSI', 50)
                    atr = latest.get('ATR', 0)
                    vol_avg = sym_df['Volume'].tail(20).mean()
                    
                    # Apply filters
                    # Filter 1: Trending (above 50 MA)
                    if close <= ema50:
                        continue
                        
                    # Filter 2: Volume requirement (> 500K avg)
                    if vol_avg < 500000:
                        continue
                        
                    # Filter 3: RSI not overbought
                    if rsi >= 70:
                        continue
                        
                    # Filter 4: Price above 200 MA (long-term uptrend)
                    if ema200 > 0 and close <= ema200:
                        continue
                        
                    # Calculate strength score
                    score = self._calculate_strength_score(sym_df)
                    
                    # Check for setup (consolidation or pullback)
                    setup_type = self._identify_setup(sym_df)
                    
                    if setup_type != "NONE":
                        results.append({
                            'symbol': symbol,
                            'score': score,
                            'setup': setup_type,
                            'price': close,
                            'rsi': rsi,
                            'vol_avg': vol_avg,
                            'distance_from_ema50': ((close - ema50) / ema50) * 100
                        })
                    
                except Exception as e:
                    self.logger.debug(f"Error processing {symbol}: {e}")
                    continue

            # Sort by score (highest first)
            sorted_results = sorted(results, key=lambda x: x['score'], reverse=True)
            
            # Select Top N
            top_n = sorted_results[:self.limit]
            
            final_symbols = [item['symbol'] for item in top_n]
            
            # Log results
            msg = "Swing Scanner Results:\n"
            for item in top_n:
                msg += f"- {item['symbol']}: Score {item['score']:.2f} | {item['setup']} | RSI {item['rsi']:.1f}\n"
            self.logger.info(msg)
            
            return final_symbols

        except Exception as e:
            self.logger.error(f"Swing Scanner Failed: {e}", exc_info=True)
            return []
            
    def _calculate_swing_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate swing trading indicators on daily data."""
        # EMAs
        df['EMA_20'] = df['Close'].ewm(span=20, adjust=False).mean()
        df['EMA_50'] = df['Close'].ewm(span=50, adjust=False).mean()
        df['EMA_200'] = df['Close'].ewm(span=200, adjust=False).mean()
        
        # RSI
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))
        
        # ATR
        high_low = df['High'] - df['Low']
        high_close = (df['High'] - df['Close'].shift()).abs()
        low_close = (df['Low'] - df['Close'].shift()).abs()
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        df['ATR'] = ranges.max(axis=1).rolling(window=14).mean()
        
        # ADX
        plus_dm = df['High'].diff()
        minus_dm = -df['Low'].diff()
        plus_dm[plus_dm < 0] = 0
        minus_dm[minus_dm < 0] = 0
        
        tr = ranges.max(axis=1)
        atr_14 = tr.rolling(window=14).mean()
        
        plus_di = 100 * (plus_dm.rolling(window=14).mean() / atr_14)
        minus_di = 100 * (minus_dm.rolling(window=14).mean() / atr_14)
        
        dx = (abs(plus_di - minus_di) / (plus_di + minus_di)) * 100
        df['ADX'] = dx.rolling(window=14).mean()
        
        return df
        
    def _calculate_strength_score(self, df: pd.DataFrame) -> float:
        """
        Calculate a strength score for ranking candidates.
        Higher score = better candidate.
        """
        latest = df.iloc[-1]
        
        score = 0.0
        
        # Trend strength (0-30 points)
        ema20 = latest.get('EMA_20', 0)
        ema50 = latest.get('EMA_50', 0)
        ema200 = latest.get('EMA_200', 0)
        
        if ema20 > ema50 > ema200:
            score += 30  # Strong uptrend
        elif ema20 > ema50:
            score += 20  # Moderate uptrend
        elif latest['Close'] > ema50:
            score += 10  # Weak uptrend
            
        # ADX strength (0-25 points)
        adx = latest.get('ADX', 0)
        if adx > 40:
            score += 25  # Very strong trend
        elif adx > 30:
            score += 20
        elif adx > 25:
            score += 15
        elif adx > 20:
            score += 10
            
        # RSI momentum (0-20 points)
        rsi = latest.get('RSI', 50)
        if 50 < rsi < 65:
            score += 20  # Sweet spot
        elif 45 < rsi <= 50:
            score += 15  # Pullback opportunity
        elif 40 < rsi <= 45:
            score += 10  # Deeper pullback
            
        # Volume trend (0-15 points)
        vol_current = latest['Volume']
        vol_avg = df['Volume'].tail(20).mean()
        vol_ratio = vol_current / vol_avg if vol_avg > 0 else 1
        
        if vol_ratio > 2.0:
            score += 15  # Volume breakout
        elif vol_ratio > 1.5:
            score += 10
        elif vol_ratio > 1.2:
            score += 5
            
        # Price action (0-10 points)
        # Recent gainers
        returns_5d = ((latest['Close'] - df.iloc[-6]['Close']) / df.iloc[-6]['Close']) * 100
        if returns_5d > 5:
            score += 10
        elif returns_5d > 2:
            score += 5
            
        return score
        
    def _identify_setup(self, df: pd.DataFrame) -> str:
        """
        Identify if there's a tradeable setup.
        Returns: BREAKOUT, PULLBACK, or NONE
        """
        latest = df.iloc[-1]
        
        # Check for breakout (20-day high)
        lookback = 20
        range_high = df['High'].tail(lookback).iloc[:-1].max()  # Exclude today
        
        if latest['Close'] > range_high:
            return "BREAKOUT"
            
        # Check for pullback (near 50 EMA)
        ema50 = latest.get('EMA_50', 0)
        if ema50 > 0:
            distance = abs(latest['Close'] - ema50) / ema50
            if distance < 0.03:  # Within 3%
                return "PULLBACK"
                
        return "NONE"
