import pandas as pd
from datetime import datetime
from .utils import round_to_tick
import logging

class TradeManager:
    """
    Manages trade lifecycle, position sizing, and risk checks (Circuit Breaker).
    """
    def __init__(self, config: dict):
        self.config = config
        self.capital = config.get('capital', 30000.0)
        self.risk_pct = config.get('risk_per_trade_percent', 2.0)
        self.max_daily_loss = config.get('max_daily_loss_percent', 4.0)
        self.max_positions = config.get('max_positions', 1)
        
        self.trades = [] # List of trade dicts
        self.trades = [] # List of trade dicts
        self.open_trades = [] # Currently open trades
        self.pending_orders = [] # Orders waiting for trigger
        self.daily_pnl = 0.0
        self.circuit_breaker_active = False
        self.logger = logging.getLogger("IntradaySignals.TradeManager")

    def reset_daily(self):
        """Resets daily counters."""
        self.daily_pnl = 0.0
        self.circuit_breaker_active = False
        self.daily_trade_counts = {} # Reset trade counts
        self.logger.info("Daily P&L reset.")

    def check_circuit_breaker(self):
        """Checks if daily loss limit reached."""
        loss_limit = -(self.capital * (self.max_daily_loss / 100.0))
        if self.daily_pnl <= loss_limit:
            self.circuit_breaker_active = True
            self.logger.warning(f"CIRCUIT BREAKER TRIGGERED! Daily PnL: {self.daily_pnl:.2f}")
            return True
        return False

    def calculate_position_size(self, entry_price: float, stop_loss: float) -> int:
        """
        Calculates quantity based on % risk per trade.
        """
        risk_amount = self.capital * (self.risk_pct / 100.0)
        risk_per_share = abs(entry_price - stop_loss)
        
        if risk_per_share == 0:
            return 0
            
        qty = int(risk_amount / risk_per_share)
        
        # Basic sanity check: Don't exceed 4x leverage (typical intraday margin) 
        # or capital limit if cash & carry. Assuming intraday margin is available.
        # Let's cap at max capital usage (1x) if user wants conservative, 
        # but for intraday usually 5x is allowed. We stick to risk-based sizing.
        
        # However, let's limit total value to e.g. 5 * Capital (Margin)
        if qty * entry_price > self.capital * 5:
            qty = int((self.capital * 5) / entry_price)
            
        return qty

    def process_signal(self, symbol: str, signal_data: dict) -> dict:
        """
        Processes a raw signal, applies risk mgmt, and returns Order details.
        """
        if self.circuit_breaker_active:
            return None

        if len(self.open_trades) >= self.max_positions:
            return None

        action = signal_data['action']
        if action == "None":
            return None
            
        # Optimization: One Shot Rule (Max 1 trade per symbol per day)
        # We keep this for Pullbacks too to enforce discipline, or relax to 2 if needed.
        # Let's keep 1 for now to force the "Best" entry.
        if not hasattr(self, 'daily_trade_counts'):
            self.daily_trade_counts = {}
            
        current_count = self.daily_trade_counts.get(symbol, 0)
        daily_limit = self.config.get('max_trades_per_symbol', 1) 
        
        if current_count >= daily_limit:
            return None
            
        self.daily_trade_counts[symbol] = current_count + 1

        price = signal_data['current_price']
        atr = signal_data['atr']
        
        # Stop Loss & Take Profit logic
        # If Strategy provides SL (Technical), use it. Else default to ATR.
        
        sl_price = signal_data.get('sl_price', 0.0)
        
        if sl_price == 0.0:
            # Fallback to ATR based SL
            sl_dist = 1.5 * atr
            if action == "BUY":
                sl_price = round_to_tick(price - sl_dist)
            else:
                sl_price = round_to_tick(price + sl_dist)
        else:
             sl_price = round_to_tick(sl_price)
                
        # Calculate Risk and Reward
        risk_dist = abs(price - sl_price)
        reward_ratio = signal_data.get('target_r', 2.0)
        
        if action == "BUY":
            tp_price = round_to_tick(price + (risk_dist * reward_ratio))
        else: # SELL
            tp_price = round_to_tick(price - (risk_dist * reward_ratio))

        # ------------------------------------------------------------------
        # STOP LIMIT ENTRY LOGIC
        # ------------------------------------------------------------------
        # If strategy provides 'stop_entry_price', we create a PENDING ORDER.
        stop_entry_price = signal_data.get('stop_entry_price', 0.0)
        
        if stop_entry_price > 0:
            # Check if we already have a pending order for this symbol
            # (One-Shot rule applies to pending too)
            for po in self.pending_orders:
                if po['symbol'] == symbol:
                    return None # Already pending
                    
            pending_order = {
                'symbol': symbol,
                'side': action,
                'created_time': signal_data['timestamp'],
                'trigger_price': stop_entry_price,
                'sl_price': sl_price, # Projected SL
                'tp_price': tp_price, # Projected TP
                'reason': signal_data['reason'],
                'atr': atr, # Store ATR to recalc SL if needed (or fixed)
                'target_r': reward_ratio,
                'expiry_candles': 3 # Expire if not triggered in 3 bars (15 mins)
            }
            self.pending_orders.append(pending_order)
            self.logger.info(f"PENDING ORDER: {symbol} {action} @ {stop_entry_price:.2f} (Stop Limit)")
            return pending_order
            
        # ------------------------------------------------------------------
        # IMMEDIATE EXECUTION (Fallback)
        # ------------------------------------------------------------------
        qty = self.calculate_position_size(price, sl_price)
        
        if qty <= 0:
            return None

        trade = {
            'symbol': symbol,
            'side': action,
            'entry_time': signal_data['timestamp'],
            'entry_price': price,
            'qty': qty,
            'sl': sl_price,
            'tp': tp_price,
            'status': 'OPEN',
            'reason': signal_data['reason'],
            'highest_high': price, # For Trailing Stop (BUY)
            'lowest_low': price,   # For Trailing Stop (SELL)
            'trailing_active': False
        }
        
        self.open_trades.append(trade)
        return trade

    def update_open_trades(self, last_prices: dict, current_time: datetime):
        """
        Checks open trades against SL/TP and handles Pyramiding.
        """
        for trade in self.open_trades[:]:
            sym = trade['symbol']
            if sym not in last_prices:
                continue
            
            candle = last_prices[sym]
            high = candle['High']
            low = candle['Low']
            close = candle['Close']
            
            # Risk Distance
            # Risk Distance
            current_sl = trade['sl']
            
            # Calculate Current R
            entry_price = trade['entry_price']
            if 'sl_original' not in trade:
                trade['sl_original'] = trade['sl']
            
            original_risk_dist = abs(entry_price - trade['sl_original'])
            
            # ----------------------------------------------------
            # 0. AGGRESSIVE BREAKEVEN (High Win Rate Optimization)
            # ----------------------------------------------------
            # Logic: If Profit >= 0.5R, Move SL to Breakeven
            if not trade.get('breakeven_active', False) and original_risk_dist > 0:
                current_profit = 0
                if trade['side'] == "BUY":
                    current_profit = close - entry_price
                else:
                    current_profit = entry_price - close
                    
                # Threshold: 1.0 R
                if current_profit >= (original_risk_dist * 1.0):
                    # Trigger Breakeven
                    trade['sl'] = round_to_tick(entry_price) # Move to BE
                    trade['breakeven_active'] = True
                    self.logger.info(f"BREAKEVEN TRIGGERED: {sym} Profit {current_profit:.2f} >= 1.0R. SL moved to Entry.")

            
            # ----------------------------------------------------
            # 1. TRAILING STOP (Profit Maximization)
            # ----------------------------------------------------
            # Update extremes
            trade['highest_high'] = max(trade.get('highest_high', entry_price), high)
            trade['lowest_low'] = min(trade.get('lowest_low', entry_price), low)
            
            if original_risk_dist > 0:
                # BUY SIDE TRAILING
                if trade['side'] == "BUY":
                    # Check if we hit 2R Profit
                    current_run_up = trade['highest_high'] - entry_price
                    if current_run_up >= (original_risk_dist * 2.0):
                        trade['trailing_active'] = True
                        
                    if trade['trailing_active']:
                        # Trail 1R behind Highest High
                        new_sl = trade['highest_high'] - (original_risk_dist * 1.0)
                        if new_sl > trade['sl']:
                            trade['sl'] = round_to_tick(new_sl)
                            self.logger.info(f"TRAILING STOP: {sym} BUY New SL {trade['sl']:.2f} (High {trade['highest_high']:.2f})")

                # SELL SIDE TRAILING
                elif trade['side'] == "SELL":
                    # Check if we hit 2R Profit
                    current_run_down = entry_price - trade['lowest_low']
                    if current_run_down >= (original_risk_dist * 2.0):
                        trade['trailing_active'] = True
                        
                    if trade['trailing_active']:
                        # Trail 1R above Lowest Low
                        new_sl = trade['lowest_low'] + (original_risk_dist * 1.0)
                        if new_sl < trade['sl']:
                            trade['sl'] = round_to_tick(new_sl)
                            self.logger.info(f"TRAILING STOP: {sym} SELL New SL {trade['sl']:.2f} (Low {trade['lowest_low']:.2f})")
            
            if not trade.get('pyramided', False) and original_risk_dist > 0:
                current_profit = 0
                if trade['side'] == "BUY":
                    current_profit = close - entry_price
                else:
                    current_profit = entry_price - close
                
                # Check 1R Threshold
                if current_profit >= original_risk_dist:
                    # PYRAMID TRIGGER
                    # Add 50% Qty
                    add_qty = int(trade['qty'] * 0.5)
                    if add_qty > 0:
                        # New Avg Price
                        # New Cost = (OldQty * OldPrice + AddQty * CurrPrice) / TotalQty
                        new_total_qty = trade['qty'] + add_qty
                        new_avg_price = ((trade['qty'] * entry_price) + (add_qty * close)) / new_total_qty
                        
                        # Update Trade
                        trade['qty'] = new_total_qty
                        trade['entry_price'] = new_avg_price # Update Avg Price
                        trade['pyramided'] = True
                        
                        # Move SL to Breakeven (New Avg Entry)
                        # Actually to be safe, maybe slightly below/above.
                        # Aggressive: Move SL to New Avg Entry. Risk is now 0 on total? 
                        # No, if price drops to Avg Entry, we lose nothing (minus comms).
                        trade['sl'] = round_to_tick(new_avg_price)
                        
                        self.logger.info(f"PYRAMID: Added {add_qty} to {sym} @ {close}. New Avg: {new_avg_price:.2f}. SL moved to BE.")

            # ----------------------------------------------------
            # 2. CHECK EXIT CONDITIONS (SL / TP)
            # ----------------------------------------------------

            exit_price = None
            exit_reason = None
            
            # BUY SIDE
            if trade['side'] == "BUY":
                if low <= trade['sl']:
                    exit_price = trade['sl']
                    exit_reason = "Hit SL"
                elif high >= trade['tp']:
                    exit_price = trade['tp'] 
                    exit_reason = "Hit TP"
            # SELL SIDE
            elif trade['side'] == "SELL":
                if high >= trade['sl']:
                    exit_price = trade['sl']
                    exit_reason = "Hit SL"
                elif low <= trade['tp']:
                    exit_price = trade['tp']
                    exit_reason = "Hit TP"

            # Close Full Trade if Exit Triggered
            if exit_price:
                self._close_trade(trade, exit_price, current_time, exit_reason)

    def _close_trade(self, trade, exit_price, exit_time, reason):
        trade['exit_time'] = exit_time
        trade['exit_price'] = exit_price
        trade['status'] = 'CLOSED'
        trade['exit_reason'] = reason
        
        # Calculate PnL
        if trade['side'] == "BUY":
            pnl = (exit_price - trade['entry_price']) * trade['qty']
        else:
            pnl = (trade['entry_price'] - exit_price) * trade['qty']
            
        trade['pnl'] = pnl
        trade['pnl_percent'] = (pnl / (trade['entry_price'] * trade['qty'])) * 100
        
        self.daily_pnl += pnl
        self.open_trades.remove(trade)
        self.trades.append(trade)
        
        self.logger.info(f"Trade Closed: {trade['symbol']} {trade['side']} PnL: {pnl:.2f} ({reason})")
        self.check_circuit_breaker()

    def update_pending_orders(self, last_prices: dict, current_time: datetime):
        """
        Checks if pending orders are triggered or expired.
        """
        for order in self.pending_orders[:]:
            sym = order['symbol']
            if sym not in last_prices:
                continue
            
            candle = last_prices[sym]
            high = candle['High']
            low = candle['Low']
            
            # Check Expiration
            # We approximate expiration by time diff? Or count?
            # Simple: Time diff > 15 mins (3 * 5m)
            time_diff = current_time - order['created_time']
            if time_diff.total_seconds() > (15 * 60):
                self.pending_orders.remove(order)
                # Ensure we reset trade count? No, we didn't count it yet?
                # Actually process_signal added to daily_trade_counts. We should probably revert that?
                # Or just treat expired order as "used attempt". Let's stick to "used attempt" for discipline.
                self.logger.info(f"ORDER EXPIRED: {sym} (No fill in 15m)")
                continue

            # Check Trigger
            triggered = False
            fill_price = 0.0
            
            if order['side'] == "BUY":
                # Buy Stop Limit: If High > Trigger
                if high >= order['trigger_price']:
                    triggered = True
                    # Assume fill at Trigger (Stop Limit) or slight slippage?
                    fill_price = order['trigger_price']
            
            elif order['side'] == "SELL":
                 # Sell Stop Limit: If Low < Trigger
                 if low <= order['trigger_price']:
                     triggered = True
                     fill_price = order['trigger_price']
            
            if triggered:
                # Convert to Trade
                # Recalculate Qty based on Fill Price
                qty = self.calculate_position_size(fill_price, order['sl_price'])
                
                if qty > 0:
                    trade = {
                        'symbol': sym,
                        'side': order['side'],
                        'entry_time': current_time,
                        'entry_price': fill_price,
                        'qty': qty,
                        'sl': order['sl_price'],
                        'tp': order['tp_price'],
                        'status': 'OPEN',
                        'reason': order['reason'] + " (Triggered)",
                        'highest_high': fill_price, # Init for Trailing
                        'lowest_low': fill_price,   # Init for Trailing
                        'trailing_active': False
                    }
                    
                    self.open_trades.append(trade)
                    self.logger.info(f"ORDER FILLED: {sym} {order['side']} @ {fill_price}")
                
                self.pending_orders.remove(order)

    def close_all_positions(self, current_prices: dict, time, reason="End of Day"):
        """Force close all positions."""
        for trade in self.open_trades[:]:
             # Use Close price if available, else standard fallback
             sym = trade['symbol']
             price = current_prices.get(sym, {}).get('Close', trade['entry_price'])
             self._close_trade(trade, price, time, reason)

    def close_all_positions_by_type(self, symbol: str, side: str, exit_price: float, exit_time: datetime, reason: str):
        """Closes all positions of a specific type (BUY/SELL) for a symbol."""
        for trade in self.open_trades[:]:
            if trade['symbol'] == symbol and trade['side'] == side:
                self._close_trade(trade, exit_price, exit_time, reason)

