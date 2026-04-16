import logging
import os
from src.database import DatabaseManager
from datetime import datetime

# Setup Logger
logging.basicConfig(level=logging.INFO)

def test_db():
    print("--- Testing Database Manager ---")
    
    # 1. Init
    db_path = "data/test_bot.db"
    if os.path.exists(db_path):
        os.remove(db_path)
        
    db = DatabaseManager(db_path)
    
    # 2. Add Trade
    trade = {
        'symbol': 'TATASTEEL',
        'side': 'BUY',
        'qty': 100,
        'entry_price': 150.0,
        'sl': 148.0,
        'tp': 154.0,
        'reason': 'Test Trade',
        'strategy': 'Trend Sniper'
    }
    
    tid = db.add_trade(trade)
    print(f"Trade Added. ID: {tid}")
    
    # 3. Read Open Trades
    open_trades = db.get_open_trades()
    print(f"Open Trades: {len(open_trades)}")
    assert len(open_trades) == 1
    assert open_trades[0]['symbol'] == 'TATASTEEL'
    
    # 4. Update Trade
    db.update_trade(tid, {'sl': 149.0, 'meta_data_test': 'foo'})
    
    # 5. Close Trade
    db.update_trade(tid, {
        'status': 'CLOSED',
        'exit_price': 155.0,
        'exit_time': datetime.now().isoformat(),
        'pnl': 500.0
    })
    
    # 6. Check History
    history = db.get_trade_history()
    print(f"History: {len(history)}")
    assert len(history) == 1
    assert history[0]['pnl'] == 500.0
    
    # 7. Log Signal
    signal = {
        'action': 'BUY',
        'current_price': 150.0,
        'indicators': {'RSI': 60}
    }
    db.log_signal(signal, 'INFY', 'RSI_MACD')
    print("Signal Logged.")
    
    print("--- DB Test Passed ---")

if __name__ == "__main__":
    test_db()
