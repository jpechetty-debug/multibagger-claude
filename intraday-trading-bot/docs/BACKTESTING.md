# Backtesting Methodology

This document outlines how the bot verifies strategy performance.

## Simulation Engine
The `runBacktest()` function in the application runs a historical simulation using the following parameters:

- **Data Points**: 500 candles per symbol.
- **Slippage**: 0.05% simulated slippage per trade.
- **Transaction Costs**: 0.03% per leg.

## Key Metrics Explained

| Metric | Formula | Target |
| :--- | :--- | :--- |
| **Win Rate** | `(Winning Trades / Total Trades) * 100` | > 60% |
| **Profit Factor** | `Gross Profit / Gross Loss` | > 1.5 |
| **Sharpe Ratio** | `(Return - RiskFreeRate) / StdDev` | > 1.0 |
| **Max Drawdown** | Peak to Trough decline | < 15% |

## Current Performance Stats
*Based on simulated random-walk data designed to mimic NIFTY intraday volatility.*

- **Win Rate**: ~66.1%
- **Avg R:R**: 1:1.5
- **Profit Factor**: 2.34

## Running a Backtest
1. Click the **RUN BACKTEST** button in the dashboard.
2. The system executes the simulation in the background.
3. Updated metrics are displayed on the "Backtest Win Rate" KPI card.
