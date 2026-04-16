import pandas as pd
import pandas_ta as ta
import numpy as np

import warnings

# Suppress invalid value warnings from pandas_ta (log10(0) etc)
warnings.filterwarnings("ignore", category=RuntimeWarning)

def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculates technical indicators required for the strategy.
    Expects DataFrame with 'Open', 'High', 'Low', 'Close', 'Volume'.
    """
    # Ensure sufficient data
    if len(df) < 50:
        return df

    # RSI (14)
    df['RSI'] = ta.rsi(df['Close'], length=14)

    # Stochastic RSI (14, 14, 3, 3)
    stoch_rsi = ta.stochrsi(df['Close'], length=14, rsi_length=14, k=3, d=3)
    if stoch_rsi is not None:
        # Columns are usually STOCHRSIk_... and STOCHRSId_...
        k_col = [c for c in stoch_rsi.columns if c.startswith('STOCHRSIk')][0]
        d_col = [c for c in stoch_rsi.columns if c.startswith('STOCHRSId')][0]
        df['Stoch_K'] = stoch_rsi[k_col]
        df['Stoch_D'] = stoch_rsi[d_col]

    # Bollinger Bands (20, 2)
    bb = ta.bbands(df['Close'], length=20, std=2)
    if bb is not None:
        # Dynamically find columns as pandas-ta naming can vary (e.g. BBL_20_2.0 vs BBL_20_2)
        # We expect columns starting with BBL, BBM, BBU
        bbl_col = [c for c in bb.columns if c.startswith('BBL')][0]
        bbm_col = [c for c in bb.columns if c.startswith('BBM')][0]
        bbu_col = [c for c in bb.columns if c.startswith('BBU')][0]
        
        df['BBL'] = bb[bbl_col]
        df['BBM'] = bb[bbm_col]
        df['BBU'] = bb[bbu_col]

    # ATR (14)
    df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)

    # VWAP (Intraday)
    # ... (existing comments) ...
    df['VWAP'] = ta.vwap(df['High'], df['Low'], df['Close'], df['Volume'])

    # RVOL (20)
    df['Vol_SMA'] = ta.sma(df['Volume'], length=20)
    df['RVOL'] = df['Volume'] / df['Vol_SMA']
    
    # EMA (10, 20, 50, 200) for Dynamic Support/Resistance & Crossovers
    df['EMA_10'] = ta.ema(df['Close'], length=10)
    df['EMA_20'] = ta.ema(df['Close'], length=20)
    df['EMA_50'] = ta.ema(df['Close'], length=50)
    df['EMA_200'] = ta.ema(df['Close'], length=200)

    # MACD
    df = calculate_macd(df)
    
    # Candlestick Patterns
    df = calculate_candlestick_patterns(df)
    
    # FINAL SAFETY: Fill NaNs to prevent downstream crashes
    # RSI, Stoch, MACD can have NaNs at the start.
    # We forward fill then fill 0.
    df = df.ffill().fillna(0)
    
    return df

def calculate_trend_indicators(df_15m: pd.DataFrame) -> pd.DataFrame:
    """
    Calculates trend indicators on the higher timeframe (15m).
    """
    if len(df_15m) < 50:
        return df_15m
    
    # EMA
    df_15m['EMA_20'] = ta.ema(df_15m['Close'], length=20)
    df_15m['EMA_50'] = ta.ema(df_15m['Close'], length=50)

    # MACD for Trend Momentum
    df_15m = calculate_macd(df_15m)

    # ADX (14) for Trend Strength
    adx_df = ta.adx(df_15m['High'], df_15m['Low'], df_15m['Close'], length=14)
    if adx_df is not None:
         # pandas-ta returns columns like ADX_14, DMP_14, DMN_14
         # We just need ADX_14. Using column access by name dynamically or assuming default.
         # Based on standard: ADX_14
         adx_col = [c for c in adx_df.columns if c.startswith('ADX')][0]
         df_15m['ADX'] = adx_df[adx_col]
    
    # Choppiness Index for Regime
    df_15m = calculate_choppiness_index(df_15m)
    
    return df_15m

def calculate_rvol(df: pd.DataFrame, period: int = 20) -> pd.DataFrame:
    """Calculates Relative Volume."""
    df['RVOL'] = df['Volume'] / df['Vol_SMA']
    return df

def calculate_choppiness_index(df: pd.DataFrame, length: int = 14) -> pd.DataFrame:
    """Calculates Choppiness Index to determine Market Regime."""
    # Chop = 100 * Log10(Sum(ATR(1), n) / (Max(Hi, n) - Min(Lo, n))) / Log10(n)
    # Using pandas-ta
    chop = ta.chop(df['High'], df['Low'], df['Close'], length=length)
    if chop is not None:
        df['CHOP'] = chop
    return df

def calculate_macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    """Calculates MACD."""
    macd = ta.macd(df['Close'], fast=fast, slow=slow, signal=signal)
    if macd is not None:
        # Columns: MACD_12_26_9, MACDh_12_26_9 (Hist), MACDs_12_26_9 (Signal)
        # Dynamic lookup
        macd_col = [c for c in macd.columns if c.startswith('MACD_')][0]
        hist_col = [c for c in macd.columns if c.startswith('MACDh_')][0]
        sig_col = [c for c in macd.columns if c.startswith('MACDs_')][0]
        
        df['MACD'] = macd[macd_col]
        df['MACD_Hist'] = macd[hist_col]
        df['MACD_Signal'] = macd[sig_col]
    return df

def calculate_candlestick_patterns(df: pd.DataFrame) -> pd.DataFrame:
    """Detects simple candlestick patterns."""
    # Engulfing: (Open1 > Close1) and (Open < Close) and (Close > Open1) and (Open < Close1) [Bullish]
    # pandas-ta has 'cdl_pattern' or individual wrappers
    
    # We will use simple logic or pandas-ta's wrappers if available.
    # To save overhead of importing all patterns, we define simple vectorized logic for major ones.
    
    o, h, l, c = df['Open'], df['High'], df['Low'], df['Close']
    o1, c1 = o.shift(1), c.shift(1)
    
    # Bullish Engulfing
    # Previous Red, Current Green. Current Body Engulfs Previous Body.
    prev_red = c1 < o1
    curr_green = c > o
    engulfs = (c > o1) & (o < c1)
    df['Pattern_Bullish_Engulfing'] = prev_red & curr_green & engulfs
    
    # Bearish Engulfing
    prev_green = c1 > o1
    curr_red = c < o
    engulfs_bear = (c < o1) & (o > c1)
    df['Pattern_Bearish_Engulfing'] = prev_green & curr_red & engulfs_bear
    
    # Hammer (Bullish Reversal)
    # Small body near top, long lower wick (>= 2x body), small upper wick
    body = abs(c - o)
    # lower_wick = o - l if curr_green else c - l
    lower_wick = np.where(curr_green, o - l, c - l)
    # upper_wick = h - c if curr_green else h - o
    upper_wick = np.where(curr_green, h - c, h - o)
    
    is_hammer = (lower_wick >= 2 * body) & (upper_wick <= body * 0.5)
    df['Pattern_Hammer'] = is_hammer

    # Shooting Star (Bearish Reversal)
    # Small body near bottom, long upper wick
    is_shooting_star = (upper_wick >= 2 * body) & (lower_wick <= body * 0.5)
    df['Pattern_Shooting_Star'] = is_shooting_star
    
    return df
    
def calculate_daily_levels(df_daily: pd.DataFrame) -> dict:
    """
    Calculates Previous Day High (PDH), Previous Day Low (PDL), and Pivot Points.
    Expects a DataFrame with Daily candles.
    """
    if df_daily.empty:
        return {}
        
    last_day = df_daily.iloc[-1]
    # Check if last_day is "today" (incomplete) or "yesterday" (complete)?
    # Assuming df_daily includes *completed* candles or we use the last closed candle.
    # Usually for "Previous Day", we look at the last *closed* day.
    # If df_daily includes today (live), we use .iloc[-2].
    # But usually daily data fetching end=today returns up to yesterday.
    # If fetched with yfinance period='5d', the last row is Today (live).
    # So we should use .iloc[-2] if the timestamp matches today.
    # Safe bet: return the last *completed* candle's levels.
    
    # We will return the last two rows to be safe and let strategy decide?
    # No, strategy wants "Previous Day".
    # We will assume row -2 is Prev Day and row -1 is Current Day (Live).
    
    if len(df_daily) < 2:
        return {}
        
    prev_day = df_daily.iloc[-2]
    
    pdh = prev_day['High']
    pdl = prev_day['Low']
    pdc = prev_day['Close']
    
    # Standard Pivot Points
    pivot = (pdh + pdl + pdc) / 3
    r1 = (2 * pivot) - pdl
    s1 = (2 * pivot) - pdh
    
    return {
        'PDH': pdh,
        'PDL': pdl,
        'PDC': pdc,
        'Pivot': pivot,
        'R1': r1,
        'S1': s1
    }
