#!/usr/bin/env python3
"""
Launcher script for Hai.
Starts the Slack bot with proper error handling and logging.
"""

import sys
import logging
from src.main import main
from src.utils.logging import setup_logging

if __name__ == "__main__":
    try:
        # Only set up logging once at the top level
        setup_logging()
        
        # Start the bot
        main()
        
    except KeyboardInterrupt:
        logging.info("Bot stopped by user")
        sys.exit(0)
        
    except Exception as e:
        logging.error(f"Bot crashed: {str(e)}")
        sys.exit(1)
