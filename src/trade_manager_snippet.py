    def close_all_positions_by_type(self, symbol: str, side: str, exit_price: float, exit_time: datetime, reason: str):
        """Closes all positions of a specific type (BUY/SELL) for a symbol."""
        for trade in self.open_trades[:]:
            if trade['symbol'] == symbol and trade['side'] == side:
                self._close_trade(trade, exit_price, exit_time, reason)
