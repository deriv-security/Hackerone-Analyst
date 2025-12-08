"""
Authorization module for Hai Bot.
Provides comprehensive access control to restrict bot usage to authorized security team members only.
"""

import os
import re
from typing import Set, Optional
from functools import wraps
from ..utils.logging import log_error, log_info, log_debug
from ..config import (
    get_bot_restriction_message,
    get_bot_contact_message,
    get_bot_unauthorized_access_message,
    get_organization_program_regex_pattern
)


class AuthorizationManager:
    """Manages user authorization for the Hai bot."""
    
    def __init__(self):
        """Initialize the authorization manager."""
        self._authorized_users: Optional[Set[str]] = None
        self._last_env_value: Optional[str] = None
        self._load_authorized_users()
    
    def _load_authorized_users(self) -> None:
        """Load authorized users from environment variables."""
        try:
            authorized_users_env = os.getenv('AUTHORIZED_USERS', '')
            
            # Check if environment has changed since last load
            if self._last_env_value == authorized_users_env and self._authorized_users is not None:
                return  # No change, use cached value
            
            self._last_env_value = authorized_users_env
            
            if not authorized_users_env:
                log_error(None, "AUTHORIZED_USERS environment variable not set - bot will deny all access")
                self._authorized_users = set()
                return
            
            # Parse comma-separated user IDs
            user_ids = [user_id.strip() for user_id in authorized_users_env.split(',') if user_id.strip()]
            self._authorized_users = set(user_ids)
            
            log_info(f"Authorization initialized with {len(self._authorized_users)} authorized users")
            
        except Exception as e:
            log_error(e, "Failed to load authorized users - bot will deny all access")
            self._authorized_users = set()
    
    def is_authorized(self, user_id: str) -> bool:
        """
        Check if a user is authorized to use the bot.
        
        Args:
            user_id: Slack user ID to check
            
        Returns:
            True if user is authorized, False otherwise
        """
        if not user_id:
            return False
        
        # Reload users in case environment has changed (important for tests)
        self._load_authorized_users()
        
        if self._authorized_users is None:
            return False
        
        return user_id in self._authorized_users
    
    def get_unauthorized_message(self) -> str:
        """
        Get the standard unauthorized access message.
        
        Returns:
            Standard warning message for unauthorized users
        """
        return "WARNING: Unauthorized access is prohibited. This agent is intended solely for the Security Team."
    
    def log_unauthorized_access(self, user_id: str, username: str, action: str, context: str = "") -> None:
        """
        Log unauthorized access attempts for security auditing.
        
        Args:
            user_id: Slack user ID of unauthorized user
            username: Username of unauthorized user
            action: Action that was attempted
            context: Additional context about the attempt
        """
        log_info(f"UNAUTHORIZED ACCESS ATTEMPT - User: {username} ({user_id}) | Action: {action} | Context: {context}")


# Global authorization manager instance
auth_manager = AuthorizationManager()


def require_authorization(func):
    """
    Decorator to require authorization for handler functions.
    
    This decorator should be applied to ALL handler functions that process user interactions.
    It will check if the user is authorized and block unauthorized access completely.
    
    Args:
        func: Handler function to protect
        
    Returns:
        Wrapped function with authorization check
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        # Check if this is a HackerOne notification message
        is_hackerone_notification = False
        
        # Special case for handle_message function - always allow it
        # This is needed because handle_message is the entry point for HackerOne notifications
        if func.__name__ == 'handle_message':
            log_debug("Authorization bypass: handle_message function is always allowed")
            return func(*args, **kwargs)
        
        # First check args (positional arguments)
        for arg in args:
            if isinstance(arg, dict):
                log_debug(f"Authorization: Checking for HackerOne notification bypass in arg: {arg}")
                
                # Check for attachments (attachment-based detection)
                attachments = arg.get('attachments', [])
                if attachments:
                    log_debug(f"Authorization: Found {len(attachments)} attachments")
                    
                    # Look for "New HackerOne Report" in attachment fallback text
                    for attachment in attachments:
                        fallback_text = attachment.get('fallback', '').lower()
                        log_debug(f"Authorization: Checking attachment fallback text: {repr(fallback_text)}")
                        
                        if "new hackerone report" in fallback_text:
                            log_debug("Authorization bypass: Found 'new hackerone report' in attachment fallback text")
                            is_hackerone_notification = True
                            break
                
                # If we already found a match, break out of the loop
                if is_hackerone_notification:
                    break
                
                # Fallback to text-based detection if no attachments or no match found
                if 'text' in arg and not is_hackerone_notification:
                    text = arg['text']
                    log_debug(f"Authorization: Checking text for HackerOne notification bypass: {repr(text)}")
                    
                    # Check for the specific format of HackerOne notifications:
                    # [Program Name]: [Reporter Name] reported [Report Title]
                    # Using configurable pattern to handle organization-specific programs
                    pattern = get_organization_program_regex_pattern()
                    log_debug(f"Authorization: Matching against pattern: {pattern}")
                    
                    program_reporter_pattern = re.match(pattern, text)
                    
                    if program_reporter_pattern:
                        groups = program_reporter_pattern.groups()
                        log_debug(f"Authorization bypass: Pattern matched! Program: {groups[0]}, Reporter: {groups[1]}, Title: {groups[2]}")
                        is_hackerone_notification = True
                        break
                    else:
                        log_debug("Authorization bypass: Pattern did not match")
        
        # If this is a HackerOne notification, allow it to proceed without authorization
        if is_hackerone_notification:
            log_debug("Authorization bypassed for HackerOne notification")
            return func(*args, **kwargs)
        
        # For all other interactions, proceed with standard authorization
        # Extract user information from the handler arguments
        user_id = None
        username = "Unknown"
        action = func.__name__
        
        # For Slack Bolt handlers, check both args and kwargs
        # First check args (positional arguments)
        for arg in args:
            if isinstance(arg, dict):
                # Check for slash command structure (has 'user_id' directly)
                if 'user_id' in arg:
                    user_id = arg['user_id']
                    username = arg.get('user_name', 'Unknown')
                    break
                # Check for button/interaction body structure first (has 'actions')
                elif 'actions' in arg and arg['actions']:
                    if 'user' in arg and isinstance(arg['user'], dict):
                        user_id = arg['user'].get('id')
                        username = arg['user'].get('name', 'Unknown')
                        break
                # Check for modal submission structure (has 'type': 'view_submission')
                elif arg.get('type') == 'view_submission' and 'user' in arg:
                    if isinstance(arg['user'], dict):
                        user_id = arg['user'].get('id')
                        username = arg['user'].get('name', 'Unknown')
                        break
                # Check for Slack event structure (mentions) - event is passed directly
                elif 'user' in arg:
                    # For mention events, user might be just the user ID string or a dict
                    if isinstance(arg['user'], dict):
                        user_id = arg['user'].get('id')
                        username = arg['user'].get('name', 'Unknown')
                    else:
                        user_id = arg['user']  # String user ID
                    break
                elif 'event' in arg and 'user' in arg['event']:
                    # For nested event structure
                    user_id = arg['event']['user']
                    break
        
        # Also check kwargs for Slack Bolt patterns
        if not user_id:
            # Check if event is passed as keyword argument
            if 'event' in kwargs and isinstance(kwargs['event'], dict):
                event = kwargs['event']
                if 'user' in event:
                    user_id = event['user']
            # Check if body is passed as keyword argument (for buttons)
            elif 'body' in kwargs and isinstance(kwargs['body'], dict):
                body = kwargs['body']
                if 'user' in body and isinstance(body['user'], dict):
                    user_id = body['user'].get('id')
                    username = body['user'].get('name', 'Unknown')
        
        # If we couldn't extract user ID, deny access
        if not user_id:
            log_error(None, f"Could not extract user ID from {action} - denying access. Args: {[type(arg).__name__ for arg in args]}, Kwargs: {list(kwargs.keys())}")
            return
        
        # Check authorization
        if not auth_manager.is_authorized(user_id):
            # FIRST: Call ack() immediately to prevent Slack warnings
            # Check both args and kwargs for ack function
            ack_called = False
            
            # Try args first (positional arguments)
            if args and hasattr(args[0], '__call__'):
                try:
                    args[0]()  # Call ack() first
                    ack_called = True
                except Exception:
                    pass  # If it's not ack, ignore the error
            
            # If not found in args, try kwargs
            if not ack_called and 'ack' in kwargs and hasattr(kwargs['ack'], '__call__'):
                try:
                    kwargs['ack']()  # Call ack() from kwargs
                    ack_called = True
                except Exception:
                    pass  # If it fails, ignore the error
            
            # THEN: Log unauthorized access attempt
            auth_manager.log_unauthorized_access(user_id, username, action)
            
            # FINALLY: Send unauthorized message to the user
            try:
                # Try to send ephemeral message if possible
                from ..api.slack import SlackAPI
                slack = SlackAPI()
                
                # Extract channel info and timestamp for response
                channel_id = None
                timestamp = None
                
                # Check positional arguments first
                for arg in args:
                    if isinstance(arg, dict):
                        if 'channel' in arg and isinstance(arg['channel'], dict):
                            channel_id = arg['channel'].get('id')
                        elif 'channel' in arg and isinstance(arg['channel'], str):
                            channel_id = arg['channel']
                        
                        if 'ts' in arg:
                            timestamp = arg['ts']
                        
                        if channel_id:
                            break
                
                # If not found in args, check kwargs (for Slack Bolt patterns)
                if not channel_id:
                    if 'event' in kwargs and isinstance(kwargs['event'], dict):
                        event = kwargs['event']
                        if 'channel' in event:
                            channel_id = event['channel']
                        if 'ts' in event:
                            timestamp = event['ts']
                
                if channel_id:
                    # Send strong warning message similar to channel restrictions
                    warning_blocks = [
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": "🚨 *UNAUTHORIZED USER ACCESS DETECTED* 🚨"
                            }
                        },
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": (
                                    f"⛔ *{get_bot_restriction_message()}*\n\n"
                                    "⚠️ *This access attempt has been logged and reported to the Security Team.*\n\n"
                                    f"❓ {get_bot_contact_message()}"
                                )
                            }
                        },
                        {
                            "type": "context",
                            "elements": [
                                {
                                    "type": "mrkdwn",
                                    "text": f"🔍 User: <@{user_id}> | 📅 {timestamp or 'Unknown timestamp'} | 🚫 Unauthorized Access"
                                }
                            ]
                        }
                    ]
                    
                    slack.send_message(
                        text=f"🚨 {get_bot_unauthorized_access_message()}",
                        blocks=warning_blocks,
                        channel=channel_id,
                        thread_ts=timestamp
                    )
            except Exception as e:
                log_error(e, f"Failed to send unauthorized message to user {user_id}")
            
            # Block the action completely
            return
        
        # User is authorized, proceed with the original function
        return func(*args, **kwargs)
    
    return wrapper


def check_authorization(user_id: str) -> bool:
    """
    Direct authorization check function.
    
    Args:
        user_id: Slack user ID to check
        
    Returns:
        True if authorized, False otherwise
    """
    return auth_manager.is_authorized(user_id)


def get_unauthorized_message() -> str:
    """
    Get the standard unauthorized message.
    
    Returns:
        Standard unauthorized access message
    """
    return auth_manager.get_unauthorized_message()
