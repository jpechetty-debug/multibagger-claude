import logging
import sys
import os
from logging.handlers import TimedRotatingFileHandler
from datetime import datetime
import pytz

def setup_logger(name: str, log_dir: str = "logs", level: str = "INFO") -> logging.Logger:
    """
    Sets up a logger with console and file handlers (daily rotation).
    """
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper()))
    
    # Avoid duplicate handlers
    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Console Handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    # File Handler (Daily Rotation)
    filename = os.path.join(log_dir, f"{datetime.now().strftime('%Y%m%d')}_trading.log")
    fh = TimedRotatingFileHandler(filename, when="midnight", interval=1, backupCount=30)
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    return logger

def get_current_time(timezone_str: str = "Asia/Kolkata") -> datetime:
    """Returns the current time in the specified timezone."""
    tz = pytz.timezone(timezone_str)
    return datetime.now(tz)

def round_to_tick(price: float, tick_size: float = 0.05) -> float:
    """Rounds price to the nearest tick size."""
    return round(price / tick_size) * tick_size
