import yfinance as yf
import json

def test_news(symbol):
    print(f"--- Fetching news for {symbol} ---")
    try:
        ticker = yf.Ticker(symbol)
        news = ticker.news
        if news:
            print(f"Found {len(news)} news items.")
            print(json.dumps(news[0], indent=2))
        else:
            print(f"No news found for {symbol}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_news("HSCL.BO")
