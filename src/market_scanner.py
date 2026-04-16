import pandas as pd
import yfinance as yf
import logging
from datetime import datetime, timedelta

class MarketScanner:
    """
    Scans the market for high-momentum stocks based on Gap %.
    """
    def __init__(self, config: dict):
        self.logger = logging.getLogger("IntradaySignals.Scanner")
        self.config = config
        self.limit = config.get('scanner_limit', 5)

    def scan(self, universe: list) -> list:
        """
        Scans the provided list of symbols and returns the Top N by Gap %.
        """
        self.logger.info(f"Scanning {len(universe)} symbols for Top {self.limit} Gappers...")
        
        if not universe:
            self.logger.warning("Empty universe provided to scanner.")
            return []

        try:
            # Batch Download for Speed
            # Fetch last 5 days to ensure we have Prev Close and Today Open
            # (If run at 09:16, we should have today's Open)
            
            # yfinance batch download
            # Format: "SYM1.NS SYM2.NS ..."
            tickers = " ".join(universe)
            
            # Fetch data
            df = yf.download(tickers, period="5d", group_by='ticker', progress=False, auto_adjust=False)
            
            if df.empty:
                self.logger.error("Scanner returned no data.")
                return []

            results = []
            
            # Parse Data
            # If multiple tickers, df columns are MultiIndex (Ticker, OHLCV)
            # If single ticker, df columns are OHLCV
            
            is_multi = isinstance(df.columns, pd.MultiIndex)
            
            for symbol in universe:
                try:
                    if is_multi:
                        # Extract symbol DF
                        try:
                            sym_df = df[symbol].dropna()
                        except KeyError:
                            continue
                    else:
                        sym_df = df.dropna()
                        if universe[0] != symbol: continue # Should not happen if universe > 1
                    
                    if len(sym_df) < 2:
                        continue
                        
                    # Get Last Two Candles
                    # -1 is Today (Partial), -2 is Yesterday
                    today = sym_df.iloc[-1]
                    yesterday = sym_df.iloc[-2]
                    
                    # Logic: 
                    # Gap = (Today Open - Yesterday Close) / Yesterday Close
                    prev_close = yesterday['Close']
                    today_open = today['Open']
                    
                    if prev_close == 0: continue
                    
                    gap_pct = ((today_open - prev_close) / prev_close) * 100.0
                    
                    # Optional: Volume Filter (Yesterday's Volume > X)
                    # min_vol = 100000 
                    # if yesterday['Volume'] < min_vol: continue
                    
                    results.append({
                        'symbol': symbol,
                        'gap_pct': gap_pct,
                        'abs_gap': abs(gap_pct),
                        'price': today_open
                    })
                    
                except Exception as e:
                    continue

            # Sort by Absolute Gap (Volatility)
            sorted_results = sorted(results, key=lambda x: x['abs_gap'], reverse=True)
            
            # Select Top N
            top_n = sorted_results[:self.limit]
            
            final_symbols = [item['symbol'] for item in top_n]
            
            # Log results
            msg = "Scanner Results:\n"
            for item in top_n:
                msg += f"- {item['symbol']}: {item['gap_pct']:.2f}% Gap\n"
            self.logger.info(msg)
            
            return final_symbols

        except Exception as e:
            self.logger.error(f"Scanner Failed: {e}")
            return []
