import json
import os
import logging
from datetime import datetime
from .database import DatabaseManager

class PortfolioManager:
    """
    Manages persistent state of the portfolio including:
    - Open positions (Synced with SQLite)
    - Daily P&L
    - Trade History (Stored in SQLite)
    - Cash / Capital
    """
    def __init__(self, config: dict):
        self.config = config
        self.data_dir = "data"
        self.file_path = os.path.join(self.data_dir, "portfolio.json")
        self.logger = logging.getLogger("IntradaySignals.Portfolio")
        self.db = DatabaseManager()
        
        # Default State (Account Level)
        # Trades are now managed by DB, but we keep 'open_positions' in memory for fast lookup
        self.state = {
            "capital": config.get("capital", 100000.0),
            "open_positions": {}, # Symbol -> Trade Dict (Intraday)
            "daily_pnl": 0.0,
            "trade_history": [], # Legacy: Kept for compatibility, but populated from DB if needed
            "swing_positions": {}, # Symbol -> Trade Dict (Swing)
            "swing_capital_allocation": config.get("swing_trading", {}).get("capital_allocation", 0.3),
            "swing_daily_pnl": 0.0,
            "swing_trade_history": [],
            "last_updated": datetime.now().isoformat()
        }
        
        self._ensure_data_dir()
        self.load_state()

    def _ensure_data_dir(self):
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)

    def load_state(self):
        """Loads account state from JSON and reconciles trades from DB."""
        # 1. Load Account State (Capital, PnL accumulation)
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, 'r') as f:
                    saved_state = json.load(f)
                    # Exclude trade lists from overwrite if we want to rely on DB? 
                    # For now, merge everything, then overwrite open_positions from DB
                    self.state.update(saved_state)
            except Exception as e:
                self.logger.error(f"Failed to load portfolio state: {e}")
        else:
            self.logger.info("No saved portfolio found. Starting fresh.")
            self.save_state()
            
        # 2. Reconcile Open Trades from DB
        # This ensures if we crash, we reload open status from DB
        db_trades = self.db.get_open_trades()
        self.state['open_positions'] = {}
        self.state['swing_positions'] = {}
        
        for t in db_trades:
            # Check strategy type to categorize
            # Assuming 'swing' strategy writes 'strategy' field differently or we infer?
            # Or we check if it was in 'swing_positions' list? 
            # Ideally, DB 'strategy' column helps.
            # Workaround: If timeframe is Daily or config says swing?
            # Let's rely on in-memory reconstruction. 
            # Actually, for robustness, we should trust the DB. 
            # If strategy is not stored, we might mix them up.
            # Assuming 'Trend Sniper' etc are intraday, 'Swing' is swing.
            
            # Temporary: Store in open_positions if not clearly swing
            # We need to distinguish. Future: Add 'type' col to DB.
            # For now, let's look at legacy 'strategy' field if we populate it.
            
            # Simple check: If existing in loaded JSON state, put it back
            # But that defeats the purpose of DB reliability.
            # Let's assume all are Intraday unless we add a specific tag.
            
            strategy_name = t.get('strategy', '')
            if 'Swing' in strategy_name or t.get('is_swing'):
                 self.state['swing_positions'][t['symbol']] = t
            else:
                 self.state['open_positions'][t['symbol']] = t
                 
        self.logger.info(f"State Loaded. Open Pos: {len(self.state['open_positions'])}, Swing: {len(self.state['swing_positions'])}")

    def save_state(self):
        """Saves Account State to JSON (Capital, PnL). Trades are in DB."""
        self.state['last_updated'] = datetime.now().isoformat()
        
        # We can optionally clear the trade lists in JSON to save space, 
        # but Dashboard might read JSON directly. 
        # For transition period, we keep writing them to JSON too.
        
        try:
            with open(self.file_path, 'w') as f:
                json.dump(self.state, f, indent=4)
        except Exception as e:
            self.logger.error(f"Failed to save portfolio state: {e}")

    def reset_daily_pnl(self):
        """Resets PnL at the start of a new day."""
        self.logger.info(f"Resetting Daily PnL. Intraday: {self.state['daily_pnl']:.2f}")
        self.state['daily_pnl'] = 0.0
        self.state['swing_daily_pnl'] = 0.0
        self.save_state()

    def add_position(self, trade: dict):
        """Adds a new open position."""
        symbol = trade['symbol']
        
        # DB Insert
        trade_id = self.db.add_trade(trade)
        trade['id'] = trade_id # Store DB ID
        
        self.state['open_positions'][symbol] = trade
        self.save_state()
        self.logger.info(f"Position Added: {symbol} {trade['side']} Qty: {trade['qty']}")

    def get_position(self, symbol: str):
        return self.state['open_positions'].get(symbol)

    def update_position(self, symbol: str, updates: dict):
        """Updates an existing position."""
        if symbol in self.state['open_positions']:
            trade = self.state['open_positions'][symbol]
            trade.update(updates)
            
            # DB Update
            if 'id' in trade:
                self.db.update_trade(trade['id'], updates)
                
            self.save_state()

    def close_position(self, symbol: str, exit_price: float, exit_time: str, reason: str):
        """Closes a position and updates P&L."""
        if symbol not in self.state['open_positions']:
            return

        trade = self.state['open_positions'].pop(symbol)
        trade['exit_price'] = exit_price
        trade['exit_time'] = exit_time
        trade['exit_reason'] = reason
        trade['status'] = "CLOSED"

        # Calculate PnL
        qty = trade['qty']
        entry_price = trade.get('entry_price', 0)
        
        if trade['side'] == "BUY":
            pnl = (exit_price - entry_price) * qty
        else:
            pnl = (entry_price - exit_price) * qty
            
        trade['pnl'] = pnl
        
        # Update State
        self.state['daily_pnl'] += pnl
        self.state['capital'] += pnl
        self.state['trade_history'].append(trade) # Keep strictly for JSON compatibility
        
        # DB Update
        if 'id' in trade:
            self.db.update_trade(trade['id'], {
                'exit_price': exit_price,
                'exit_time': exit_time,
                'reason': reason, # Append? Or overwrite?
                'status': 'CLOSED',
                'pnl': pnl
            })
        
        if len(self.state['trade_history']) > 1000:
             self.state['trade_history'] = self.state['trade_history'][-1000:]

        self.save_state()
        self.logger.info(f"Position Closed: {symbol} PnL: {pnl:.2f} ({reason})")
        return trade

    def get_stats(self):
        """Returns current intraday stats."""
        # Use DB for stats if possible, or fallback to memory
        # For consistency with "state", we use memory for live Dashboard PnL
        # But 'trade_count' could come from DB.
        
        history = self.state.get('trade_history', [])
        win_count = len([t for t in history if t.get('pnl', 0) > 0])
        total_closed = len(history)
        win_rate = (win_count / total_closed * 100) if total_closed > 0 else 0.0
        
        return {
            "daily_pnl": self.state['daily_pnl'],
            "open_count": len(self.state['open_positions']),
            "capital": self.state['capital'],
            "win_rate": win_rate,
            "trade_count": total_closed
        }
        
    # ==================== SWING TRADING METHODS ====================
    
    def add_swing_position(self, trade: dict):
        """Adds a new swing position."""
        symbol = trade['symbol']
        trade['is_swing'] = True # Tag for DB
        trade['strategy'] = 'Swing'
        
        # DB Insert
        trade_id = self.db.add_trade(trade)
        trade['id'] = trade_id
        
        self.state['swing_positions'][symbol] = trade
        self.save_state()
        self.logger.info(f"Swing Position Added: {symbol} {trade['side']} Qty: {trade['qty']}")

    def get_swing_position(self, symbol: str):
        return self.state['swing_positions'].get(symbol)

    def update_swing_position(self, symbol: str, updates: dict):
        """Updates an existing swing position."""
        if symbol in self.state['swing_positions']:
            trade = self.state['swing_positions'][symbol]
            trade.update(updates)
            
            if 'id' in trade:
                self.db.update_trade(trade['id'], updates)
                
            self.save_state()

    def close_swing_position(self, symbol: str, exit_price: float, exit_time: str, reason: str):
        """Closes a swing position and updates P&L."""
        if symbol not in self.state['swing_positions']:
            return

        trade = self.state['swing_positions'].pop(symbol)
        trade['exit_price'] = exit_price
        trade['exit_time'] = exit_time
        trade['exit_reason'] = reason
        trade['status'] = "CLOSED"

        qty = trade['qty']
        entry_price = trade.get('entry_price', 0)
        
        if trade['side'] == "BUY":
            pnl = (exit_price - entry_price) * qty
        else:
            pnl = (entry_price - exit_price) * qty
            
        trade['pnl'] = pnl
        
        self.state['swing_daily_pnl'] += pnl
        self.state['capital'] += pnl 
        self.state['swing_trade_history'].append(trade)
        
        # DB Update
        if 'id' in trade:
            self.db.update_trade(trade['id'], {
                'exit_price': exit_price,
                'exit_time': exit_time,
                'reason': reason,
                'status': 'CLOSED',
                'pnl': pnl
            })
        
        if len(self.state['swing_trade_history']) > 500:
            self.state['swing_trade_history'] = self.state['swing_trade_history'][-500:]

        self.save_state()
        self.logger.info(f"Swing Position Closed: {symbol} PnL: {pnl:.2f} ({reason})")
        return trade

    def get_swing_stats(self):
        """Returns current swing trading stats."""
        history = self.state.get('swing_trade_history', [])
        win_count = len([t for t in history if t.get('pnl', 0) > 0])
        total_closed = len(history)
        win_rate = (win_count / total_closed * 100) if total_closed > 0 else 0.0
        
        hold_durations = []
        for trade in history:
            if 'entry_time' in trade and 'exit_time' in trade:
                try:
                    entry = datetime.fromisoformat(trade['entry_time'])
                    exit_t = datetime.fromisoformat(trade['exit_time'])
                    hold_durations.append((exit_t - entry).days)
                except: pass
        
        avg_hold_days = sum(hold_durations) / len(hold_durations) if hold_durations else 0
        
        total_capital = self.state['capital']
        swing_allocation = self.state.get('swing_capital_allocation', 0.3)
        swing_capital = total_capital * swing_allocation
        
        return {
            "swing_daily_pnl": self.state.get('swing_daily_pnl', 0.0),
            "swing_open_count": len(self.state['swing_positions']),
            "swing_capital": swing_capital,
            "swing_win_rate": win_rate,
            "swing_trade_count": total_closed,
            "swing_avg_hold_days": avg_hold_days
        }

