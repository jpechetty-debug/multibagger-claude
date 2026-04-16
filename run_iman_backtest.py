
import pandas as pd
import yaml
import sys
import os
from datetime import datetime, timedelta
import concurrent.futures
from tqdm import tqdm

# Add src to path
sys.path.append(os.path.join(os.getcwd(), 'src'))

from src.utils import setup_logger
from src.data_adapter import YFinanceAdapter
from src.strategy import StrategyEngine
from src.trade_manager import TradeManager
import logging

logging.getLogger("yfinance").setLevel(logging.WARNING)

def load_config():
    # Load existing config or default
    if os.path.exists("config/config.yaml"):
        with open("config/config.yaml", "r") as f:
            cfg = yaml.safe_load(f)
    else:
        cfg = {} # Fallback
            
    # FORCE IMAN_RETRACEMENT MODE
    cfg['strategy_mode'] = 'IMAN_RETRACEMENT'
    
    # Ensure optimized params are used (though hardcoded in class for now, good to set in config if flexible)
    # The strategy class currently hardcodes target_r=2.0 in the code I modified.
    
    return cfg

def process_symbol(symbol, config, start_date, end_date):
    adapter = YFinanceAdapter()
    strategy = StrategyEngine(config)
    trade_manager = TradeManager(config)
    
    # 1. Fetch Data (Robust Method)
    try:
        import yfinance as yf
        # 60 days
        df = yf.download(symbol, period="59d", interval="5m", progress=False, auto_adjust=False)
        
        if df.empty: return []
            
        # Clean DF
        if isinstance(df.columns, pd.MultiIndex):
            if 'Close' in df.columns.get_level_values(0):
                df.columns = df.columns.get_level_values(0)
            else:
                 df.columns = df.columns.get_level_values(-1)
        
        df = df.loc[:, ~df.columns.duplicated()]
        if df.index.tz is None:
            df.index = df.index.tz_localize('UTC').tz_convert('Asia/Kolkata')
        else:
            df.index = df.index.tz_convert('Asia/Kolkata')
            
    except Exception as e:
        print(f"Error fetching {symbol}: {e}")
        return []

    # Daily Data for Trend Filter
    try:
        df_daily = yf.download(symbol, period="6mo", interval="1d", progress=False, auto_adjust=False)
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
    
    # Resample for 1H Filter (Critical for Optimized Strategy)
    df_1h = df.resample('1h').agg({
        'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'
    }).dropna()
    
    # Calc 1H EMA for Helper (Strategy might calculate it itself if passed df_1h, let's pre-calc to be safe)
    import pandas_ta as ta
    if not df_1h.empty:
        df_1h['EMA_50'] = ta.ema(df_1h['Close'], length=50)

    # 4. Simulation Loop
    start_idx = 50
    prev_date = None
    
    for i in range(start_idx, len(df)):
        current_bar = df.iloc[i]
        timestamp = df.index[i]
        current_date = timestamp.date()
        
        if prev_date is None or current_date != prev_date:
            trade_manager.reset_daily()
            prev_date = current_date
            
        current_df = df.iloc[:i+1]
        
        # Pass relevant 1H data (up to current time)
        # Strategy expects full df usually and takes last?
        # Let's pass full df_1h but strictly it should only peer into past.
        # But for backtest speed we pass full and Strategy checks `iloc[-1]`.
        # Wait, if we pass full 1H, `iloc[-1]` is the FUTURE relative to `i`?
        # YES. This is a lookahead bias risk.
        # We must slice 1H df to `timestamp`.
        
        relevant_1h = df_1h[df_1h.index <= timestamp]
        
        # Analyze
        # Strategy logic: df_1h.iloc[-1]. get('EMA_50')
        signal = strategy.analyze(current_df, None, df_1h=relevant_1h) # df_15m None is fine for this strategy
             
        # Process
        # Check Exits first?
        # Iman strategy relies on Limit orders usually in real life, but here we simulate Market on Signal.
        
        if signal['action'] != "None":
            trade_manager.process_signal(symbol, signal)
            
        # Update Open Trades
        price_dict = {symbol: {'High': current_bar['High'], 'Low': current_bar['Low'], 'Close': current_bar['Close']}}
        trade_manager.update_open_trades(price_dict, timestamp)
        
        # Check Pending Orders (Stop Limits)
        # Iman strategy logic might rely on market entry in this simple version or limits?
        # The logic returning 'stop_entry_price' would use pending orders.
        # The logic we wrote returns 'action'='BUY'/'SELL' directly with sl_price.
        # So it enters immediately.
        
        trade_manager.update_pending_orders(price_dict, timestamp)
        
    trade_manager.close_all_positions({symbol: {'Close': df.iloc[-1]['Close']}}, df.index[-1], "Backtest End")
    return trade_manager.trades

def run_iman_backtest():
    logger = setup_logger("IntradaySignals.BacktestIman")
    config = load_config()
    
    symbols = config.get('symbols', [])[:10] # Top 10
    if not symbols: symbols = ['RELIANCE.NS', 'TCS.NS', 'INFY.NS', 'HDFCBANK.NS']
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=60) 
    
    logger.info(f"Starting Iman Retracement Backtest (Optimized): {start_date.date()} to {end_date.date()}")
    
    all_trades = []
    
    with concurrent.futures.ProcessPoolExecutor() as executor:
        futures = {executor.submit(run_process_safe, sym, config, start_date, end_date): sym for sym in symbols}
        
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
    df_trades.to_csv("iman_backtest_results.csv", index=False)
    
    # stats
    if 'pnl' in df_trades.columns:
        df_trades['pnl'] = pd.to_numeric(df_trades['pnl'])
        total = df_trades['pnl'].sum()
        win_cnt = len(df_trades[df_trades['pnl'] > 0])
        loss_cnt = len(df_trades[df_trades['pnl'] <= 0])
        win_rate = (win_cnt / len(df_trades)) * 100 if len(df_trades) > 0 else 0
        
        print("\n=== Iman Retracement (Optimized) Backtest Results ===")
        print(f"Trades: {len(df_trades)}")
        print(f"Total PnL: {total:.2f}")
        print(f"Win Rate: {win_rate:.2f}%")
        print(f"Winners: {win_cnt} | Losers: {loss_cnt}")
        
        if win_cnt > 0:
            avg_win = df_trades[df_trades['pnl'] > 0]['pnl'].mean()
            print(f"Avg Win: {avg_win:.2f}")

# Wrapper to catch serialization errors in ProcessPool
def run_process_safe(sym, cfg, start, end):
    try:
        return process_symbol(sym, cfg, start, end)
    except Exception as e:
        print(f"Process Error {sym}: {e}")
        return []

if __name__ == "__main__":
    run_iman_backtest()
