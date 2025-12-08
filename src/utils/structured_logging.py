"""
Structured logging for Hai bot interactions.
Logs complete interaction data to JSON files for analysis.
"""

import json
import os
from datetime import datetime
from typing import Dict, Any, List, Optional
from pathlib import Path

from .secret_protection import sanitize_for_logging
from ..config import get_slack_bot_id, get_slack_bot_type

# Constants
LOGS_DIR = Path(__file__).parent.parent.parent / "logs"
INTERACTIONS_LOG = LOGS_DIR / "interactions.jsonl"

def _ensure_logs_directory():
    """Ensure the logs directory exists."""
    LOGS_DIR.mkdir(exist_ok=True)

def _get_user_interaction_count(user_id: str) -> int:
    """Get the current interaction count for a user by reading the log file."""
    _ensure_logs_directory()
    
    if not INTERACTIONS_LOG.exists():
        return 1  # This will be the first interaction
    
    count = 0
    try:
        with open(INTERACTIONS_LOG, 'r') as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                    if entry.get('user_id') == user_id:
                        count += 1
                except json.JSONDecodeError:
                    continue  # Skip malformed lines
    except Exception:
        pass  # Fail silently
    
    return count + 1  # Return the count for the next interaction

def log_interaction(
    user_id: str,
    channel_id: str,
    thread_id: str,
    user_message: str,
    response_text: str = "",
    duration: float = 0.0,
    input_attachments: Optional[List[str]] = None,
    output_attachments: Optional[List[str]] = None,
    request_timestamp: Optional[datetime] = None
):
    """
    Log a structured interaction to the JSON log file.
    
    Args:
        user_id: Slack user ID who initiated the interaction
        channel_id: Slack channel ID where interaction occurred
        thread_id: Slack thread timestamp
        user_message: The user's input message
        response_text: The bot's response text (optional)
        duration: Processing duration in seconds
        input_attachments: List of input attachment filenames
        output_attachments: List of output attachment filenames
        request_timestamp: When the request started (defaults to now)
    """
    try:
        _ensure_logs_directory()
        
        # Get current interaction count for this user
        chat_history_length = _get_user_interaction_count(user_id)
        
        # Create timestamps
        now = datetime.utcnow()
        created_at = now.isoformat() + "Z"
        req_timestamp = (request_timestamp or now).isoformat() + "Z"
        
        # Sanitize all text fields to remove secrets before logging
        sanitized_user_message = sanitize_for_logging(user_message)
        sanitized_response_text = sanitize_for_logging(response_text)
        
        # Create the structured log entry
        log_entry = {
            "created_at": created_at,
            "request_timestamp": req_timestamp,
            "bot_id": get_slack_bot_id(),
            "type_of_bot": get_slack_bot_type(),
            "user_id": user_id,
            "channel_id": channel_id,
            "thread_id": thread_id,
            "user_message": sanitized_user_message,
            "input_attachments": input_attachments or [],
            "system_prompt": "",  # Always empty for privacy
            "chat_history_length": chat_history_length,
            "response_text": sanitized_response_text,
            "duration": duration,
            "output_attachments": output_attachments or []
        }
        
        # Append to the JSONL file
        with open(INTERACTIONS_LOG, 'a') as f:
            f.write(json.dumps(log_entry) + '\n')
            
    except Exception:
        # Fail silently to not disrupt bot operation
        pass

def log_mention_interaction(
    event: Dict[str, Any],
    report_id: str,
    response_text: str = "",
    duration: float = 0.0,
    request_timestamp: Optional[datetime] = None
):
    """
    Log a mention interaction (user asking for report analysis).
    
    Args:
        event: Slack event data
        report_id: The HackerOne report ID being analyzed
        response_text: The analysis response
        duration: Processing time in seconds
        request_timestamp: When the request started
    """
    user_message = f"Analyze report {report_id}: {event.get('text', '')}"
    
    log_interaction(
        user_id=event.get('user', ''),
        channel_id=event.get('channel', ''),
        thread_id=event.get('ts', ''),
        user_message=user_message,
        response_text=response_text,
        duration=duration,
        request_timestamp=request_timestamp
    )

def log_button_interaction(
    user_id: str,
    channel_id: str,
    thread_id: str,
    button_action: str,
    report_id: str,
    response_text: str = "",
    duration: float = 0.0,
    output_attachments: Optional[List[str]] = None,
    request_timestamp: Optional[datetime] = None
):
    """
    Log a button interaction (user clicking bot buttons).
    
    Args:
        user_id: Slack user ID
        channel_id: Slack channel ID
        thread_id: Slack thread timestamp
        button_action: Description of button pressed
        report_id: Associated report ID
        response_text: Bot's response
        duration: Processing time
        output_attachments: Generated files
        request_timestamp: When request started
    """
    user_message = f"Button: {button_action} for report {report_id}"
    
    log_interaction(
        user_id=user_id,
        channel_id=channel_id,
        thread_id=thread_id,
        user_message=user_message,
        response_text=response_text,
        duration=duration,
        output_attachments=output_attachments,
        request_timestamp=request_timestamp
    )

def log_modal_interaction(
    user_id: str,
    channel_id: str,
    thread_id: str,
    modal_type: str,
    user_input: str,
    report_id: str,
    response_text: str = "",
    duration: float = 0.0,
    request_timestamp: Optional[datetime] = None
):
    """
    Log a modal interaction (user submitting forms).
    
    Args:
        user_id: Slack user ID
        channel_id: Slack channel ID
        thread_id: Slack thread timestamp
        modal_type: Type of modal (e.g., "Ask Harry", "Update Status")
        user_input: User's input in the modal
        report_id: Associated report ID
        response_text: Bot's response
        duration: Processing time
        request_timestamp: When request started
    """
    user_message = f"Modal: {modal_type} for report {report_id} - {user_input}"
    
    log_interaction(
        user_id=user_id,
        channel_id=channel_id,
        thread_id=thread_id,
        user_message=user_message,
        response_text=response_text,
        duration=duration,
        request_timestamp=request_timestamp
    )

def get_user_interaction_count(user_id: str) -> int:
    """
    Get the current interaction count for a user without incrementing.
    
    Args:
        user_id: Slack user ID
        
    Returns:
        Current interaction count for the user
    """
    return _get_user_interaction_count(user_id) - 1  # Subtract 1 since _get_user_interaction_count returns next count
