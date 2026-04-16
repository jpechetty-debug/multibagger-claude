
import logging
import time
from src.bot_engine import BotEngine
from src.utils import setup_logger
import yaml

# Setup basic config
def load_config():
    with open("config/config.yaml", "r") as f:
        config = yaml.safe_load(f)
    # Ensure a reasonable number of symbols for test
    # If list is small, we won't see much diff, but if > 20, batch helps.
    return config

def verify_speed():
    logger = setup_logger("IntradaySignals.SpeedTest")
    config = load_config()
    
    # Init Engine
    engine = BotEngine(config)
    
    print(f"Starting Cycle with {len(engine.symbols)} symbols...")
    start_time = time.time()
    
    # Run ONE cycle manually
    engine.run_cycle()
    
    end_time = time.time()
    duration = end_time - start_time
    
    print(f"\n=== Speed Test Results ===")
    print(f"Symbols: {len(engine.symbols)}")
    print(f"Total Cycle Time: {duration:.2f} seconds")
    print(f"Avg per Symbol: {duration/len(engine.symbols):.2f}s")
    
    if duration < 10:
        print("PASS: Cycle time < 10s (Target Reached)")
    else:
        print("WARNING: Cycle time might still be high.")

if __name__ == "__main__":
    verify_speed()
