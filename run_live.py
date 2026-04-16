import yaml
import logging
import sys
import os
from src.utils import setup_logger
from src.bot_engine import BotEngine

# Add src to path
sys.path.append(os.path.join(os.getcwd(), 'src'))

def load_config():
    with open("config/config.yaml", "r") as f:
        return yaml.safe_load(f)

def main():
    logger = setup_logger("IntradaySignals")
    logger.info("Initializing Production Bot...")
    
    try:
        config = load_config()
    except FileNotFoundError:
        logger.error("config/config.yaml not found!")
        return

    # Secrets check
    if config['telegram']['bot_token'] == "YOUR_BOT_TOKEN_HERE":
        logger.warning("Telegram token not configured. Bot will run without alerts.")
        config['telegram']['enabled'] = False

    engine = BotEngine(config)
    engine.start()

if __name__ == "__main__":
    main()
