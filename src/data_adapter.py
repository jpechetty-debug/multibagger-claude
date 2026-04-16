import pandas as pd
import yfinance as yf
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
import time
import logging
import os

class DataAdapter(ABC):
    """Abstract base class for data providers (Backtest/Live)."""
    
    @abstractmethod
    def fetch_data(self, symbol: str, timeframe: str, start: datetime = None, end: datetime = None) -> pd.DataFrame:
        """Fetches historical OHLCV data."""
        pass

    @abstractmethod
    def fetch_latest_candles(self, symbol: str, timeframe: str, limit: int = 100) -> pd.DataFrame:
        """Fetches the most recent candles for live analysis."""
        pass

class YFinanceAdapter(DataAdapter):
    """
    Uses yfinance to fetch data.
    Includes Self-Healing Blacklist and Caching.
    """
    
    def __init__(self, cache_dir: str = "data/cache"):
        self.logger = logging.getLogger("IntradaySignals.Adapter")
        self.blacklist = {} # Symbol -> expiry_timestamp
        self.error_counts = {} # Symbol -> count
        self.BLACKLIST_THRESHOLD = 3
        self.BLACKLIST_COOLDOWN = 3600 # 1 Hour
        self.cache_dir = cache_dir
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir, exist_ok=True)

    def is_blacklisted(self, symbol: str) -> bool:
        if symbol in self.blacklist:
            if time.time() < self.blacklist[symbol]:
                return True
            else:
                # Expired
                del self.blacklist[symbol]
                self.error_counts[symbol] = 0 # Reset count
                self.logger.info(f"Removing {symbol} from blacklist (Cooldown over).")
        return False

    def report_error(self, symbol: str):
        """Reports an error for a symbol."""
        self.error_counts[symbol] = self.error_counts.get(symbol, 0) + 1
        if self.error_counts[symbol] >= self.BLACKLIST_THRESHOLD:
            expiry = time.time() + self.BLACKLIST_COOLDOWN
            self.blacklist[symbol] = expiry
            self.logger.warning(f"Blacklisting {symbol} for 1 hour due to acceptable errors.")

    def report_success(self, symbol: str):
        """Reports success, clearing transient errors."""
        if symbol in self.error_counts:
            self.error_counts[symbol] = 0
            
    def _get_cache_path(self, symbol: str, timeframe: str) -> str:
        safe_sym = symbol.replace('.NS', '_NS')
        return os.path.join(self.cache_dir, f"{safe_sym}_{timeframe}.parquet")

    def fetch_data(self, symbol: str, timeframe: str, start: datetime = None, end: datetime = None) -> pd.DataFrame:
        """
        Fetches historical data from yfinance with Caching.
        """
        if self.is_blacklisted(symbol):
            return pd.DataFrame()
            
        # Check Cache
        cache_path = self._get_cache_path(symbol, timeframe)
        if os.path.exists(cache_path):
            try:
                # Check modification time (expire after 24h)
                mtime = os.path.getmtime(cache_path)
                if (time.time() - mtime) < 86400: # 1 Day valid
                    df_cache = pd.read_parquet(cache_path)
                    
                    # Ensure index tz aware
                    if df_cache.index.tz is None:
                        df_cache.index = df_cache.index.tz_localize('UTC').tz_convert('Asia/Kolkata')
                    else:
                        df_cache.index = df_cache.index.tz_convert('Asia/Kolkata')
                        
                    # Filter by date if provided
                    if start and end:
                        # Ensure safe timezone comparison
                        start_tz = start.astimezone(df_cache.index.tz) if start.tzinfo else pd.Timestamp(start).tz_localize('Asia/Kolkata')
                        end_tz = end.astimezone(df_cache.index.tz) if end.tzinfo else pd.Timestamp(end).tz_localize('Asia/Kolkata')
                        
                        mask = (df_cache.index >= start_tz) & (df_cache.index <= end_tz)
                        return df_cache.loc[mask]
                    
                    return df_cache
            except Exception as e:
                self.logger.warning(f"Cache read error for {symbol}: {e}")

        try:
            # Map timeframe format: 5m -> 5m, 15m -> 15m
            # yfinance supports: 1m, 2m, 5m, 15m, 30m, 60m, 90m, 1h, 1d, 5d, 1wk, 1mo, 3mo
            
            # Note: start/end are strict in yf.download.
            df = yf.download(symbol, start=start, end=end, interval=timeframe, progress=False, auto_adjust=False)
            
            if df.empty:
                self.logger.warning(f"No data returned for {symbol}")
                self.report_error(symbol)
                return df
                
            # Handle MultiIndex columns (YFinance <-> Pandas compatibility)
            if isinstance(df.columns, pd.MultiIndex):
                # We want the level that contains 'Close'
                if 'Close' in df.columns.get_level_values(0):
                    df.columns = df.columns.get_level_values(0)
                elif len(df.columns.levels) > 1 and 'Close' in df.columns.get_level_values(1):
                    df.columns = df.columns.get_level_values(1)
                else:
                    # Fallback: keep last level
                    df.columns = df.columns.get_level_values(-1)

            # Clean duplicate columns if any (rare but possible after flattening)
            df = df.loc[:, ~df.columns.duplicated()]

            df.rename(columns={
                'Open': 'Open', 'High': 'High', 'Low': 'Low', 
                'Close': 'Close', 'Volume': 'Volume', 'Adj Close': 'Adj Close'
            }, inplace=True)
            
            # Ensure index is timezone aware (Asia/Kolkata)
            # Yfinance usually returns localized UTC or Exchange time. 
            # We convert to Asia/Kolkata
            if df.index.tz is None:
                df.index = df.index.tz_localize('UTC').tz_convert('Asia/Kolkata')
            else:
                df.index = df.index.tz_convert('Asia/Kolkata')
            
            self.report_success(symbol)
            
            # Save to Cache (Full fetched range)
            try:
                df[['Open', 'High', 'Low', 'Close', 'Volume']].to_parquet(cache_path)
            except Exception as e:
                self.logger.warning(f"Cache write failed for {symbol}: {e}")
            
            return df[['Open', 'High', 'Low', 'Close', 'Volume']]

        except Exception as e:
            self.logger.error(f"Error fetching data for {symbol}: {e}")
            self.report_error(symbol)
            return pd.DataFrame()

    def fetch_latest_candles(self, symbol: str, timeframe: str, limit: int = 100) -> pd.DataFrame:
        """
        Fetches latest candles. For yfinance, we fetch '1d' or '5d' period with the interval.
        """
        if self.is_blacklisted(symbol):
            return pd.DataFrame()
            
        # Determine period based on timeframe to get enough bars
        period = "5d" # Default buffer for intraday
        if timeframe == '1d':
            period = '1mo' # Longer buffer for daily analysis
        elif timeframe == '1h':
            period = '1mo'

        
        try:
             # Use the same fetch logic, but specifying period instead of start/end
            df = yf.download(symbol, period=period, interval=timeframe, progress=False, ignore_tz=False, auto_adjust=False)
            
            if df.empty:
                self.report_error(symbol)
                return df
            
            if isinstance(df.columns, pd.MultiIndex):
                if 'Close' in df.columns.get_level_values(0):
                    df.columns = df.columns.get_level_values(0)
                elif len(df.columns.levels) > 1 and 'Close' in df.columns.get_level_values(1):
                    df.columns = df.columns.get_level_values(1)
                else:
                    df.columns = df.columns.get_level_values(-1)

            # Clean duplicate columns
            df = df.loc[:, ~df.columns.duplicated()]

            # Timezone handling
            if df.index.tz is None:
                df.index = df.index.tz_localize('UTC').tz_convert('Asia/Kolkata')
            else:
                df.index = df.index.tz_convert('Asia/Kolkata')
                
            self.report_success(symbol)
            return df[['Open', 'High', 'Low', 'Close', 'Volume']].tail(limit)
            
        except Exception as e:
            self.logger.error(f"Error fetching latest data for {symbol}: {e}")
            self.report_error(symbol)
            return pd.DataFrame()
            
    def fetch_batch_latest_candles(self, symbols: list, timeframe: str, limit: int = 100) -> dict:
        """
        Fetches latest candles for multiple symbols in a single batch request.
        Returns a dictionary: {symbol: DataFrame}
        """
        if not symbols: return {}
        
        # Filter blacklisted
        valid_symbols = [s for s in symbols if not self.is_blacklisted(s)]
        if not valid_symbols: return {}
        
        # Prepare tickers string
        tickers_str = " ".join(valid_symbols)
        
        # Determine period
        period = "5d" # Default buffer for intraday
        if timeframe == '1d': period = '1mo'
        elif timeframe == '1h': period = '1mo'
        
        try:
            self.logger.info(f"Batch fetching {len(valid_symbols)} symbols ({timeframe})...")
            # Fetch batch
            start_t = time.time()
            df = yf.download(tickers_str, period=period, interval=timeframe, group_by='ticker', progress=False, auto_adjust=False, threads=True)
            elapsed = time.time() - start_t
            self.logger.info(f"Batch fetch complete in {elapsed:.2f}s")
            
            if df.empty:
                return {}
                
            results = {}
            
            is_multi = isinstance(df.columns, pd.MultiIndex)
            
            if len(valid_symbols) == 1:
                # Single symbol case: might not be multiindex if just 1 passed to download?
                # Actually group_by='ticker' forces it usually.
                if is_multi:
                    try:
                        sym_df = df[valid_symbols[0]].copy()
                    except KeyError:
                        sym_df = df.copy() 
                else:
                    sym_df = df.copy()
                
                # Clean and Store
                sym_df = self._clean_df(sym_df)
                if not sym_df.empty:
                    results[valid_symbols[0]] = sym_df.tail(limit)
                    
            else:
                # Multi symbol
                for sym in valid_symbols:
                    try:
                        if is_multi:
                             # Access (Ticker, ...)
                             if sym in df.columns.get_level_values(0):
                                 sym_df = df[sym].copy()
                             else:
                                 continue
                        else:
                             continue
                             
                        sym_df = self._clean_df(sym_df)
                        if not sym_df.empty:
                            results[sym] = sym_df.tail(limit)
                            
                    except Exception as e:
                        continue
                        
            return results

        except Exception as e:
            self.logger.error(f"Batch Fetch Error: {e}")
            return {}

    def _clean_df(self, df: pd.DataFrame) -> pd.DataFrame:
        """Helper to clean and standardized DF from batch or single fetch."""
        if df.empty: return df
        
        # Handle MultiIndex columns (Level 1 typically has OHLCV)
        if isinstance(df.columns, pd.MultiIndex):
             # Try to find 'Close'
             if 'Close' in df.columns.get_level_values(0):
                 df.columns = df.columns.get_level_values(0)
             else:
                 df.columns = df.columns.get_level_values(-1)
        
        df = df.loc[:, ~df.columns.duplicated()]
        
        # Timezone
        if df.index.tz is None:
            df.index = df.index.tz_localize('UTC').tz_convert('Asia/Kolkata')
        else:
            df.index = df.index.tz_convert('Asia/Kolkata')
            
        return df[['Open', 'High', 'Low', 'Close', 'Volume']]

    def fetch_daily(self, symbol: str, days: int = 90) -> pd.DataFrame:
        """
        Fetches daily candlestick data for swing trading.
        
        Args:
            symbol: Stock symbol (e.g., 'RELIANCE.NS')
            days: Number of days of history to fetch
            
        Returns:
            DataFrame with daily OHLCV data
        """
        if self.is_blacklisted(symbol):
            return pd.DataFrame()
            
        try:
            # Fetch daily data
            df = yf.download(symbol, period=f"{days}d", interval='1d', progress=False, auto_adjust=False)
            
            if df.empty:
                self.logger.warning(f"No daily data returned for {symbol}")
                self.report_error(symbol)
                return df
                
            # Handle MultiIndex columns
            if isinstance(df.columns, pd.MultiIndex):
                if 'Close' in df.columns.get_level_values(0):
                    df.columns = df.columns.get_level_values(0)
                elif len(df.columns.levels) > 1 and 'Close' in df.columns.get_level_values(1):
                    df.columns = df.columns.get_level_values(1)
                else:
                    df.columns = df.columns.get_level_values(-1)

            df = df.loc[:, ~df.columns.duplicated()]
            
            # Timezone handling
            if df.index.tz is None:
                df.index = df.index.tz_localize('UTC').tz_convert('Asia/Kolkata')
            else:
                df.index = df.index.tz_convert('Asia/Kolkata')
                
            self.report_success(symbol)
            return df[['Open', 'High', 'Low', 'Close', 'Volume']]
            
        except Exception as e:
            self.logger.error(f"Error fetching daily data for {symbol}: {e}")
            self.report_error(symbol)
            return pd.DataFrame()
            
    def fetch_4h(self, symbol: str, days: int = 30) -> pd.DataFrame:
        """
        Fetches 4-hour candlestick data for swing entry timing.
        
        Args:
            symbol: Stock symbol (e.g., 'RELIANCE.NS')
            days: Number of days of history to fetch
            
        Returns:
            DataFrame with 4-hour OHLCV data
        """
        if self.is_blacklisted(symbol):
            return pd.DataFrame()
            
        try:
            # Note: yfinance doesn't support 4h directly, use 1h and resample
            df = yf.download(symbol, period=f"{days}d", interval='1h', progress=False, auto_adjust=False)
            
            if df.empty:
                self.logger.warning(f"No hourly data returned for {symbol}")
                self.report_error(symbol)
                return df
                
            # Handle MultiIndex columns
            if isinstance(df.columns, pd.MultiIndex):
                if 'Close' in df.columns.get_level_values(0):
                    df.columns = df.columns.get_level_values(0)
                elif len(df.columns.levels) > 1 and 'Close' in df.columns.get_level_values(1):
                    df.columns = df.columns.get_level_values(1)
                else:
                    df.columns = df.columns.get_level_values(-1)

            df = df.loc[:, ~df.columns.duplicated()]
            
            # Timezone handling
            if df.index.tz is None:
                df.index = df.index.tz_localize('UTC').tz_convert('Asia/Kolkata')
            else:
                df.index = df.index.tz_convert('Asia/Kolkata')
                
            # Resample to 4-hour
            df_4h = df.resample('4H').agg({
                'Open': 'first',
                'High': 'max',
                'Low': 'min',
                'Close': 'last',
                'Volume': 'sum'
            }).dropna()
                
            self.report_success(symbol)
            return df_4h
            
        except Exception as e:
            self.logger.error(f"Error fetching 4-hour data for {symbol}: {e}")
            self.report_error(symbol)
            return pd.DataFrame()

    def fetch_news(self, symbol: str = None) -> list:
        """
        Fetches news for a specific symbol or general market news.
        
        Args:
            symbol: Stock symbol (e.g., 'RELIANCE.NS'). If None, fetches for Nifty 50 (^NSEI).
            
        Returns:
            List of news dictionaries.
        """
        target = symbol if symbol else "^NSEI"
        try:
            ticker = yf.Ticker(target)
            news = ticker.news
            return news if news else []
        except Exception as e:
            self.logger.error(f"Error fetching news for {target}: {e}")
            return []


class LivePoller(DataAdapter):
    """
    Simulates a live feed by polling a REST endpoint (using yfinance as the backend here).
    Structure designed to be replaced by a real Broker API adapter.
    """
    def __init__(self, fallback_adapter: DataAdapter):
        self.adapter = fallback_adapter

    def fetch_data(self, symbol: str, timeframe: str, start: datetime = None, end: datetime = None) -> pd.DataFrame:
        return self.adapter.fetch_data(symbol, timeframe, start, end)

    def fetch_latest_candles(self, symbol: str, timeframe: str, limit: int = 100) -> pd.DataFrame:
        return self.adapter.fetch_latest_candles(symbol, timeframe, limit)

    def fetch_batch_latest_candles(self, symbols: list, timeframe: str, limit: int = 100) -> dict:
        if hasattr(self.adapter, 'fetch_batch_latest_candles'):
            return self.adapter.fetch_batch_latest_candles(symbols, timeframe, limit)
        return {}

    def fetch_news(self, symbol: str = None) -> list:
        if hasattr(self.adapter, 'fetch_news'):
            return self.adapter.fetch_news(symbol)
        return []

    def is_blacklisted(self, symbol: str) -> bool:
        if hasattr(self.adapter, 'is_blacklisted'):
            return self.adapter.is_blacklisted(symbol)
        return False

# Placeholder for real broker Websocket
class BrokerWebsocketStub:
    """
    Blueprint for a Websocket adapter.
    Users should implement `on_ticks` and `subscribe`.
    """
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.active_subscriptions = []

    def connect(self):
        print("Connecting to Broker Websocket (Stub)...")

    def subscribe(self, tokens: list):
        self.active_subscriptions.extend(tokens)
        print(f"Subscribed to {tokens}")

    def on_ticks(self, ticks):
        """Callback for incoming ticks."""
        pass
