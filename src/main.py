"""
Main entry point for Hai.
Sets up and runs the Slack bot with all handlers configured.
"""

import logging
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from .config import validate_config, get_slack_tokens, get_max_followup_options
from .utils.logging import log_event
from .handlers.button_handlers import (
    handle_analyze_profile,
    handle_view_profile,
    handle_attachment_analysis,
    handle_full_report_analysis,
    handle_suggest_followup,
    handle_followup_option,
    handle_generate_mermaid,
    handle_generate_eraser_diagram,
    handle_retry_analysis,
    handle_update_status,
    handle_update_status_submission,
    handle_acknowledge_report,
    handle_ask_harry,
    handle_ask_harry_submission
)
from .handlers.mention_handlers import handle_mention
from .handlers.message_handlers import handle_message
from .handlers.slash_commands import handle_report_command

def setup_bot() -> App:
    """
    Set up and configure the Slack bot.
    
    Returns:
        App: Configured Slack bot app
    """
    # Validate environment variables
    validate_config()
    
    # Get Slack tokens
    bot_token, app_token = get_slack_tokens()
    
    # Initialize the bot
    app = App(token=bot_token)
    
    # Register mention handler
    app.event("app_mention")(handle_mention)
    
    # Register message handler for HackerOne notifications
    app.event("message")(handle_message)
    
    # Register slash command handlers
    app.command("/report")(handle_report_command)
    
    # Register button click handlers
    app.action("analyze_profile")(handle_analyze_profile)
    app.action("view_profile")(handle_view_profile)
    app.action("analyze_attachments")(handle_attachment_analysis)
    app.action("full_report")(handle_full_report_analysis)
    app.action("suggest_followup")(handle_suggest_followup)
    # Register handlers for each follow-up option button
    for i in range(get_max_followup_options()):
        app.action(f"followup_option_{i}")(handle_followup_option)
    app.action("generate_mermaid")(handle_generate_mermaid)
    app.action("generate_eraser_diagram")(handle_generate_eraser_diagram)
    app.action("retry_analysis")(handle_retry_analysis)
    app.action("update_status")(handle_update_status)
    app.view("update_status_modal")(handle_update_status_submission)
    app.action("acknowledge_report")(handle_acknowledge_report)
    app.action("ask_harry")(handle_ask_harry)
    
    # Register view submission handler for the Ask Harry modal
    app.view("ask_harry_modal")(handle_ask_harry_submission)
    
    return app

def main() -> None:
    """Main entry point for the bot."""
    try:
        # Logging is already set up in run.py, so don't set it up again here
        log_event("Starting Hai bot...")
        
        # Set up the bot
        app = setup_bot()
        bot_token, app_token = get_slack_tokens()
        
        # Start the bot
        handler = SocketModeHandler(app, app_token)
        handler.start()
        
        log_event("Hai bot is running!")
        
    except Exception as e:
        logging.error(f"Failed to start Hai bot: {str(e)}")
        raise

if __name__ == "__main__":
    main()
