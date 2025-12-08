"""
Logging configuration for Hai.
Provides consistent logging setup across the application.
"""

import sys
import logging
from typing import Optional

class CustomFormatter(logging.Formatter):
    """Custom formatter that includes log level in the output."""
    
    def format(self, record: logging.LogRecord) -> str:
        """Format the log record with level prefix."""
        if record.levelno == logging.INFO:
            return f"[INFO] {record.getMessage()}"
        elif record.levelno == logging.DEBUG:
            return f"[DEBUG] {record.getMessage()}"
        elif record.levelno == logging.WARNING:
            return f"[WARNING] {record.getMessage()}"
        elif record.levelno == logging.ERROR:
            return f"[ERROR] {record.getMessage()}"
        elif record.levelno == logging.CRITICAL:
            return f"[CRITICAL] {record.getMessage()}"
        return super().format(record)

def setup_logging(level: Optional[str] = None) -> None:
    """
    Set up logging with proper log levels and formatting.
    
    Args:
        level: Optional log level name. Defaults to INFO if not provided.
    """
    # Get log level from parameter or environment variable
    log_level_name = level or 'INFO'
    log_level = getattr(logging, log_level_name.upper(), logging.INFO)
    
    # Configure the root logger
    logger = logging.getLogger()
    logger.setLevel(log_level)
    
    # Remove any existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # Create console handler with custom formatter
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    
    # Create a more detailed formatter
    formatter = logging.Formatter(
        '[%(asctime)s] [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # Force immediate output
    sys.stdout.flush()
    
    # Log initialization with visible separator
    print("\n" + "="*50)
    print("[Hai BOT] Logging System Initialized")
    print("="*50 + "\n")
    
    # Also log this in the actual log (without the separators)
    logging.info("[Hai BOT] Hai Bot started")

def log_event(message: str) -> None:
    """
    Log an event with a special prefix to ensure visibility.
    
    Args:
        message: The message to log
    """
    logging.info(f"[Hai BOT] {message}")

def log_api_request(url: str, purpose: str) -> None:
    """
    Log an API request with its purpose.
    
    Args:
        url: The API endpoint URL
        purpose: The purpose of the API request
    """
    logging.info(f"[ENDPOINT] {url} - {purpose}")

def log_debug_response(response_text: str, max_length: int = 1000) -> None:
    """
    Log API response content at debug level, truncating if too long.
    
    Args:
        response_text: The response text to log
        max_length: Maximum length before truncating
    """
    if len(response_text) > max_length:
        logging.debug(f"Response content (truncated): {response_text[:max_length]}...")
    else:
        logging.debug(f"Response content: {response_text}")

def log_button_press(button_name: str, report_id: str) -> None:
    """
    Log a button press event.
    
    Args:
        button_name: The name of the button pressed
        report_id: The associated report ID
    """
    logging.info(f"BUTTON PRESSED: {button_name} for Report #{report_id}")

def log_info(message: str) -> None:
    """
    Log a message at INFO level.
    
    Args:
        message: The message to log
    """
    logging.info(message)

def log_debug(message: str) -> None:
    """
    Log a message at DEBUG level.
    
    Args:
        message: The message to log
    """
    logging.debug(message)

def log_warning(message: str) -> None:
    """
    Log a message at WARNING level.
    
    Args:
        message: The message to log
    """
    logging.warning(message)

def log_error(error: Exception, context: str = "") -> None:
    """
    Log an error with optional context.
    
    Args:
        error: The exception to log
        context: Optional context about where the error occurred
    """
    if context:
        logging.error(f"Error in {context}: {str(error)}")
    else:
        logging.error(str(error))
