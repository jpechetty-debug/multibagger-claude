# API Reference

The Trading Bot exposes a global `state` object and several control functions in the browser console for developers.

## Data Structures

### `state` Object
The central store of truth.
```javascript
const state = {
    active: boolean,       // Is bot running?
    intervalId: number,    // JS Interval ID
    signals: Signal[],     // Array of generated signals
    config: Config         // Current configuration
};
```

### `Signal` Object
```javascript
{
    id: number,            // Unique timestamp ID
    time: Date,            // Signal generation time
    symbol: string,        // e.g., "NIFTY"
    type: "BUY" | "SELL" | "HOLD",
    price: string,         // e.g., "19450.00"
    indicators: {
        rsi: number,       // 0-100
        macd: string,      // "Bullish" | "Bearish"
        bb: string         // "Upper Band" | "Lower Band" | "Mid Band"
    },
    confidence: number     // 0-100
}
```

## Functions

### `startBot()`
Initializes the signal generation loop. Sets `state.active` to true.

### `stopBot()`
Pauses the signal generation. Clears the interval but preserves data.

### `updateDisplay()`
Refreshes the DOM. Re-renders the KPI cards and the Signal Table based on current `state.signals`.

### `generateSignal(symbol)`
*   **Input**: `symbol` (string)
*   **Output**: `Signal` object or `null`
*   **Description**: Core logic function. Fetches price, calculates indicators, and applies logic rules.

## Extending the Bot
To connect real data, override the `generateSignal` function to fetch from an API:

```javascript
/* EXAMPLE OVERRIDE */
async function generateSignal(symbol) {
    const data = await fetch(`https://api.mybroker.com/quote/${symbol}`);
    // ... reimplement logic ...
}
```
