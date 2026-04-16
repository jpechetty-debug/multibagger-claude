import pandas as pd
import logging
from .strategies import TrendSniperStrategy, RsiMacdStrategy, SMCStrategy, StochMacdStrategy, ImanRetracementStrategy, CombinedStrategy, RsiMacdCrossoverStrategy, MaCrossoverStrategy, EmaMacdMfiStrategy, SuperTrendRsiPsarStrategy, SmaPsarStrategy, BollingerRsiStrategy, MacdTrendlineStrategy, SmcRefinedStrategy, DoubleInsideBarStrategy, ScalpConfluenceStrategy

class StrategyEngine:
    """
    Strategy Factory:
    Loads the appropriate strategy implementation based on configuration.
    Acts as a facade to the specific strategy class.
    """
    
    def __init__(self, config: dict):
        self.config = config
        self.logger = logging.getLogger("IntradaySignals.Strategy")
        self.strategy_mode = config.get('strategy_mode', 'TREND_SNIPER') 
        
        self.strategies = {
            'TREND_SNIPER': TrendSniperStrategy,
            'RSI_MACD': RsiMacdStrategy,
            'SMC_SCALP': SMCStrategy,
            'STOCH_MACD': StochMacdStrategy,
            'BORING_MACD': ImanRetracementStrategy,
            'BEST_MACD': ImanRetracementStrategy,
            'WARRIOR_MACD': ImanRetracementStrategy,
            'BRAHMASTRA': ImanRetracementStrategy,
            'CANDLE_BREAKOUT': ImanRetracementStrategy,
            'DHAN_SCALP': ImanRetracementStrategy,
            'ORB_STRATEGY': ImanRetracementStrategy,
            'IMAN_RETRACEMENT': ImanRetracementStrategy,
            'THREE_EMA': ImanRetracementStrategy,
            'COMBINED': CombinedStrategy,
            'RSI_MACD_CROSSOVER': RsiMacdCrossoverStrategy,
            'MA_CROSSOVER': MaCrossoverStrategy,
            'EMA_MACD_MFI': EmaMacdMfiStrategy,
            'SUPERTREND_RSI_PSAR': SuperTrendRsiPsarStrategy,
            'SMA_PSAR': SmaPsarStrategy,
            'SMC_REFINED': SmcRefinedStrategy,
            'MACD_TRENDLINE': MacdTrendlineStrategy,
            'DOUBLE_INSIDE_BAR': DoubleInsideBarStrategy,
            'SCALP_CONFLUENCE': ScalpConfluenceStrategy
        }
        
        # Instantiate Selected Strategy
        strategy_cls = self.strategies.get(self.strategy_mode, TrendSniperStrategy)
        try:
            self.strategy = strategy_cls(config)
            self.logger.info(f"Loaded Strategy: {self.strategy.name}")
        except Exception as e:
            self.logger.error(f"Failed to load strategy {self.strategy_mode}: {e}")
            self.strategy = TrendSniperStrategy(config) # Fallback

    def analyze(self, df_5m: pd.DataFrame, df_15m: pd.DataFrame, 
                market_regime: str = "NEUTRAL", daily_bias: str = "NEUTRAL", 
                df_1h: pd.DataFrame = None, df_daily: pd.DataFrame = None) -> dict:
        """
        Delegates analysis to the loaded strategy instance.
        """
        try:
            return self.strategy.analyze(
                df_5m, df_15m, 
                market_regime=market_regime, 
                daily_bias=daily_bias, 
                df_1h=df_1h, 
                df_daily=df_daily
            )
        except Exception as e:
            self.logger.error(f"Error in strategy execution: {e}")
            return {'action': 'None', 'reason': f'Error: {str(e)}'}

