import pandas as pd
import numpy as np
from scipy.signal import argrelextrema

class PatternScanner:
    """
    Identifies classic chart patterns given a DataFrame with High/Low/Close data.
    Supported Patterns:
    - Double Top / Double Bottom
    - Head and Shoulders
    """
    
    def __init__(self, tolerance=0.02):
        self.tolerance = tolerance # Tolerance for price similarity (e.g., 2%)

    def scan_pattern(self, df: pd.DataFrame, window=5) -> dict:
        """
        Scans for patterns in the provided DataFrame.
        Returns a dictionary of found patterns and their indices.
        """
        if len(df) < 50:
            return {'patterns': []}
            
        patterns = []
        
        # 1. Find Local Extrema (Peaks and Troughs)
        # Using simple local Max/Min
        # Order=5 means 5 bars on each side -> 11 bar window
        order = window 
        
        # Peaks (Highs)
        peaks_idx = argrelextrema(df['High'].values, np.greater, order=order)[0]
        # Troughs (Lows)
        troughs_idx = argrelextrema(df['Low'].values, np.less, order=order)[0]
        
        peaks = df.iloc[peaks_idx][['High']]
        troughs = df.iloc[troughs_idx][['Low']]
        
        # We need at least a few extrema to match patterns
        if len(peaks) < 3 or len(troughs) < 3:
            return {'patterns': []}

        patterns.extend(self._find_double_top(peaks, df))
        patterns.extend(self._find_double_bottom(troughs, df))
        patterns.extend(self._find_double_bottom(troughs, df))
        patterns.extend(self._find_head_shoulders(peaks, df))
        patterns.extend(self._find_triangles(peaks, troughs, df))
        patterns.extend(self._find_flags(df))
        patterns.extend(self._find_triangles(peaks, troughs, df))
        patterns.extend(self._find_flags(df))

        # Filter for latest only? Or return all?
        # Usually valid if the pattern completed recently.
        # Let's return the most recent valid pattern found.
        
        return {'patterns': patterns}

    def _is_approx_equal(self, p1, p2):
        return abs(p1 - p2) <= (p1 * self.tolerance)

    def _find_double_top(self, peaks, df):
        found = []
        # Check last 2 peaks
        if len(peaks) >= 2:
            p2 = peaks.iloc[-1]
            p1 = peaks.iloc[-2]
            
            # Times must be somewhat recent
            # Check price similarity
            if self._is_approx_equal(p1['High'], p2['High']):
                # Find Trough between them
                t1_idx = p1.name
                t2_idx = p2.name
                
                # Get low in between
                interval = df.loc[t1_idx:t2_idx]
                if len(interval) > 0:
                    neckline = interval['Low'].min()
                    
                    found.append({
                        'pattern': 'Double Top',
                        'p1': (t1_idx, p1['High']),
                        'p2': (t2_idx, p2['High']),
                        'neckline': neckline
                    })
        return found
        
    def _find_double_bottom(self, troughs, df):
        found = []
        if len(troughs) >= 2:
            t2 = troughs.iloc[-1]
            t1 = troughs.iloc[-2]
            
            if self._is_approx_equal(t1['Low'], t2['Low']):
                # Find Peak between them
                idx1 = t1.name
                idx2 = t2.name
                
                interval = df.loc[idx1:idx2]
                if len(interval) > 0:
                    neckline = interval['High'].max()
                    
                    found.append({
                        'pattern': 'Double Bottom',
                        't1': (idx1, t1['Low']),
                        't2': (idx2, t2['Low']),
                        'neckline': neckline
                    })
        return found

    def _find_head_shoulders(self, peaks, df):
        found = []
        if len(peaks) >= 3:
            # P3 = Right Shoulder, P2 = Head, P1 = Left Shoulder
            p3 = peaks.iloc[-1]
            p2 = peaks.iloc[-2]
            p1 = peaks.iloc[-3]
            
            # Head must be higher than shoulders
            if p2['High'] > p1['High'] and p2['High'] > p3['High']:
                # Shoulders approx equal
                if self._is_approx_equal(p1['High'], p3['High']):
                    found.append({
                        'pattern': 'Head and Shoulders',
                        'left': (p1.name, p1['High']),
                        'head': (p2.name, p2['High']),
                        'right': (p3.name, p3['High'])
                    })
        return found
