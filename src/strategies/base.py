from abc import ABC, abstractmethod
import pandas as pd

class BaseStrategy(ABC):
    """
    Abstract Base Class for all trading strategies.
    Enforces a common interface for the Strategy Engine.
    """
    
    def __init__(self, config: dict):
        self.config = config
        self.name = "BaseStrategy"

    @abstractmethod
    def analyze(self, df_5m: pd.DataFrame, df_15m: pd.DataFrame, 
                market_regime: str = "NEUTRAL", daily_bias: str = "NEUTRAL", 
                df_1h: pd.DataFrame = None, df_daily: pd.DataFrame = None) -> dict:
        """
        Analyzes market data and returns a signal dictionary.
        
        Returns:
            dict: {
                'action': 'BUY' | 'SELL' | 'None',
                'reason': str,
                'current_price': float,
                'atr': float,
                'timestamp': pd.Timestamp,
                'sl_price': float,
                'target_r': float,
                'stop_entry_price': float,
                'indicators': dict
            }
        """
        pass

    def get_common_indicators(self, row, df):
        """Helper to extract common indicators safely."""
        return {
            'atr': row.get('ATR', 0),
            'rsi': row.get('RSI', 50),
            'close': row['Close']
        }
