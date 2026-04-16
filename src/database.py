import sqlite3
import json
import logging
from datetime import datetime
from pathlib import Path

class DatabaseManager:
    """
    Manages SQLite database interactions for the Trading Fortress.
    Handles: Trades, Signals, and Market Data Caching.
    """
    
    def __init__(self, db_path: str = "data/trading_bot.db"):
        self.db_path = db_path
        self.logger = logging.getLogger("IntradaySignals.DB")
        self._init_db()

    def _get_connection(self):
        """Creates a database connection with row factory."""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Initializes the database schema."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # OPTIMIZATION: Write-Ahead Logging for concurrency
            cursor.execute("PRAGMA journal_mode=WAL;")
            
            # 1. TRADES TABLE
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    qty INTEGER NOT NULL,
                    entry_time TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    sl REAL,
                    tp REAL,
                    exit_time TEXT,
                    exit_price REAL,
                    pnl REAL DEFAULT 0.0,
                    status TEXT DEFAULT 'OPEN',
                    strategy TEXT,
                    reason TEXT,
                    meta_data TEXT -- JSON for extra fields like highest_high, trailing details
                )
            """)
            
            # 2. SIGNALS TABLE (For Analysis)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    strategy TEXT,
                    action TEXT,
                    price REAL,
                    indicators TEXT -- JSON
                )
            """)
            
            # 3. EQUITY CURVE (Daily Snapshots)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS equity_curve (
                    date TEXT PRIMARY KEY,
                    capital REAL,
                    daily_pnl REAL,
                    open_positions INTEGER
                )
            """)

            conn.commit()
            self.logger.info("Database Schema Initialized.")
            
        except Exception as e:
            self.logger.error(f"Database Initialization Failed: {e}")
            raise
        finally:
            conn.close()

    # --- TRADE METHODS ---
    
    def add_trade(self, trade: dict) -> int:
        """
        Inserts a new trade. Returns the Trade ID.
        """
        conn = self._get_connection()
        try:
            meta = {k: v for k, v in trade.items() if k not in [
                'symbol', 'side', 'qty', 'entry_time', 'entry_price', 'sl', 'tp', 'status', 'strategy', 'reason'
            ]}
            
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO trades (symbol, side, qty, entry_time, entry_price, sl, tp, status, strategy, reason, meta_data)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                trade['symbol'], trade['side'], trade['qty'], 
                trade.get('entry_time', datetime.now().isoformat()),
                trade['entry_price'], trade.get('sl'), trade.get('tp'),
                trade.get('status', 'OPEN'), trade.get('strategy', 'Unknown'),
                trade.get('reason', ''), json.dumps(meta)
            ))
            conn.commit()
            return cur.lastrowid
        except Exception as e:
            self.logger.error(f"Error adding trade: {e}")
            return -1
        finally:
            conn.close()

    def update_trade(self, trade_id: int, updates: dict):
        """
        Updates an existing trade (e.g., closing it or updating SL).
        """
        conn = self._get_connection()
        try:
            sets = []
            values = []
            
            # Handle meta separately
            meta_updates = {}
            top_level_cols = ['exit_time', 'exit_price', 'pnl', 'status', 'sl', 'tp']
            
            for k, v in updates.items():
                if k in top_level_cols:
                    sets.append(f"{k} = ?")
                    values.append(v)
                else:
                    meta_updates[k] = v
            
            if meta_updates:
                # Need to read existing meta, merge, and write back? 
                # Or just keep it simple for now. 
                # SQLite JSON functions are an option, but let's do read-modify-write for compatibility.
                cur = conn.cursor()
                cur.execute("SELECT meta_data FROM trades WHERE id = ?", (trade_id,))
                row = cur.fetchone()
                if row:
                    current_meta = json.loads(row['meta_data']) if row['meta_data'] else {}
                    current_meta.update(meta_updates)
                    sets.append("meta_data = ?")
                    values.append(json.dumps(current_meta))

            if not sets:
                return

            values.append(trade_id)
            query = f"UPDATE trades SET {', '.join(sets)} WHERE id = ?"
            
            conn.execute(query, values)
            conn.commit()
            
        except Exception as e:
            self.logger.error(f"Error updating trade {trade_id}: {e}")
        finally:
            conn.close()

    def get_open_trades(self):
        """Returns all OPEN trades as a list of dicts."""
        conn = self._get_connection()
        trades = []
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM trades WHERE status = 'OPEN'")
            rows = cur.fetchall()
            for r in rows:
                t = dict(r)
                if t['meta_data']:
                    t.update(json.loads(t['meta_data']))
                trades.append(t)
        finally:
            conn.close()
        return trades

    def get_trade_history(self, limit=100):
        """Returns closed trades."""
        conn = self._get_connection()
        trades = []
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM trades WHERE status = 'CLOSED' ORDER BY exit_time DESC LIMIT ?", (limit,))
            rows = cur.fetchall()
            for r in rows:
                t = dict(r)
                if t['meta_data']:
                    t.update(json.loads(t['meta_data']))
                trades.append(t)
        finally:
            conn.close()
        return trades

    # --- SIGNAL METHODS ---
    
    def log_signal(self, signal: dict, symbol: str, strategy: str):
        conn = self._get_connection()
        try:
            conn.execute("""
                INSERT INTO signals (timestamp, symbol, strategy, action, price, indicators)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                signal.get('timestamp', datetime.now().isoformat()),
                symbol, strategy, signal['action'], signal.get('current_price'),
                json.dumps(signal.get('indicators', {}))
            ))
            conn.commit()
        except Exception as e:
            self.logger.error(f"Error logging signal: {e}")
        finally:
            conn.close()

    # --- STATS ---
    def get_todays_stats(self):
        """Calculates PnL for today."""
        conn = self._get_connection()
        try:
            # We assume ISO format timestamps
            today = datetime.now().strftime("%Y-%m-%d")
            cur = conn.cursor()
            
            # PnL from closed trades today
            cur.execute("""
                SELECT SUM(pnl) as total_pnl, COUNT(*) as count 
                FROM trades 
                WHERE status = 'CLOSED' AND exit_time LIKE ?
            """, (f"{today}%",))
            res = cur.fetchone()
            
            daily_pnl = res['total_pnl'] if res['total_pnl'] else 0.0
            trade_count = res['count']
            
            return {'daily_pnl': daily_pnl, 'trade_count': trade_count}
        finally:
            conn.close()
