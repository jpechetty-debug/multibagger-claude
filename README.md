# Intraday Signal Generator (NSE 5m)

A modular, production-oriented Python framework for generating intraday mean-reversion signals on NSE equities.

## Features
- **Hybrid Strategy**: Combines 15m Trend Filter (EMA) with 5m Mean Reversion (VWAP + BB + RSI).
- **Modes**: 
  - `Live`: Generates real-time signals via polling (simulated execution).
  - `Backtest`: Replays historical data to validate strategy.
- **Risk Management**: ATR-based stops, max daily loss circuit breaker, position sizing.
- **Alerts**: Telegram integration for instant signal notifications.
- **Extensible**: Modular Data Adapter meant for plugging in Kite Connect / Interactive Brokers.

## Prerequisites
- Windows 10/11
- Python 3.12.5
- VS Code (recommended)

## Installation

1. **Setup Environment**
   ```bash
   # Create virtual environment
   python -m venv venv
   
   # Activate (Windows)
   venv\Scripts\activate
   
   # Install dependencies
   pip install -r requirements.txt
   ```

2. **Configuration**
   - Copy the example config:
     ```bash
     copy config\config_example.yaml config\config.yaml
     ```
   - Edit `config/config.yaml`:
     - Add your Telegram Bot Token and Chat ID.
     - Adjust `symbols` (default Nifty 100 subset).
     - Tune `capital` and `risk parameters`.

## Usage

### 1. Backtest Mode
Runs the strategy on historical data (default: last 60 days due to yfinance intraday limits).
```bash
python run_backtest.py
```
**Output**:
- `sample_output.csv`: List of all trades.
- `reports/equity_curve.png`: Performance graph.

### 2. Live Signal Mode
Starts the scheduler to poll data every 5 minutes and generate alerts.
```bash
python run_live.py
```
**Output**:
- Real-time logs in console and `logs/` directory.
- Telegram alerts for Entry/Exit.
- `logs/trade_log_live.csv` updated incrementally.

## Data Source & Adapters
The project uses `yfinance` by default, which has delayed data and rate limits. 
**For Production**: 
1. Open `src/data_adapter.py`.
2. Implement your broker's websocket in `BrokerWebsocketStub` or create a new Adapter class.
3. Update `run_live.py` to use your new adapter.

## Strategy Logic
1. **Trend Filter (15m)**: Bullish if Price > EMA(50). Bearish if Price < EMA(50).
2. **Entry (5m)**:
   - **Long**: Trend Bullish AND Price dips below VWAP/LowerBB AND RSI < 40.
   - **Short**: Trend Bearish AND Price spikes above VWAP/UpperBB AND RSI > 60.
3. **Exit**:
   - SL: 1.5x ATR.
   - TP: 2.0x SL.

## Disclaimer
**This software is for educational purposes only.** It generates signals based on technical indicators. Do not trade real money without extensive testing and understanding the risks. The authors are not responsible for financial losses.
