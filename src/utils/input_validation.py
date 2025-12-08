"""
Input validation utilities for Hai Bot.
Provides comprehensive validation for all user inputs.
"""

import re
from typing import Dict, Any, Optional, Tuple, List
from ..utils.logging import log_error, log_debug

def validate_slash_command(command_text: str) -> bool:
    """
    Validate slash command input against allowlist patterns.
    
    Args:
        command_text: The command text to validate
        
    Returns:
        True if valid, False otherwise
    """
    if not command_text:
        return False
        
    # Define allowlist patterns for different commands
    patterns = {
        "report": r"^[a-zA-Z0-9\-_]{1,20}$",  # Alphanumeric with limited special chars
        "analyze": r"^[a-zA-Z0-9\-_\s]{1,100}$",  # Allow spaces but limit length
        "ask": r"^[a-zA-Z0-9\-_\s\.\,\?\!]{1,500}$",  # Allow punctuation for questions
        "help": r"^[a-zA-Z0-9\-_\s]{0,50}$",  # Optional topic
        "status": r"^[a-zA-Z0-9\-_]{1,20}$"  # Report ID
    }
    
    # Extract command type and validate against appropriate pattern
    parts = command_text.split(maxsplit=1)
    if not parts:
        return False
        
    command_type = parts[0].lower()
    if command_type not in patterns:
        log_debug(f"Invalid command type: {command_type}")
        return False
        
    if len(parts) > 1:
        is_valid = bool(re.match(patterns[command_type], parts[1]))
        if not is_valid:
            log_debug(f"Command argument failed validation: {parts[1]}")
        return is_valid
    
    return True

def validate_button_payload(payload: Dict[str, Any]) -> bool:
    """
    Validate button click payload.
    
    Args:
        payload: The button payload to validate
        
    Returns:
        True if valid, False otherwise
    """
    if not isinstance(payload, dict):
        return False
        
    # Check for required fields
    required_fields = ['type', 'user', 'actions']
    if not all(field in payload for field in required_fields):
        return False
        
    # Validate action_id format
    if 'actions' in payload and payload['actions']:
        for action in payload['actions']:
            if 'action_id' not in action:
                return False
                
            # Validate action_id against allowlist pattern
            action_id = action.get('action_id', '')
            if not re.match(r'^[a-z_]{1,30}$', action_id):
                log_debug(f"Invalid action_id format: {action_id}")
                return False
                
            # Validate value format if present
            if 'value' in action:
                value = action.get('value', '')
                # Allow only specific format: action_name_reportid
                if not re.match(r'^[a-z_]+_[a-zA-Z0-9\-]{1,30}$', value):
                    log_debug(f"Invalid action value format: {value}")
                    return False
    
    return True

def sanitize_user_input(text: str) -> str:
    """
    Sanitize user input to prevent injection attacks.
    
    Args:
        text: The text to sanitize
        
    Returns:
        Sanitized text
    """
    if not text:
        return ""
        
    # Remove potentially dangerous characters
    sanitized = re.sub(r'[<>]', '', text)
    
    # Limit length
    if len(sanitized) > 1000:
        sanitized = sanitized[:1000] + "... (truncated)"
        
    return sanitized

def validate_channel_id(channel_id: str) -> bool:
    """
    Validate a Slack channel ID.
    
    Args:
        channel_id: The channel ID to validate
        
    Returns:
        True if valid, False otherwise
    """
    # Slack channel IDs start with C and are followed by alphanumeric characters
    return bool(re.match(r'^C[A-Z0-9]{8,}$', channel_id))

def validate_user_id(user_id: str) -> bool:
    """
    Validate a Slack user ID.
    
    Args:
        user_id: The user ID to validate
        
    Returns:
        True if valid, False otherwise
    """
    # Slack user IDs start with U and are followed by alphanumeric characters
    return bool(re.match(r'^U[A-Z0-9]{8,}$', user_id))

def validate_thread_ts(thread_ts: str) -> bool:
    """
    Validate a Slack thread timestamp.
    
    Args:
        thread_ts: The thread timestamp to validate
        
    Returns:
        True if valid, False otherwise
    """
    # Slack timestamps are a Unix timestamp with a dot and microseconds
    return bool(re.match(r'^\d+\.\d+$', thread_ts))
