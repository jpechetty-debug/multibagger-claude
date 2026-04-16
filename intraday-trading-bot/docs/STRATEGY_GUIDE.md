# Strategy Guide

The Enterprise Intraday Trading Bot utilizes a **Mean Reversion** strategy combined with **Momentum Confirmation**. It seeks price extremes (Overbought/Oversold) that are confirmed by momentum shifts.

## The "Trident" Indicator Setup

We use three logic gates to filter noise. A valid signal requires **ALL THREE** gates to be open simultaneously.

### 1. Relative Strength Index (RSI)
*Period: 14*
*   **Purpose**: Identifies potential reversals at price extremes.
*   **Buy Zone**: RSI < 30 (Market is oversold, price may bounce).
*   **Sell Zone**: RSI > 70 (Market is overbought, price may drop).
*   **Neutral**: 40-60 (No action).

### 2. MACD (Moving Average Convergence Divergence)
*Settings: 12 (Fast), 26 (Slow), 9 (Signal)*
*   **Purpose**: Confirms the momentum direction. We don't catch falling knives; we wait for the turn.
*   **Bullish**: MACD Line crosses ABOVE Signal Line.
*   **Bearish**: MACD Line crosses BELOW Signal Line.

### 3. Bollinger Bands
*Settings: 20 SMA, 2 StdDev*
*   **Purpose**: Volatility context.
*   **Buy Condition**: Price touches or breaks BELOW the Lower Band (Statistical anomaly to the downside).
*   **Sell Condition**: Price touches or breaks ABOVE the Upper Band (Statistical anomaly to the upside).

---

## Signal Generation Logic

### BUY Signal (Long Entry)
1.  **RSI** is below 30.
2.  **MACD** histogram is positive (or crossing up).
3.  **Price** is at or below the Lower Bollinger Band.

### SELL Signal (Short Entry)
1.  **RSI** is above 70.
2.  **MACD** histogram is negative (or crossing down).
3.  **Price** is at or above the Upper Bollinger Band.

### HOLD Signal (Wait)
*   Any condition where the above 3 rules do not align.
*   Typically occurs during consolidation (RSI 40-60).

## Confidence Scoring
The bot assigns a confidence % to every signal:
*   **Base Score**: 50%
*   **Strong RSI**: +1.5% for every point beyond threshold.
*   **Trend Alignment**: +15% if price action aligns with higher timeframe trend (simulated).
*   **Volume Spike**: +15% (simulated volume confirmation).

*Minimum threshold to display signal: 65%*
