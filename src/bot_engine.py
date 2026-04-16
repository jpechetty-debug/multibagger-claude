import logging
import time
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
import concurrent.futures
import threading
from tqdm import tqdm

from .utils import setup_logger, get_current_time, round_to_tick
from .data_adapter import YFinanceAdapter, LivePoller
from .strategy import StrategyEngine
from .swing_strategy import SwingStrategyEngine  # NEW: Swing strategy
from .swing_scanner import SwingScanner  # NEW: Swing scanner
from .portfolio import PortfolioManager
from .risk_engine import RiskEngine
from .telegram_bot import TelegramBot
from .trade_manager import TradeManager # Loop logic mainly in here for trade lifecycle
from .market_scanner import MarketScanner

class BotEngine:
    """
    Main Orchestrator for the Trading Bot.
    """
    def __init__(self, config: dict):
        self.config = config
        self.logger = logging.getLogger("IntradaySignals.Engine")
        
        # Initialize Components
        self.adapter = LivePoller(YFinanceAdapter())
        self.strategy = StrategyEngine(config)
        self.portfolio = PortfolioManager(config)
        self.risk_engine = RiskEngine(config, self.portfolio)
        self.bot = TelegramBot(config['telegram']['bot_token'], config['telegram']['chat_id'], config['telegram']['enabled'])
        self.scanner = MarketScanner(config)
        
        # Trade Manager (Helper for logic, but state is in Portfolio)
        # We might need to adapt TradeManager to use Portfolio or move logic here.
        # For this refactor, let's keep TradeManager as a calculator but use Portfolio for storage.
        # Actually, RiskEngine + Portfolio replaces most of TradeManager's state responsibilities.
        # We will implement the loop logic directly here using the new components.
        
        self._register_commands()
        self.symbols = config['symbols']
        self.pending_orders = [] # Store Stop Limit Orders
        
        # Swing Trading Components
        swing_enabled = config.get('swing_trading', {}).get('enabled', False)
        if swing_enabled:
            self.swing_strategy = SwingStrategyEngine(config)
            self.swing_scanner = SwingScanner(config)
            self.swing_symbols = []  # Separate list for swing candidates
        else:
            self.swing_strategy = None
            self.swing_scanner = None
            self.swing_symbols = []
        
        self.scheduler = BackgroundScheduler(timezone=config['timezone'])
        self.lock = threading.Lock() # Thread Safety for Parallel Execution
        self.last_regime = "NEUTRAL" # Init regime state
        self.market_stats = {"gainers": [], "losers": []}

    def _register_commands(self):
        """Registers Telegram Commands."""
        self.bot.register_command("/stats", self._cmd_stats)
        self.bot.register_command("/positions", self._cmd_positions)
        self.bot.register_command("/freeze", self._cmd_freeze)
        self.bot.register_command("/unfreeze", self._cmd_unfreeze)
        self.bot.register_command("/capital", self._cmd_capital)
        self.bot.register_command("/scan", self._cmd_scan)

    # --- Command Handlers ---
    def _cmd_scan(self):
        self.run_scanner()
        return f"Scanner Triggered. Symbols: {self.symbols}"

    def _cmd_stats(self):
        with self.lock:
            stats = self.portfolio.get_stats()
        return (f"📊 *Daily Stats*\n"
                f"PnL: {stats['daily_pnl']:.2f}\n"
                f"Capital: {stats['capital']:.2f}\n"
                f"Open Positions: {stats['open_count']}")

    def _cmd_positions(self):
        with self.lock:
            pos = self.portfolio.state['open_positions']
            if not pos:
                return "No open positions."
            
            msg = "Open Positions:\n"
            for sym, trade in pos.items():
                pnl = (trade.get('last_price', trade['entry_price']) - trade['entry_price']) * trade['qty']
                if trade['side'] == 'SELL': pnl = -pnl
                msg += f"- {sym}: {pnl:.2f} ({trade['status']})\n"
        return msg

    def _cmd_freeze(self):
        self.risk_engine.kill_switch_active = True
        return "⚠️ Trading FROZEN due to manual override."

    def _cmd_unfreeze(self):
        self.risk_engine.kill_switch_active = False
        return "✅ Trading RESUMED."
    
    def _cmd_capital(self):
        with self.lock:
            return f"Current Equity: {self.portfolio.state['capital']:.2f}"

    # --- Core Logic ---
    def run_cycle(self):
        """Main 5-minute Cycle."""
        self.logger.info("--- Starting 5m Cycle ---")
        current_time = get_current_time()
        
        # 0. Market Hours Check
        # ... (impl in run_live, moving here)
        
        # 1. Update Portfolio (Mark to Market)
        # BATCH OPTIMIZED
        with self.lock:
            self._update_portfolio_valuations(current_time)
        
        # 2. Market Regime
        regime = self._get_market_regime()
        
        # 3. Process Symbols (BATCH OPTIMIZED)
        self.logger.info(f"Processing {len(self.symbols)} symbols (Batch Request)...")
        
        # A. Batch Fetch Data (5m)
        # Returns {symbol: df_5m}
        batch_data = self.adapter.fetch_batch_latest_candles(self.symbols, "5m", limit=300)
        
        # B. Batch Fetch Daily Data (Optimized)
        # Returns {symbol: df_1d}
        self.logger.info("Batch fetching daily data...")
        batch_daily = self.adapter.fetch_batch_latest_candles(self.symbols, "1d", limit=200)
        
        if not batch_data:
            self.logger.warning("Batch fetch returned empty.")
            return

        self.logger.info(f"Received data using batch, analyzing...")

        # C. Analyze in Parallel (CPU Bound now, not I/O)
        max_workers = 20
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(self._process_symbol, sym, current_time, regime, batch_data.get(sym), batch_daily.get(sym)) 
                for sym in self.symbols if sym in batch_data
            ]
            
            results = []
            for f in tqdm(concurrent.futures.as_completed(futures), total=len(futures), desc="Analyzing Market", unit="sym"):
                res = f.result()
                if res:
                    results.append(res)
        
        # Process Market Stats (Gainers/Losers)
        if results:
            # Sort by % Change
            results.sort(key=lambda x: x['pct_change'], reverse=True)
            
            top_gainers = results[:5]
            top_losers = results[-5:]
            top_losers = top_losers[::-1] # Reverse to have worst first
            
            self.market_stats = {
                "gainers": top_gainers,
                "losers": top_losers
            }
                
        self._save_dashboard_snapshot()
        self.logger.info("Cycle Complete.")

    def _process_symbol(self, sym, current_time, regime, df_5m=None, df_daily=None):
        """
        Worker function to process a single symbol.
        No side effects on shared state unless via locked methods.
        """
        try:
            # A. Resilience Check
            if self.adapter.is_blacklisted(sym):
                return
                
            # B. Use Pre-fetched Data
            if df_5m is None or df_5m.empty:
                return 
            
            # Daily Bias
            daily_bias = "NEUTRAL"
            
            # Use passed batch daily data
            if df_daily is None:
                df_daily = pd.DataFrame() # Empty
            
            if not df_daily.empty:
                import pandas_ta as ta
                ema_series = ta.ema(df_daily['Close'], length=50)
                if ema_series is not None and not ema_series.empty:
                    ema = ema_series.iloc[-1]
                    if df_daily.iloc[-1]['Close'] > ema: daily_bias = "BULLISH"
                    else: daily_bias = "BEARISH"
            
            # C. Resample 15m & 1H
            # 15m
            df_15m = df_5m.resample('15min').agg({
                'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'
            }).dropna()
            
            # 1H (HTF Alignment)
            df_1h = df_5m.resample('1h').agg({
                'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'
            }).dropna()
            
            # Calculate Indicators
            import pandas_ta as ta
            from .indicators import calculate_indicators, calculate_trend_indicators
            df_5m = calculate_indicators(df_5m)
            df_15m = calculate_trend_indicators(df_15m)
            
            # 1H Indicators
            if not df_1h.empty:
                df_1h['EMA_50'] = ta.ema(df_1h['Close'], length=50)

            # D. Strategy Analysis
            signal = self.strategy.analyze(df_5m, df_15m, market_regime=regime, daily_bias=daily_bias, df_1h=df_1h, df_daily=df_daily)
            
            # E. Signal Processing (Requires Lock)
            if signal['action'] != 'None':
                with self.lock:
                    self._process_signal(sym, signal, current_time)
            
            # Return Stats
            pct_change = 0.0
            rsi_val = 50.0
            
            if not df_5m.empty:
                # Calculate RSI for UI
                try:
                    import pandas_ta as ta
                    rsi_series = ta.rsi(df_5m['Close'], length=14)
                    if rsi_series is not None and not rsi_series.empty:
                        rsi_val = rsi_series.iloc[-1]
                except: pass

                # Best: Use the Daily data passed
                base_price = None
                method = "None"
                
                # 1. Try Daily Data (Previous Close)
                if not df_daily.empty and len(df_daily) > 1:
                    last_date = df_daily.index[-1].date()
                    current_date = current_time.date()
                    
                    if last_date == current_date:
                        base_price = df_daily.iloc[-2]['Close']
                        method = "Daily_Prev"
                    else:
                        base_price = df_daily.iloc[-1]['Close']
                        method = "Daily_Last"
                        
                # 2. Fallback: Find Previous Day Close in 5m Data
                if base_price is None:
                    current_date = current_time.date()
                    dates = df_5m.index.date
                    prev_mask = dates < current_date
                    
                    if prev_mask.any():
                        base_price = df_5m[prev_mask].iloc[-1]['Close']
                        method = "5m_PrevDay"
                
                # 3. Fallback: Use Today's Open (Intraday Change)
                if base_price is None:
                    base_price = df_5m.iloc[0]['Open'] # Approximate
                
                curr = df_5m.iloc[-1]['Close']
                if base_price and base_price != 0:
                    pct_change = ((curr - base_price) / base_price) * 100
                
            # Sparkline Data (Last 20 bars)
            sparkline = []
            if not df_5m.empty:
                sparkline = df_5m['Close'].tail(20).tolist()

            return {
                "symbol": sym,
                "pct_change": float(pct_change),
                "price": float(df_5m.iloc[-1]['Close']),
                "volume": int(df_5m.iloc[-1]['Volume']),
                "rsi": float(rsi_val),
                "trend": sparkline
            }
                
        except Exception as e:
            # self.logger.error(f"Error in cycle for {sym}: {e}")
            pass
        return None


    def _get_market_regime(self):
        """
        Determines Market Regime based on Nifty 50 (^NSEI) Volatility & Trend.
        Returns: VOLATILE | TRENDING | RANGE-BOUND | STABLE
        """
        try:
            # Fetch Nifty Data (Method depends on Adapter)
            # Using ^NSEI for Nifty 50
            df = self.adapter.fetch_latest_candles("^NSEI", "5m", limit=75) # ~1 day of 5m
            
            if df.empty:
                return "NEUTRAL"
                
            # 1. Calc Daily Change / Volatility
            # Approximate Daily Range from 5m data if 1d not available
            # Or just use standard deviation of close prices
            
            closes = df['Close']
            
            # Simple Trend Check: Price vs EMA 20
            import pandas_ta as ta
            ema_20 = ta.ema(closes, length=20).iloc[-1]
            current_price = closes.iloc[-1]
            
            # Volatility: Standard Deviation of returns
            returns = closes.pct_change().dropna()
            volatility = returns.std() * 100 # Percentage
            
            # Thresholds (Heuristic)
            # 5m Volatility > 0.1% per bar is high for index?
            # Let's use Range: (High - Low) / Low
            high = df['High'].max()
            low = df['Low'].min()
            range_pct = ((high - low) / low) * 100
            
            regime = "RANGE-BOUND"
            
            if range_pct > 1.2: # Mobile > 1% move intraday is volatile
                regime = "VOLATILE"
            elif volatility > 0.08: # Panic moves
                regime = "VOLATILE"
            else:
                # Check Trend
                if abs(current_price - ema_20) / current_price > 0.001:
                    regime = "TRENDING"
                else:
                    regime = "RANGE-BOUND"
            
            self.last_regime = regime # Store for snapshot
            return regime
        except Exception as e:
            self.logger.error(f"Error determining market regime: {e}")
            return "NEUTRAL"

    def _process_signal(self, sym, signal, time):
        # NOTE: This method MUST be called within a lock context
        
        # 0. Log Signal to DB (Analysis)
        try:
            # We use the portfolio's DB connection for simplicity
            self.portfolio.db.log_signal(signal, sym, self.strategy.strategy_mode)
        except Exception as e:
            self.logger.error(f"Failed to log signal for {sym}: {e}")
        
        # 1. Risk Check
        allowed, reason = self.risk_engine.can_open_trade(sym)
        if not allowed:
            self.logger.info(f"Signal Rejected for {sym}: {reason}")
            return
            
        # 2. Sizing & Levels
        atr = signal['atr']
        price = signal['current_price']
        
        # SL logic from Strategy (or default)
        sl_price = signal.get('sl_price', 0.0)
        if sl_price == 0.0:
            sl_dist = 1.5 * atr
            if signal['action'] == "BUY":
                sl_price = price - sl_dist
            else:
                sl_price = price + sl_dist

        target_r = signal.get('target_r', 1.5)
        
        # Calculate TP based on SL distance
        risk_dist = abs(price - sl_price)
        
        if signal['action'] == "BUY":
            tp_price = price + (risk_dist * target_r)
        else:
            tp_price = price - (risk_dist * target_r)
            
        # 3. Stop Limit / Pending Order Logic
        stop_entry_price = signal.get('stop_entry_price', 0.0)
        
        if stop_entry_price > 0:
            # Check for existing pending
            for po in self.pending_orders:
                if po['symbol'] == sym: return # Already pending
            
            pending = {
                'symbol': sym,
                'side': signal['action'],
                'created_time': time, # datetime object
                'trigger_price': stop_entry_price,
                'sl_price': sl_price,
                'tp_price': tp_price,
                'reason': signal['reason'],
                'atr': atr
            }
            self.pending_orders.append(pending)
            self.logger.info(f"PENDING ORDER: {sym} {signal['action']} @ {stop_entry_price:.2f}")
            self.bot.send_message(f"⏳ **PENDING**: {sym} {signal['action']} Stop Limit @ {stop_entry_price:.2f}")
            return

        # 4. Immediate Execution (Fallback)
        qty = self.risk_engine.calculate_qty(price, sl_price)
        
        if qty > 0:
            trade = {
                'symbol': sym, 'side': signal['action'], 'entry_time': time.isoformat(),
                'entry_price': price, 'qty': qty, 'sl': sl_price, 'tp': tp_price,
                'status': 'OPEN', 'reason': signal['reason'],
                'highest_high': price, 'lowest_low': price, 'trailing_active': False
            }
            self.portfolio.add_position(trade)
            self.bot.notify_signal(trade)

    def _update_portfolio_valuations(self, time):
        """Checks open positions for SL/TP and Pending Orders."""
        # NOTE: This method is called within a lock context or is single-threaded
        
        # 1. Get List of Symbols to Update (Open Pos + Pending)
        active_symbols = list(self.portfolio.state['open_positions'].keys())
        for po in self.pending_orders:
            if po['symbol'] not in active_symbols:
                active_symbols.append(po['symbol'])
                
        if not active_symbols:
            return

        # 2. Batch Fetch Latest Price
        # Batch Fetch Optimization
        price_map = {}
        
        # We use a smaller limit for speed
        batch_prices = self.adapter.fetch_batch_latest_candles(active_symbols, "5m", limit=3)
        
        for sym, df in batch_prices.items():
            if not df.empty:
                price_map[sym] = {
                    'High': df.iloc[-1]['High'],
                    'Low': df.iloc[-1]['Low'],
                    'Close': df.iloc[-1]['Close']
                }
                
                # Update Portfolio Live Price (for Dashboard PnL)
                if sym in self.portfolio.state['open_positions']:
                    trade = self.portfolio.state['open_positions'][sym]
                    trade['last_price'] = df.iloc[-1]['Close'] 


        # 3. Process Pending Orders
        for order in self.pending_orders[:]:
            sym = order['symbol']
            if sym not in price_map: continue
            
            candle = price_map[sym]
            high = candle['High']
            low = candle['Low']
            
            # Expiration (15m = 3 candles)
            time_diff = (time - order['created_time']).total_seconds()
            if time_diff > (15 * 60):
                self.pending_orders.remove(order)
                self.logger.info(f"Order Expired: {sym}")
                continue
                
            triggered = False
            fill_price = 0.0
            
            if order['side'] == "BUY" and high >= order['trigger_price']:
                triggered = True
                fill_price = order['trigger_price']
            elif order['side'] == "SELL" and low <= order['trigger_price']:
                triggered = True
                fill_price = order['trigger_price']
                
            if triggered:
                # Convert to Trade
                qty = self.risk_engine.calculate_qty(fill_price, order['sl_price'])
                if qty > 0:
                    trade = {
                        'symbol': sym, 'side': order['side'], 'entry_time': time.isoformat(),
                        'entry_price': fill_price, 'qty': qty, 'sl': order['sl_price'], 'tp': order['tp_price'],
                        'status': 'OPEN', 'reason': order['reason'] + " (Triggered)",
                        'highest_high': fill_price, 'lowest_low': fill_price, 'trailing_active': False
                    }
                    self.portfolio.add_position(trade)
                    self.bot.notify_signal(trade) # Notify fill
                self.pending_orders.remove(order)

        # 4. Process Open Positions (SL/TP/Breakeven)
        for sym, trade in list(self.portfolio.state['open_positions'].items()):
            if sym not in price_map: continue
            candle = price_map[sym]
            high = candle['High']
            low = candle['Low']
            close = candle['Close']
            
            # A. Trailing Stop Logic (Prioritize Profit Protection)
            # Logic: If Profit >= 2.0R -> Activate Trailing
            # Trail Distance: 1.0R from Highest High / Lowest Low
            
            # Update High/Low
            if high > trade.get('highest_high', -99999): trade['highest_high'] = high
            if low < trade.get('lowest_low', 99999): trade['lowest_low'] = low
            
            entry = trade['entry_price']
            # Assuming current SL is initial SL if trailing not active yet.
            # If we restored from state, we might need 'initial_sl' field.
            # For now, we trust 'sl' hasn't moved unless trailing active.
            
            current_sl = trade['sl']
            
            # Calculate R (Risk)
            # If trailing is active, we can't infer initial risk easily unless stored.
            # Let's approximate or rely on 'qty' to reverse calc? No.
            # We should have stored 'initial_sl'. But for compatibility:
            # If not trailing_active, risk = abs(entry - current_sl)
            # If trailing_active, we use 1.5 * ATR? We don't have ATR here easily.
            # Let's use a safe fallback: 1% of entry? Or infer from current SL if not active.
            
            if not trade.get('trailing_active', False):
                original_risk_dist = abs(entry - current_sl)
            else:
                # If already active, we need R to maintain distance.
                # We will store 'risk_dist' in trade upon activation or creation?
                # Let's retro-fit: If missing, estimate 0.5%?
                # Better: Add 'risk_dist' to trade creation.
                original_risk_dist = trade.get('risk_dist', abs(entry * 0.005)) # Fallback
            
            # Store risk_dist if not present
            if 'risk_dist' not in trade and original_risk_dist > 0:
                 trade['risk_dist'] = original_risk_dist

            if original_risk_dist > 0:
                # Check Activation (2.0 R)
                current_profit_dist = (close - entry) if trade['side'] == "BUY" else (entry - close)
                
                if current_profit_dist >= (original_risk_dist * 2.0):
                    if not trade.get('trailing_active', False):
                        trade['trailing_active'] = True
                        self.logger.info(f"TRAILING ACTIVATED: {sym} Profit {current_profit_dist:.2f} >= 2R")
                        self.bot.send_message(f"🚀 **Trailing Active**: {sym} Reached 2R Profit.")

                # Execute Trailing
                if trade.get('trailing_active', False):
                    dist_to_trail = original_risk_dist * 1.0 # Trail at 1R distance
                    
                    if trade['side'] == "BUY":
                        new_sl = trade['highest_high'] - dist_to_trail
                        if new_sl > trade['sl']:
                            trade['sl'] = round_to_tick(new_sl)
                            self.logger.info(f"Trailing SL Updated for {sym}: {trade['sl']}")
                    else: # SELL
                        new_sl = trade['lowest_low'] + dist_to_trail
                        if new_sl < trade['sl']:
                            trade['sl'] = round_to_tick(new_sl)
                            self.logger.info(f"Trailing SL Updated for {sym}: {trade['sl']}")
            
            # B. Exit Check
            exit_price = None
            reason = ""
            
            if trade['side'] == "BUY":
                if low <= trade['sl']:
                    exit_price = trade['sl']; reason = "Hit SL"
                elif high >= trade['tp']:
                    exit_price = trade['tp']; reason = "Hit TP"
            else:
                if high >= trade['sl']:
                    exit_price = trade['sl']; reason = "Hit SL"
                elif low <= trade['tp']:
                    exit_price = trade['tp']; reason = "Hit TP"
                    
            if exit_price:
                # Close Trade
                pnl = (exit_price - entry) * trade['qty'] if trade['side'] == "BUY" else (entry - exit_price) * trade['qty']
                self.portfolio.close_position(sym, exit_price, time.isoformat(), reason)
                self.bot.send_message(f"🚪 **Trade Closed**: {sym}\n{reason} @ {exit_price}\nPnL: {pnl:.2f}")

    def _save_dashboard_snapshot(self):
        """Saves a snapshot of transient state for the Dashboard."""
        import json
        import os
        
        snapshot = {
            "last_updated": datetime.now().isoformat(),
            "status": "RUNNING",
            "symbols_in_focus": self.symbols,
            "pending_orders": self.pending_orders,
            "market_regime": self.last_regime,
            "market_stats": self.market_stats,
            "open_positions_live": self.portfolio.state['open_positions'],
            # Swing trading data
            "swing_symbols": self.swing_symbols,
            "swing_positions": self.portfolio.state.get('swing_positions', {})
        }
        
        try:
            with open("data/dashboard_snapshot.json", "w") as f:
                json.dump(snapshot, f, indent=4)
        except Exception as e:
            self.logger.error(f"Failed to save dashboard snapshot: {e}")
    
    # ==================== SWING TRADING METHODS ====================
    
    def run_swing_cycle(self):
        """Daily swing trading cycle."""
        if not self.swing_strategy:
            return
            
        self.logger.info("--- Starting Swing Trading Cycle ---")
        current_time = get_current_time()
        
        # Update swing positions (check exits)
        with self.lock:
            self._update_swing_positions(current_time)
        
        # Analyze swing candidates
        for sym in self.swing_symbols:
            try:
                # Fetch daily and 4h data
                df_daily = self.adapter.fetch_daily(sym, days=90)
                if df_daily.empty:
                    continue
                    
                # Calculate indicators
                from .indicators import calculate_indicators
                df_daily = calculate_indicators(df_daily)
                
                # Analyze
                signal = self.swing_strategy.analyze(df_daily)
                
                # Process signal
                if signal['action'] != 'None':
                    with self.lock:
                        self._process_swing_signal(sym, signal, current_time)
                        
            except Exception as e:
                self.logger.error(f"Error processing swing symbol {sym}: {e}")
                
        self._save_dashboard_snapshot()
        self.logger.info("Swing Cycle Complete.")
        
    def _process_swing_signal(self, sym, signal, time):
        """Process swing trading signals."""
        # Check if already have a swing position
        if self.portfolio.get_swing_position(sym):
            return
            
        # Check max positions
        max_swing_positions = self.config.get('swing_trading', {}).get('max_positions', 3)
        if len(self.portfolio.state['swing_positions']) >= max_swing_positions:
            self.logger.info(f"Max swing positions reached. Skipping {sym}")
            return
            
        # Calculate position size
        swing_stats = self.portfolio.get_swing_stats()
        swing_capital = swing_stats['swing_capital']
        
        price = signal['current_price']
        sl_price = signal.get('sl_price', 0.0)
        
        if sl_price == 0.0:
            atr = signal['atr']
            sl_multiplier = self.config.get('swing_trading', {}).get('stop_loss_atr_multiplier', 2.5)
            if signal['action'] == "BUY":
                sl_price = price - (atr * sl_multiplier)
            else:
                sl_price = price + (atr * sl_multiplier)
                
        # Calculate qty (risk 1% per swing trade)
        risk_per_trade = swing_capital * 0.01
        risk_dist = abs(price - sl_price)
        qty = int(risk_per_trade / risk_dist) if risk_dist > 0 else 0
        
        if qty > 0:
            target_r = signal.get('target_r', 4.0)
            if signal['action'] == "BUY":
                tp_price = price + (risk_dist * target_r)
            else:
                tp_price = price - (risk_dist * target_r)
                
            trade = {
                'symbol': sym,
                'side': signal['action'],
                'entry_time': time.isoformat(),
                'entry_price': price,
                'qty': qty,
                'sl': sl_price,
                'tp': tp_price,
                'status': 'OPEN',
                'reason': signal['reason'],
                'highest_high': price,
                'lowest_low': price,
                'trailing_active': False,
                'risk_dist': risk_dist
            }
            
            self.portfolio.add_swing_position(trade)
            self.bot.send_message(f"🔄 **Swing Position Opened**\n{sym} {signal['action']} @ {price:.2f}\n{signal['reason']}")
            self.logger.info(f"Swing Position Opened: {sym} {signal['action']} @ {price}")
            
    def _update_swing_positions(self, time):
        """Update swing positions (check exits, time-based)."""
        if not self.portfolio.state['swing_positions']:
            return
            
        max_hold_days = self.config.get('swing_trading', {}).get('max_hold_days', 15)
        
        for sym, trade in list(self.portfolio.state['swing_positions'].items()):
            try:
                # Fetch current price
                df = self.adapter.fetch_latest_candles(sym, "1d", limit=1)
                if df.empty:
                    continue
                    
                high = df.iloc[-1]['High']
                low = df.iloc[-1]['Low']
                close = df.iloc[-1]['Close']
                
                # Update tracking
                trade['last_price'] = close
                if high > trade.get('highest_high', -99999):
                    trade['highest_high'] = high
                if low < trade.get('lowest_low', 99999):
                    trade['lowest_low'] = low
                    
                # Check time-based exit
                entry_date = datetime.fromisoformat(trade['entry_time'])
                hold_days = (time - entry_date).days
                
                if hold_days >= max_hold_days:
                    pnl = (close - trade['entry_price']) * trade['qty'] if trade['side'] == "BUY" else (trade['entry_price'] - close) * trade['qty']
                    self.portfolio.close_swing_position(sym, close, time.isoformat(), f"Max Hold Time ({max_hold_days} days)")
                    self.bot.send_message(f"⏰ **Swing Time Exit**: {sym}\n{hold_days} days\nPnL: {pnl:.2f}")
                    continue
                    
                # Trailing stop for swing trades (after 1.5R profit)
                entry = trade['entry_price']
                risk_dist = trade.get('risk_dist', abs(entry - trade['sl']))
                current_profit = (close - entry) if trade['side'] == "BUY" else (entry - close)
                
                if current_profit >= (risk_dist * 1.5):
                    if not trade.get('trailing_active', False):
                        trade['trailing_active'] = True
                        self.logger.info(f"Swing Trailing Activated: {sym}")
                        
                    # Trail at 1.5R distance
                    trail_dist = risk_dist * 1.5
                    if trade['side'] == "BUY":
                        new_sl = trade['highest_high'] - trail_dist
                        if new_sl > trade['sl']:
                            trade['sl'] = round_to_tick(new_sl)
                    else:
                        new_sl = trade['lowest_low'] + trail_dist
                        if new_sl < trade['sl']:
                            trade['sl'] = round_to_tick(new_sl)
                            
                # Check SL/TP
                exit_price = None
                reason = ""
                
                if trade['side'] == "BUY":
                    if low <= trade['sl']:
                        exit_price = trade['sl']
                        reason = "Hit SL"
                    elif high >= trade['tp']:
                        exit_price = trade['tp']
                        reason = "Hit TP"
                else:
                    if high >= trade['sl']:
                        exit_price = trade['sl']
                        reason = "Hit SL"
                    elif low <= trade['tp']:
                        exit_price = trade['tp']
                        reason = "Hit TP"
                        
                if exit_price:
                    pnl = (exit_price - entry) * trade['qty'] if trade['side'] == "BUY" else (entry - exit_price) * trade['qty']
                    self.portfolio.close_swing_position(sym, exit_price, time.isoformat(), reason)
                    self.bot.send_message(f"🚪 **Swing Exit**: {sym}\n{reason} @ {exit_price}\nPnL: {pnl:.2f}")
                    
            except Exception as e:
                self.logger.error(f"Error updating swing position {sym}: {e}")
                
    def run_swing_scanner(self):
        """Run swing scanner to identify candidates."""
        if not self.swing_scanner:
            return
            
        self.logger.info("Running Swing Scanner...")
        self.bot.send_message("🔍 Running Swing Scanner...")
        
        universe = self.config['symbols']
        
        try:
            candidates = self.swing_scanner.scan(universe)
            
            if candidates:
                with self.lock:
                    self.swing_symbols = candidates
                msg = f"📈 **Swing Candidates**\nTop {len(candidates)}:\n" + "\n".join([f"- {s}" for s in candidates])
                self.logger.info(f"Swing Scanner Selected: {candidates}")
                self.bot.send_message(msg)
            else:
                self.logger.warning("Swing scanner found no candidates.")
                
            self._save_dashboard_snapshot()
            
        except Exception as e:
            self.logger.error(f"Swing Scanner Error: {e}")

    def run_scanner(self):
        """Runs the market scanner and updates active symbols."""
        if not self.config.get('use_scanner', False):
            return

        self.logger.info("Running Market Scanner...")
        self.bot.send_message("📡 Running Market Scanner...")
        
        # Use full universe from Config as candidates
        universe = self.config['symbols']
        
        try:
            top_stocks = self.scanner.scan(universe)
            
            if top_stocks:
                # With parallel execution, we can handle more symbols if needed.
                # But scanner limits to Top N.
                self.symbols = top_stocks
                msg = f"🎯 **Scanner Results**\nFocusing on Top {len(top_stocks)}:\n" + "\n".join([f"- {s}" for s in top_stocks])
                self.logger.info(f"Scanner Selected: {top_stocks}")
                self.bot.send_message(msg)
            else:
                self.logger.warning("Scanner found no stocks. keeping default list.")
                self.bot.send_message("⚠️ Scanner found no stocks. Using default list.")
                
            self._save_dashboard_snapshot()

        except Exception as e:
            self.logger.error(f"Scanner Error: {e}")

    def start(self):
        self.portfolio.reset_daily_pnl() # New Day
        
        # Schedule Intraday Scanner at 09:16 AM
        if self.config.get('use_scanner', False):
            self.scheduler.add_job(
                self.run_scanner, 'cron', day_of_week='mon-fri', hour=9, minute=16
            )
            self.logger.info("Scheduled Intraday Scanner for 09:16 AM.")
        
        # Schedule Swing Scanner daily at 09:20 AM
        if self.swing_scanner:
            self.scheduler.add_job(
                self.run_swing_scanner, 'cron', day_of_week='mon-fri', hour=9, minute=20
            )
            self.logger.info("Scheduled Swing Scanner for 09:20 AM.")
            
        # Schedule Swing Cycle daily at 09:30 AM
        if self.swing_strategy:
            self.scheduler.add_job(
                self.run_swing_cycle, 'cron', day_of_week='mon-fri', hour=9, minute=30
            )
            self.logger.info("Scheduled Swing Cycle for 09:30 AM daily.")

        # Schedule Intraday 5min cycle
        self.scheduler.add_job(
            self.run_cycle, 'cron', day_of_week='mon-fri', hour='9-15', minute='*/5', second='10'
        )
        
        # Run immediately on startup for feedback
        self.logger.info("Running initial startup cycle...")
        self.run_cycle()
        
        self.scheduler.start()
        self.logger.info("Bot Engine Started.")
        self._save_dashboard_snapshot()
        
        try:
            while True: time.sleep(1)
        except (KeyboardInterrupt, SystemExit):
            self.scheduler.shutdown()
            self.bot.shutdown()
