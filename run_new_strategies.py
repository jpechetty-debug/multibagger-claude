import pandas as pd
import yaml
import sys
import os
import concurrent.futures
from datetime import datetime, timedelta
from tqdm import tqdm

# Add src to path
sys.path.append(os.path.join(os.getcwd(), 'src'))

from src.utils import setup_logger
from src.data_adapter import YFinanceAdapter
from src.strategy import StrategyEngine
from src.trade_manager import TradeManager
import logging

# Suppress noise
logging.getLogger("yfinance").setLevel(logging.WARNING)

def load_config():
    with open("config/config_example.yaml", "r") as f:
        if os.path.exists("config/config.yaml"):
            with open("config/config.yaml", "r") as f2:
                return yaml.safe_load(f2)
        return yaml.safe_load(f)

# Re-use process logic but accept strategy_mode override
def process_symbol_strategy(symbol, config, strategy_mode, start_date, end_date):
    config['strategy_mode'] = strategy_mode
    
    adapter = YFinanceAdapter()
    strategy = StrategyEngine(config)
    trade_manager = TradeManager(config)
    
    # Fetch Data
    df = adapter.fetch_data(symbol, "5m", start=start_date, end=end_date)
    start_date_daily = start_date - timedelta(days=365)
    df_daily = adapter.fetch_data(symbol, "1d", start=start_date_daily, end=end_date)
    
    if df.empty or df_daily.empty:
        return []

    # Resample
    df_15m = df.resample('15min').agg({'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'}).dropna()
    df_1h = df.resample('1h').agg({'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'}).dropna()
    
    # Indicators
    from src.indicators import calculate_indicators, calculate_trend_indicators
    import pandas_ta as ta
    df = calculate_indicators(df)
    df_15m = calculate_trend_indicators(df_15m)
    df_1h['EMA_50'] = ta.ema(df_1h['Close'], length=50)
    df_daily['EMA_50'] = ta.ema(df_daily['Close'], length=50)

    # Simulation
    start_idx = 60 # Ensure enough data
    prev_date = None
    
    for i in range(start_idx, len(df)):
        timestamp = df.index[i]
        current_date = timestamp.date()
        
        if prev_date is None or current_date != prev_date:
            trade_manager.reset_daily()
            prev_date = current_date
            
        relevant_15m = df_15m[df_15m.index < timestamp]
        if relevant_15m.empty: continue
        
        relevant_daily = df_daily[df_daily.index.date < timestamp.date()]
        daily_bias = "NEUTRAL"
        if not relevant_daily.empty:
            last_daily = relevant_daily.iloc[-1]
            ema_50 = last_daily.get('EMA_50', 0)
            if pd.notna(ema_50) and ema_50 > 0:
                daily_bias = "BULLISH" if last_daily['Close'] > ema_50 else "BEARISH"
                
        df_5m_slice = df.iloc[:i+1]
        relevant_1h = df_1h[df_1h.index < timestamp]
        
        signal = strategy.analyze(df_5m_slice, relevant_15m, market_regime="NEUTRAL", daily_bias=daily_bias, df_1h=relevant_1h)
        
        if signal['action'] != "None":
            trade_manager.process_signal(symbol, signal)
            
        price_dict = {symbol: {'High': df.iloc[i]['High'], 'Low': df.iloc[i]['Low'], 'Close': df.iloc[i]['Close']}}
        trade_manager.update_open_trades(price_dict, timestamp)
        trade_manager.update_pending_orders(price_dict, timestamp)

    trade_manager.close_all_positions({symbol: {'Close': df.iloc[-1]['Close']}}, df.index[-1], "Backtest End")
    return trade_manager.trades

def run_multi_strategy_backtest():
    strategies = ['BOLLINGER_RSI']
    test_symbols = ['RELIANCE.NS', 'TCS.NS', 'INFY.NS', 'HDFCBANK.NS', 'ICICIBANK.NS'] # Major liquid stocks
    
    config = load_config()
    end_date = datetime.now()
    start_date = end_date - timedelta(days=59)
    
    print(f"Starting Multi-Strategy Backtest on {len(test_symbols)} symbols...")
    print(f"Strategies: {strategies}")
    
    results = {}
    
    for strats in strategies:
        print(f"\n--- Running {strats} ---")
        all_trades = []
        
        with concurrent.futures.ProcessPoolExecutor() as executor:
            futures = {executor.submit(process_symbol_strategy, sym, config.copy(), strats, start_date, end_date): sym for sym in test_symbols}
            
            for future in tqdm(concurrent.futures.as_completed(futures), total=len(test_symbols), desc=strats):
                try:
                    trades = future.result()
                    all_trades.extend(trades)
                except Exception as e:
                    print(f"Error: {e}")
                    
        if all_trades:
            df_trades = pd.DataFrame(all_trades)
            total_pnl = df_trades['pnl'].sum()
            win_rate = len(df_trades[df_trades['pnl'] > 0]) / len(df_trades) * 100 if len(df_trades) > 0 else 0
            trades_count = len(df_trades)
            results[strats] = {'PnL': total_pnl, 'Trades': trades_count, 'WinRate': win_rate}
            
            df_trades.to_csv(f"results_{strats}.csv", index=False)
        else:
            results[strats] = {'PnL': 0.0, 'Trades': 0, 'WinRate': 0.0}

    print("\n=== Final Summary ===")
    print(f"{'Strategy':<25} | {'Trades':<10} | {'Win Rate':<10} | {'Total PnL':<15}")
    print("-" * 70)
    for s, res in results.items():
        print(f"{s:<25} | {res['Trades']:<10} | {res['WinRate']:<10.2f}% | {res['PnL']:<15.2f}")

if __name__ == "__main__":
    run_multi_strategy_backtest()
