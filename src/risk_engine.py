import logging
from .portfolio import PortfolioManager

class RiskEngine:
    """
    Centralized Risk Management.
    Enforces:
    - Max Daily Loss (Kill Switch)
    - Position Sizing (ATR based)
    - Max Open Positions
    """
    def __init__(self, config: dict, portfolio: PortfolioManager):
        self.config = config
        self.portfolio = portfolio
        self.logger = logging.getLogger("IntradaySignals.Risk")
        
        self.max_daily_loss_pct = config.get('max_daily_loss_percent', 5.0)
        self.max_positions = config.get('max_positions', 5)
        self.risk_per_trade_pct = config.get('risk_per_trade_percent', 1.0)
        self.kill_switch_active = False

    def check_kill_switch(self):
        """Checks if daily loss limit is hit."""
        # If manually killed or auto killed
        if self.kill_switch_active:
            return True
            
        stats = self.portfolio.get_stats()
        daily_pnl = stats['daily_pnl']
        capital = stats['capital']
        
        # Loss Limit (Negative Value)
        limit = -(capital * (self.max_daily_loss_pct / 100.0))
        
        if daily_pnl <= limit:
            self.kill_switch_active = True
            self.logger.warning(f"KILL SWITCH TRIGGERED! Daily PnL: {daily_pnl:.2f} Limit: {limit:.2f}")
            return True
            
        return False

    def can_open_trade(self, symbol: str):
        """Checks generic rules for opening a new trade."""
        if self.check_kill_switch():
            return False, "Kill Switch Active"
            
        stats = self.portfolio.get_stats()
        if stats['open_count'] >= self.max_positions:
            return False, "Max Positions Reached"
            
        if self.portfolio.get_position(symbol):
            return False, f"Position already open for {symbol}"
            
        return True, "OK"

    def calculate_qty(self, price: float, sl_price: float):
        """
        Calculates quantity based on Risk %.
        Risk Amount = Capital * Risk%
        Risk Per Share = |Price - SL|
        Qty = Risk Amount / Risk Per Share
        """
        capital = self.portfolio.state['capital']
        risk_amount = capital * (self.risk_per_trade_pct / 100.0)
        risk_per_share = abs(price - sl_price)
        
        if risk_per_share == 0:
            return 0
            
        qty = int(risk_amount / risk_per_share)
        
        # Market Impact / Cap Check (Optional: Don't use > 20% capital on one trade)
        # For intraday leverage (MIS), we allow up to 4x or 5x.
        max_trade_val = capital * 4.0 # Cap single trade notional to 400% of equity (leverage)
        if qty * price > max_trade_val:
             qty = int(max_trade_val / price)
             
        return qty
