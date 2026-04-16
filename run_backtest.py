import pandas as pd
import yaml
import sys
import os
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import pandas_ta as ta
import concurrent.futures
from tqdm import tqdm

# Add src to path
sys.path.append(os.path.join(os.getcwd(), 'src'))

from src.utils import setup_logger
from src.data_adapter import YFinanceAdapter
from src.strategy import StrategyEngine
from src.trade_manager import TradeManager
import logging

# Set logging for third party libs to WARNING to suppress noise
logging.getLogger("yfinance").setLevel(logging.WARNING)

def load_config():
    with open("config/config_example.yaml", "r") as f:
        if os.path.exists("config/config.yaml"):
            with open("config/config.yaml", "r") as f2:
                return yaml.safe_load(f2)
        return yaml.safe_load(f)

def process_symbol(symbol, config, start_date, end_date):
    """
    Independent process function for a single symbol.
    Returns list of trades.
    """
    # Re-init components inside process (avoids pickle issues with complex objects)
    
    adapter = YFinanceAdapter() # Uses cache now
    strategy = StrategyEngine(config)
    trade_manager = TradeManager(config) # clean state
    
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
        
        # Reset Daily (logic in TradeManager handles "daily PnL" limit, but here we just simulate)
        if prev_date is None or current_date != prev_date:
            trade_manager.reset_daily()
            prev_date = current_date
            
        # Context Data
        relevant_15m = df_15m[df_15m.index < timestamp]
        if relevant_15m.empty: continue
        
        # Daily Bias
        relevant_daily = df_daily[df_daily.index.date < timestamp.date()]
        daily_bias = "NEUTRAL"
        if not relevant_daily.empty:
            last_daily = relevant_daily.iloc[-1]
            ema_50 = last_daily.get('EMA_50', 0)
            if pd.notna(ema_50) and ema_50 > 0:
                daily_bias = "BULLISH" if last_daily['Close'] > ema_50 else "BEARISH"
                
        # Slices
        df_5m_slice = df.iloc[:i+1]
        df_15m_slice = relevant_15m
        relevant_1h = df_1h[df_1h.index < timestamp]
        
        # Analyze
        signal = strategy.analyze(df_5m_slice, df_15m_slice, market_regime="NEUTRAL", daily_bias=daily_bias, df_1h=relevant_1h)
        
        # Process
        if signal['action'] != "None":
            trade_manager.process_signal(symbol, signal)
            
        price_dict = {symbol: {'High': current_bar['High'], 'Low': current_bar['Low'], 'Close': current_bar['Close']}}
        trade_manager.update_open_trades(price_dict, timestamp)
        trade_manager.update_pending_orders(price_dict, timestamp)

    # Close All at End
    trade_manager.close_all_positions({symbol: {'Close': df.iloc[-1]['Close']}}, df.index[-1], "Backtest End")
    
    return trade_manager.trades

def run_backtest():
    logger = setup_logger("IntradaySignals.Backtest")
    config = load_config()
    
    symbols = config['symbols']
    # Limit symbols for testing speed if needed, or run full
    symbols = symbols[:10] 
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=59) # 5m constraint
    
    logger.info(f"Starting Parallel Backtest from {start_date.date()} to {end_date.date()}")
    logger.info(f"Symbols: {len(symbols)}")
    
    all_trades = []
    
    # Run Parallel
    # Using ProcessPoolExecutor allows utilizing multiple cores
    # max_workers = os.cpu_count() or 4
    
    with concurrent.futures.ProcessPoolExecutor() as executor:
        # Submit all tasks
        futures = {executor.submit(process_symbol, sym, config, start_date, end_date): sym for sym in symbols}
        
        # Progress Bar
        for future in tqdm(concurrent.futures.as_completed(futures), total=len(symbols), desc="Backtesting"):
            sym = futures[future]
            try:
                trades = future.result()
                all_trades.extend(trades)
            except Exception as e:
                logger.error(f"Error processing {sym}: {e}")
                
    # Generate Report
    if not all_trades:
        logger.warning("No trades generated.")
        return

    df_trades = pd.DataFrame(all_trades)
    df_trades.to_csv("sample_output.csv", index=False)
    logger.info(f"Saved trade logs to sample_output.csv with {len(df_trades)} trades.")
    
    total_pnl = df_trades['pnl'].sum()
    win_rate = len(df_trades[df_trades['pnl'] > 0]) / len(df_trades) * 100
    
    print("\n=== Backtest Summary ===")
    print(f"Total P&L: {total_pnl:.2f}")
    print(f"Total Trades: {len(df_trades)}")
    print(f"Win Rate: {win_rate:.2f}%")
    
    # Sort by time for equity curve
    df_trades['exit_time'] = pd.to_datetime(df_trades['exit_time'])
    df_trades = df_trades.sort_values('exit_time')
    
    df_trades['cumulative_pnl'] = df_trades['pnl'].cumsum() + config['capital']
    
    plt.figure(figsize=(10, 6))
    plt.plot(df_trades['cumulative_pnl'].values, label='Equity Curve')
    plt.title("Backtest Equity Curve")
    plt.xlabel("Trade Count")
    plt.ylabel("Capital")
    plt.legend()
    plt.savefig("reports/equity_curve.png")
    logger.info("Saved equity curve to reports/equity_curve.png")

if __name__ == "__main__":
    # Windows support for multiprocessing
    run_backtest()
