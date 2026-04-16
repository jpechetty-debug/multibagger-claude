
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
            
    # FORCE SMC MODE
    cfg['strategy_mode'] = 'SMC_SCALP'
    return cfg

def process_smc_symbol(symbol, config, start_date, end_date):
    """
    SMC Version of process_symbol.
    """
    adapter = YFinanceAdapter()
    strategy = StrategyEngine(config)
    trade_manager = TradeManager(config)
    
    # 1. Fetch Data
    df = adapter.fetch_data(symbol, "5m", start=start_date, end=end_date)
    start_date_daily = start_date - timedelta(days=365)
    df_daily = adapter.fetch_data(symbol, "1d", start=start_date_daily, end=end_date)
    
    if df.empty or df_daily.empty:
        return []

    # 2. Resample
    df_15m = df.resample('15min').agg({
        'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'
    }).dropna()
    
    df_1h = df.resample('1h').agg({
        'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'
    }).dropna()
    
    # 3. Indicators
    from src.indicators import calculate_indicators, calculate_trend_indicators
    df = calculate_indicators(df)
    df_15m = calculate_trend_indicators(df_15m)
    df_1h['EMA_50'] = ta.ema(df_1h['Close'], length=50)
    df_daily['EMA_50'] = ta.ema(df_daily['Close'], length=50)

    # 4. Simulation Loop
    start_idx = 50
    prev_date = None
    
    for i in range(start_idx, len(df)):
        current_bar = df.iloc[i]
        timestamp = df.index[i]
        current_date = timestamp.date()
        
        # Reset Daily PnL
        if prev_date is None or current_date != prev_date:
            trade_manager.reset_daily()
            prev_date = current_date
            
        relevant_15m = df_15m[df_15m.index < timestamp]
        if relevant_15m.empty: continue
        
        relevant_daily = df_daily[df_daily.index.date < timestamp.date()]
        if relevant_daily.empty: continue
        
        relevant_1h = df_1h[df_1h.index < timestamp]

        df_5m_slice = df.iloc[:i+1]
        
        # Analyze
        signal = strategy.analyze(df_5m_slice, relevant_15m, df_1h=relevant_1h)
        # Note: We pass full dataframes, strategy handles last row extraction
        
        # Process
        if signal['action'] != "None":
            trade_manager.process_signal(symbol, signal)
            
        price_dict = {symbol: {'High': current_bar['High'], 'Low': current_bar['Low'], 'Close': current_bar['Close']}}
        trade_manager.update_open_trades(price_dict, timestamp)
        
    trade_manager.close_all_positions({symbol: {'Close': df.iloc[-1]['Close']}}, df.index[-1], "Backtest End")
    return trade_manager.trades

def run_smc_backtest():
    logger = setup_logger("IntradaySignals.BacktestSMC")
    config = load_config()
    
    symbols = config['symbols'][:30]
    
    # Run slightly shorter period for speed if needed, or full 60 days
    end_date = datetime.now()
    start_date = end_date - timedelta(days=59) 
    
    logger.info(f"Starting SMC Backtest: {start_date.date()} to {end_date.date()}")
    logger.info(f"Strategy: {config['strategy_mode']}")
    
    all_trades = []
    
    with concurrent.futures.ProcessPoolExecutor() as executor:
        futures = {executor.submit(process_smc_symbol, sym, config, start_date, end_date): sym for sym in symbols}
        
        for future in tqdm(concurrent.futures.as_completed(futures), total=len(symbols), desc="SMC Backtest"):
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
    df_trades.to_csv("smc_backtest_results.csv", index=False)
    
    # stats
    df_trades['pnl'] = pd.to_numeric(df_trades['pnl'])
    total = df_trades['pnl'].sum()
    win_cnt = len(df_trades[df_trades['pnl'] > 0])
    loss_cnt = len(df_trades[df_trades['pnl'] <= 0])
    win_rate = (win_cnt / len(df_trades)) * 100
    
    print("\n=== SMC Backtest Results ===")
    print(f"Trades: {len(df_trades)}")
    print(f"Total PnL: {total:.2f}")
    print(f"Win Rate: {win_rate:.2f}%")
    print(f"Winners: {win_cnt} | Losers: {loss_cnt}")
    
    avg_win = df_trades[df_trades['pnl'] > 0]['pnl'].mean() if win_cnt > 0 else 0
    avg_loss = df_trades[df_trades['pnl'] <= 0]['pnl'].mean() if loss_cnt > 0 else 0
    print(f"Avg Win: {avg_win:.2f} | Avg Loss: {avg_loss:.2f}")

if __name__ == "__main__":
    run_smc_backtest()
