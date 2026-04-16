import pandas as pd
import numpy as np
import pandas_ta as ta

def find_swings(df: pd.DataFrame, length: int = 5) -> pd.DataFrame:
    """
    Identifies Swing Highs and Swing Lows (Fractals).
    """       
    if len(df) < length: return df
    
    # 2 Left, 2 Right confirmation
    h = df['High']
    l = df['Low']
    
    # Vectorized shift comparisons
    # h vs h.shift(2) is the pivot
    # h.shift(2) > h.shift(3), h.shift(2) > h.shift(4) (Left)
    # h.shift(2) > h.shift(1), h.shift(2) > h (Right)
    # Alignment: We want the boolean at index of the pivot? 
    # The original code assigns at the current bar (Rightmost), checking back.
    # is_swing_high at index `i` means `i-2` was the high.
    
    is_swing_high = (
        (h.shift(2) > h.shift(3)) & 
        (h.shift(2) > h.shift(4)) & 
        (h.shift(2) > h.shift(1)) & 
        (h.shift(2) > h)
    )
    
    is_swing_low = (
        (l.shift(2) < l.shift(3)) & 
        (l.shift(2) < l.shift(4)) & 
        (l.shift(2) < l.shift(1)) & 
        (l.shift(2) < l)
    )
    
    df['Swing_High'] = is_swing_high
    df['Swing_Low'] = is_swing_low
    
    # Store the Price of the Swing
    # Note: The swing price occurred at shift(2), but we record it at the confirmation bar.
    df['Swing_High_Price'] = np.where(is_swing_high, h.shift(2), np.nan)
    df['Swing_Low_Price'] = np.where(is_swing_low, l.shift(2), np.nan)
    
    return df

def detect_structure_break(df: pd.DataFrame) -> dict:
    """
    Detects if the *current* candle has broken the most recent confirmed Swing High/Low.
    """
    if len(df) < 10:
        return {'type': 'NONE'}
        
    last_row = df.iloc[-1]
    
    # Optimization: ffill only the last valid values instead of full series if possible, 
    # but pandas ffill is fast. We just need the last valid swing BEFORE the current bar.
    
    # We want the last established swing.
    # 'Swing_High_Price' is NaN unless it's a confirmation bar.
    # ffill() propagates the last confirmed swing price forward.
    # iloc[-2] gets the status as of the PREVIOUS completed candle.
    
    # Check if 'Last_Swing_High' column exists to avoid re-computing ffill every time if we were persistent,
    # but we are stateless per call mostly.
    
    swings_high = df['Swing_High_Price'].ffill()
    swings_low = df['Swing_Low_Price'].ffill()
    
    last_swing_high = swings_high.iloc[-2] 
    last_swing_low = swings_low.iloc[-2]
    
    bos_type = "NONE"
    
    if pd.isna(last_swing_high) or pd.isna(last_swing_low):
        return {'type': 'NONE'}
        
    close = last_row['Close']
    
    if close > last_swing_high:
        bos_type = "BULLISH_BOS"
    elif close < last_swing_low:
        bos_type = "BEARISH_BOS"
        
    return {
        'type': bos_type,
        'level_broken': last_swing_high if bos_type == 'BULLISH_BOS' else last_swing_low
    }

def detect_liquidity_sweep(df: pd.DataFrame) -> dict:
    """
    Detects a 'Fakeout' or Liquidity Sweep.
    """
    if len(df) < 10:
        return {'type': 'NONE'}

    last_row = df.iloc[-1]
    
    # Use computed series to avoid re-ffill if passed, but safer to re-do or expect cols
    # Assuming lightweight
    last_swing_high = df['Swing_High_Price'].ffill().iloc[-2]
    last_swing_low = df['Swing_Low_Price'].ffill().iloc[-2]
    
    resp = {'type': 'NONE'}

    if pd.notna(last_swing_low):
        # Bullish Sweep (Grab Sell-Side Liquidity)
        # Low broke support, but Close rejected and closed back above
        if last_row['Low'] < last_swing_low and last_row['Close'] > last_swing_low:
            resp = {'type': 'BULLISH_SWEEP', 'level': last_swing_low}

    if pd.notna(last_swing_high):
        # Bearish Sweep (Grab Buy-Side Liquidity)
        # High broke resistance, but Close rejected and closed back below
        if last_row['High'] > last_swing_high and last_row['Close'] < last_swing_high:
            resp = {'type': 'BEARISH_SWEEP', 'level': last_swing_high}
            
    return resp

def detect_three_drives(df: pd.DataFrame) -> dict:
    """
    Detects a simplified Three Drives Pattern.
    """
    # Look at the last 3 Swing Highs or Lows.
    
    # Extract indices of swing highs
    # This filter is fast enough
    swing_highs = df[df['Swing_High']].tail(3)
    swing_lows = df[df['Swing_Low']].tail(3)
    
    if len(swing_highs) < 3 and len(swing_lows) < 3:
        return {'pattern': 'NONE'}
        
    pattern = 'NONE'
    
    # Check Bearish 3-Drive (3 Higher Highs)
    if len(swing_highs) == 3:
        h1, h2, h3 = swing_highs['Swing_High_Price'].values
        if h3 > h2 > h1:
             pattern = "BEARISH_3DRIVE"
             
    # Check Bullish 3-Drive (3 Lower Lows)
    if len(swing_lows) == 3:
        l1, l2, l3 = swing_lows['Swing_Low_Price'].values
        if l3 < l2 < l1:
            pattern = "BULLISH_3DRIVE"
            
    return {'pattern': pattern}

def detect_divergence(df: pd.DataFrame) -> dict:
    """
    Detects Regular Divergence between Price (Low/High) and RSI.
    """
    if 'RSI' not in df.columns:
        return {'type': 'NONE'}
        
    swing_highs = df[df['Swing_High']]
    swing_lows = df[df['Swing_Low']]
    
    div_type = 'NONE'
    
    # Check Bearish Divergence (Highs)
    if len(swing_highs) >= 2:
        # Last 2 Swing Highs
        last_2_h = swing_highs.iloc[-2:]
        p1 = last_2_h['Swing_High_Price'].iloc[0]
        p2 = last_2_h['Swing_High_Price'].iloc[1]
        
        # Corresponding RSI at those indices
        # Optimization: Access by index is fast
        r1 = df.at[last_2_h.index[0], 'RSI']
        r2 = df.at[last_2_h.index[1], 'RSI']
        
        # Price Higher High (p2 > p1) AND RSI Lower High (r2 < r1)
        if p2 > p1 and r2 < r1:
            div_type = "BEARISH_DIVERGENCE"
            
    # Check Bullish Divergence (Lows)
    if len(swing_lows) >= 2:
        last_2_l = swing_lows.iloc[-2:]
        p1 = last_2_l['Swing_Low_Price'].iloc[0]
        p2 = last_2_l['Swing_Low_Price'].iloc[1]
        
        r1 = df.at[last_2_l.index[0], 'RSI']
        r2 = df.at[last_2_l.index[1], 'RSI']
        
        # Price Lower Low (p2 < p1) AND RSI Higher Low (r2 > r1)
        if p2 < p1 and r2 > r1:
            div_type = "BULLISH_DIVERGENCE"
            
    return {'type': div_type}

def detect_imbalance(df: pd.DataFrame) -> pd.DataFrame:
    """
    Detects Fair Value Gaps (FVG) / Imbalances.
    """
    high = df['High']
    low = df['Low']
    
    # Bullish FVG (Gap between High[i-2] and Low[i])
    bull_fvg_cond = (low > high.shift(2))
    
    # Bearish FVG (Gap between Low[i-2] and High[i])
    bear_fvg_cond = (high < low.shift(2))
    
    df['FVG_Bullish'] = bull_fvg_cond
    df['FVG_Bearish'] = bear_fvg_cond
    
    # Calculate Gaps
    df['FVG_Top'] = np.where(bull_fvg_cond, low, np.where(bear_fvg_cond, low.shift(2), np.nan))
    df['FVG_Bottom'] = np.where(bull_fvg_cond, high.shift(2), np.where(bear_fvg_cond, high, np.nan))
    
    return df

def detect_order_blocks(df: pd.DataFrame) -> dict:
    """
    Detects Order Blocks near the current price.
    Vectorized implementation looking for recent unmitigated OBs.
    """
    if len(df) < 20: return {'type': 'NONE'}
    
    # We want to find if there is an Order Block in the recent history (e.g. last 15 candles)
    # that hasn't been brutally violated (though simple detection is asked).
    
    # 1. Identify Candles
    close = df['Close']
    open_p = df['Open']
    high = df['High']
    low = df['Low']
    
    is_down_candle = close < open_p
    is_up_candle = close > open_p
    
    # 2. Identify Displacement (Strong move after)
    # Check next 3 candles max/min
    # Using Rolling window looking FORWARD is hard in pandas without shifting back.
    # Shift back: Future(t) becomes Present(t-k)
    
    # Future High (max of next 3)
    # rolling(3).max() is backward looking.
    # To look forward: shift(-1).rolling(3).max().shift(-2)? No.
    # reversed_df.rolling(3).max()?
    # Easiest: Shift columns
    
    # Look ahead 3 bars
    next_high_1 = high.shift(-1)
    next_high_2 = high.shift(-2)
    next_high_3 = high.shift(-3)
    
    future_high_max = np.maximum(np.maximum(next_high_1, next_high_2), next_high_3)
    
    next_low_1 = low.shift(-1)
    next_low_2 = low.shift(-2)
    next_low_3 = low.shift(-3)
    
    future_low_min = np.minimum(np.minimum(next_low_1, next_low_2), next_low_3)
    
    # 3. Identify OB Conditions (Boolean Series)
    # Bullish OB: Down candle, then Future High > Current High
    bull_ob_mask = is_down_candle & (future_high_max > high)
    
    # Bearish OB: Up candle, then Future Low < Current Low
    bear_ob_mask = is_up_candle & (future_low_min < low)
    
    # 4. Search recent history (e.g., last 15 bars, excluding very recent 5 to allow formation)
    # Original logic: range(len(df)-2, len(df)-lookback, -1) -> skips last 1 (current forming)
    # And breaks on first find.
    
    # We look at the last 15 rows.
    lookback = 15
    # Slicing the series
    recent_bull = bull_ob_mask.iloc[-(lookback+5):-2] # Exclude very last few? Original skipped if i < 5? No, loop range. 
    # Loop was: for i in range(len(df)-2, len(df)-lookback, -1). 
    # Start: -2 (2nd to last). End: -15.
    
    # Let's iterate backwards over the boolean mask - simpler than full vector logic for "First logic"
    # But finding the index of the last True is fast.
    
    # Get indices where OB is True in the window
    recent_bull_indices = np.where(recent_bull)[0] 
    recent_bear_indices = np.where(bear_ob_mask.iloc[-(lookback+5):-2])[0]
    
    # We want the MOST RECENT one (closest to end).
    # Since we sliced the end of the DF, the last elements in array are the most recent in time.
    
    # Priority: Find the latest OB.
    
    ob_type = 'NONE'
    ob_top = 0.0
    ob_bottom = 0.0
    
    # Check if we have any Bullish OBs
    last_bull_idx = 7
    last_bear_idx = -1
    
    if len(recent_bull_indices) > 0:
        last_bull_rel_idx = recent_bull_indices[-1] # Index relative to slice
        # Map back to df index or just get row
        # Actually we just need which one is 'later'.
        if len(recent_bear_indices) > 0:
            last_bear_rel_idx = recent_bear_indices[-1]
            if last_bull_rel_idx > last_bear_rel_idx:
                ob_type = 'BULLISH_OB'
                # Get the row. 
                # Slice start index:
                slice_start = len(df) - (lookback+5)
                if slice_start < 0: slice_start = 0
                abs_idx = slice_start + last_bull_rel_idx
                row = df.iloc[abs_idx]
                ob_top = row['High']
                ob_bottom = row['Low']
            else:
                ob_type = 'BEARISH_OB'
                slice_start = len(df) - (lookback+5)
                if slice_start < 0: slice_start = 0
                abs_idx = slice_start + last_bear_rel_idx
                row = df.iloc[abs_idx]
                ob_top = row['High']
                ob_bottom = row['Low']
        else:
             ob_type = 'BULLISH_OB'
             slice_start = len(df) - (lookback+5)
             if slice_start < 0: slice_start = 0
             abs_idx = slice_start + last_bull_rel_idx
             row = df.iloc[abs_idx]
             ob_top = row['High']
             ob_bottom = row['Low']
    elif len(recent_bear_indices) > 0:
        ob_type = 'BEARISH_OB'
        last_bear_rel_idx = recent_bear_indices[-1]
        slice_start = len(df) - (lookback+5)
        if slice_start < 0: slice_start = 0
        abs_idx = slice_start + last_bear_rel_idx
        row = df.iloc[abs_idx]
        ob_top = row['High']
        ob_bottom = row['Low']
        
    return {
        'type': ob_type,
        'top': ob_top,
        'bottom': ob_bottom
    }

