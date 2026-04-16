# Enterprise Intraday Trading Bot

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Version](https://img.shields.io/badge/version-1.0.0-green.svg)
![Status](https://img.shields.io/badge/status-production--ready-orange.svg)

A production-ready, single-file HTML application implementing an institutional-grade trading bot with real-time signal generation, backtesting, and live monitoring capabilities.

## Key Features

- **Zero Dependency Deployment**: Entirely self-contained in a single HTML file.
- **Enterprise UX**: Dark mode design system inspired by institutional terminals.
- **Real-Time Signal Generation**: Calculates RSI, MACD, and Bollinger Bands locally.
- **Live Dashboard**: Monitors NIFTY and BANKNIFTY simulation by default.
- **Backtesting Engine**: Built-in verification of strategy performance.
- **Privacy Focused**: All data processing happens client-side in your browser.

## Quick Start

1.  **Download**: Clone this repo or simply download [index.html](./index.html).
2.  **Run**: Open `index.html` in any modern web browser (Chrome, Edge, Firefox, Safari).
3.  **Trade**: Click "START BOT" to begin signal generation.

## Strategy Overview

The bot uses a confluence model requiring agreement from three indicators to generate high-confidence signals:

| Indicator | Buy Condition | Sell Condition |
| :--- | :--- | :--- |
| **RSI (14)** | < 30 (Oversold) | > 70 (Overbought) |
| **MACD (12,26,9)** | Bullish Crossover | Bearish Crossover |
| **Bollinger Bands** | Price < Lower Band | Price > Upper Band |

*For detailed strategy mechanics, see [STRATEGY_GUIDE.md](./docs/STRATEGY_GUIDE.md).*

## Documentation

- [Installation Guide](./docs/INSTALLATION.md)
- [API Reference](./docs/API_REFERENCE.md)
- [Strategy Guide](./docs/STRATEGY_GUIDE.md)
- [Backtesting Methodology](./docs/BACKTESTING.md)

## License

This project is licensed under the MIT License - see the [LICENSE](./LICENSE) file for details.

## Disclaimer

**Educational Purpose Only.** This software simulates trading strategies and does not constitute financial advice. Always backtest thoroughly and consult with a certified financial advisor before live trading.
