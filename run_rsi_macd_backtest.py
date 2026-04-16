
import pandas as pd
import yaml
import sys
import os
from datetime import datetime, timedelta
import pandas_ta as ta
import concurrent.futures
from tqdm import tqdm
import matplotlib.pyplot as plt

# Add src to path
sys.path.append(os.path.join(os.getcwd(), 'src'))

from src.utils import setup_logger
from src.data_adapter import YFinanceAdapter
from src.strategy import StrategyEngine
from src.trade_manager import TradeManager
import logging

logging.getLogger("yfinance").setLevel(logging.WARNING)

def load_config():
    with open("config/config_example.yaml", "r") as f:
        if os.path.exists("config/config.yaml"):
            with open("config/config.yaml", "r") as f2:
                cfg = yaml.safe_load(f2)
        else:
            cfg = yaml.safe_load(f)
            
    # FORCE RSI MACD CROSSOVER MODE
    cfg['strategy_mode'] = 'RSI_MACD_CROSSOVER'
    
    # Ensure params are set if not in config
    if 'TIMEPERIOD_FAST' not in cfg: cfg['TIMEPERIOD_FAST'] = 12
    if 'TIMEPERIOD_SLOW' not in cfg: cfg['TIMEPERIOD_SLOW'] = 26
    if 'TIMEPERIOD_SIGNAL' not in cfg: cfg['TIMEPERIOD_SIGNAL'] = 9
    if 'TIMEPERIOD_RSI' not in cfg: cfg['TIMEPERIOD_RSI'] = 14
    if 'OVERSOLD_VALUE' not in cfg: cfg['OVERSOLD_VALUE'] = 30
    if 'OVERBOUGHT_VALUE' not in cfg: cfg['OVERBOUGHT_VALUE'] = 70
    
    return cfg

def process_symbol(symbol, config, start_date, end_date):
    """
    Standard process symbol for backtest.
    """
    adapter = YFinanceAdapter()
    strategy = StrategyEngine(config)
    trade_manager = TradeManager(config)
    
    # 1. Fetch Data
    # robust fetch against date skew: use period='59d' directly
    try:
        import yfinance as yf
        df = yf.download(symbol, period="59d", interval="5m", progress=False, auto_adjust=False)
        
        if df.empty:
            return []
            
        # Clean DF (copied from Adapter logic)
        if isinstance(df.columns, pd.MultiIndex):
            if 'Close' in df.columns.get_level_values(0):
                df.columns = df.columns.get_level_values(0)
            else:
                 df.columns = df.columns.get_level_values(-1)
        
        df = df.loc[:, ~df.columns.duplicated()]
        
        # Rename standard cols
        df.rename(columns={'Adj Close': 'Adj Close'}, inplace=True) # Ensure consistency if needed
        
        # Timezone
        if df.index.tz is None:
            df.index = df.index.tz_localize('UTC').tz_convert('Asia/Kolkata')
        else:
            df.index = df.index.tz_convert('Asia/Kolkata')
            
    except Exception as e:
        print(f"Error fetching {symbol}: {e}")
        return []

    # daily for higher timeframe filters
    # we can try fetching daily with period too
    try:
        df_daily = yf.download(symbol, period="1y", interval="1d", progress=False, auto_adjust=False)
        if not df_daily.empty:
            if isinstance(df_daily.columns, pd.MultiIndex):
                if 'Close' in df_daily.columns.get_level_values(0):
                    df_daily.columns = df_daily.columns.get_level_values(0)
                else:
                    df_daily.columns = df_daily.columns.get_level_values(-1)
            df_daily = df_daily.loc[:, ~df_daily.columns.duplicated()]
            if df_daily.index.tz is None:
                df_daily.index = df_daily.index.tz_localize('UTC').tz_convert('Asia/Kolkata')
            else:
                df_daily.index = df_daily.index.tz_convert('Asia/Kolkata')
    except:
        df_daily = pd.DataFrame()
    
    if df.empty:
        return []

    # 2. Resample (BaseStrategy interface expects these, though Crossover might only use 5m by default)
    # Creating them anyway to adhere to interface.
    df_15m = df.resample('15min').agg({
        'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'
    }).dropna()
    
    df_1h = df.resample('1h').agg({
        'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'
    }).dropna()
    
    # 3. Indicators
    # We call standard indicators calc, which adds some but maybe not the specific ones in our strategy class
    # The strategy class calculates its own indicators in analyze() usually or expects them.
    # Our new strategy calculates them inside analyze().
    # But let's run the standard helper just in case common ones like ATR are used.
    from src.indicators import calculate_indicators
    df = calculate_indicators(df)
    
    # 4. Simulation Loop
    start_idx = 100 # ample warmup
    prev_date = None
    
    trades = []
    
    # Simple loop
    for i in range(start_idx, len(df)):
        current_bar = df.iloc[i]
        timestamp = df.index[i]
        current_date = timestamp.date()
        
        # Reset Daily PnL
        if prev_date is None or current_date != prev_date:
            trade_manager.reset_daily()
            prev_date = current_date
            
        # Slicing
        # We pass the whole DF up to i
        # To simulate correctly, we shouldn't see future?
        # Strategy analyze usually takes the whole dataframe and looks at iloc[-1]
        # So we pass df.iloc[:i+1]
        
        current_df = df.iloc[:i+1]
        
        # Analyze
        signal = strategy.analyze(current_df, df_15m, df_1h=df_1h)
             
        # Process
        # Check for specific exit signals first from the strategy
        if 'exit_signal' in signal:
            if signal['exit_signal'] == 'EXIT_BUY':
                # Close Longs
                trade_manager.close_all_positions_by_type(symbol, 'BUY', current_bar['Close'], timestamp, "Strategy Exit Signal")
            elif signal['exit_signal'] == 'EXIT_SELL':
                # Close Shorts
                trade_manager.close_all_positions_by_type(symbol, 'SELL', current_bar['Close'], timestamp, "Strategy Exit Signal")

        if signal['action'] != "None":
            trade_manager.process_signal(symbol, signal)
            
        # Update Open Trades (Stop Loss / Target checks)
        price_dict = {symbol: {'High': current_bar['High'], 'Low': current_bar['Low'], 'Close': current_bar['Close']}}
        trade_manager.update_open_trades(price_dict, timestamp)
        
    trade_manager.close_all_positions({symbol: {'Close': df.iloc[-1]['Close']}}, df.index[-1], "Backtest End")
    return trade_manager.trades

def run_rsi_macd_backtest():
    logger = setup_logger("IntradaySignals.BacktestRsiMacd")
    config = load_config()
    
    symbols = config.get('symbols', ['RELIANCE.NS', 'TCS.NS', 'INFY.NS', 'HDFCBANK.NS', 'ICICIBANK.NS'])[:10] # Test top 10
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=60) 
    
    logger.info(f"Starting RSI MACD Crossover Backtest: {start_date.date()} to {end_date.date()}")
    
    all_trades = []
    
    # Sequential for debugging potential errors easily, or Parallel
    # Parallel is better.
    with concurrent.futures.ProcessPoolExecutor() as executor:
        futures = {executor.submit(process_symbol, sym, config, start_date, end_date): sym for sym in symbols}
        
        for future in tqdm(concurrent.futures.as_completed(futures), total=len(symbols), desc="Backtest"):
            sym = futures[future]
            try:
                trades = future.result()
                all_trades.extend(trades)
            except Exception as e:
                logger.error(f"Error {sym}: {e}")
                
    if not all_trades:
        print("No Trades Generated.")
        return

    df_trades = pd.DataFrame(all_trades)
    df_trades.to_csv("rsi_macd_backtest_results.csv", index=False)
    
    # stats
    if 'pnl' in df_trades.columns:
        df_trades['pnl'] = pd.to_numeric(df_trades['pnl'])
        total = df_trades['pnl'].sum()
        win_cnt = len(df_trades[df_trades['pnl'] > 0])
        loss_cnt = len(df_trades[df_trades['pnl'] <= 0])
        win_rate = (win_cnt / len(df_trades)) * 100 if len(df_trades) > 0 else 0
        
        print("\n=== RSI MACD Backtest Results ===")
        print(f"Trades: {len(df_trades)}")
        print(f"Total PnL: {total:.2f}")
        print(f"Win Rate: {win_rate:.2f}%")
        print(f"Winners: {win_cnt} | Losers: {loss_cnt}")
        
        if win_cnt > 0:
            avg_win = df_trades[df_trades['pnl'] > 0]['pnl'].mean()
            print(f"Avg Win: {avg_win:.2f}")
        
        if loss_cnt > 0:
            avg_loss = df_trades[df_trades['pnl'] <= 0]['pnl'].mean()
            print(f"Avg Loss: {avg_loss:.2f}")

if __name__ == "__main__":
    run_rsi_macd_backtest()
