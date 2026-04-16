import unittest
import pandas as pd
import sys
import os

# Add src to path
sys.path.append(os.path.join(os.getcwd(), 'src'))

from src.indicators import calculate_indicators
from src.strategy import StrategyEngine
from src.trade_manager import TradeManager

class TestIntradaySignals(unittest.TestCase):
    def test_imports(self):
        """Test that modules import correctly."""
        self.assertTrue(True)

    def test_indicators(self):
        """Test indicator calculation on dummy data."""
        data = {
            'Open': [100, 101, 102] * 20,
            'High': [105, 106, 107] * 20,
            'Low': [95, 96, 97] * 20,
            'Close': [100, 102, 104] * 20,
            'Volume': [1000, 1500, 2000] * 20
        }
        df = pd.DataFrame(data)
        df_ind = calculate_indicators(df)
        self.assertIn('RSI', df_ind.columns)
        self.assertIn('VWAP', df_ind.columns)
        self.assertIn('RVOL', df_ind.columns)

if __name__ == '__main__':
    unittest.main()
