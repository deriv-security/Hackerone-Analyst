"""
Message handlers for Hai.
Handles Slack message events for HackerOne notifications.
"""

import re
from datetime import datetime
from typing import Dict, Any, Optional, Match, Tuple

from ..api.hackerone import HackerOneAPI
from ..api.slack import SlackAPI
from ..utils.logging import log_error, log_event, log_debug, log_info
from ..utils.structured_logging import log_mention_interaction
from ..utils.authorization import require_authorization
from ..config import get_allowed_channels, get_organization_program_patterns
from .mention_handlers import analyze_report_with_logging

# Initialize API clients
hackerone = HackerOneAPI()
slack = SlackAPI()

# Removed custom emoji reactions as they are no longer needed

def _is_hackerone_notification(event: Dict[str, Any]) -> bool:
    """
    Check if the message is a HackerOne notification based on its attachments or text.
    
    Args:
        event: The Slack event data
        
    Returns:
        bool: True if the message is a HackerOne notification, False otherwise
    """
    # Debug logging
    log_debug(f"Checking if message is HackerOne notification: {event}")
    
    # First try attachment-based detection (preferred method)
    attachments = event.get('attachments', [])
    if attachments:
        log_debug(f"Found {len(attachments)} attachments in the event")
        
        # Look for "New HackerOne Report" in attachment fallback text
        for attachment in attachments:
            fallback_text = attachment.get('fallback', '').lower()
            log_debug(f"Checking attachment fallback text: {repr(fallback_text)}")
            
            if "new hackerone report" in fallback_text:
                log_debug("Found 'new hackerone report' in attachment fallback text")
                return True
        
        log_debug("No HackerOne notification indicators found in attachments")
    else:
        log_debug("No attachments found in the event")
    
    # Fallback to text-based detection for backward compatibility with tests
    if 'text' in event:
        text = event['text']
        log_debug(f"Falling back to text-based detection: {repr(text)}")
        
        # Check for the specific format of HackerOne notifications:
        # [Program Name]: [Reporter Name] reported [Report Title]
        program_patterns = get_organization_program_patterns()
        pattern = rf'^\s*({"|".join(program_patterns)})\s*:\s+([^\s]+)\s+reported\s+(.+)'
        log_debug(f"Matching against pattern: {pattern}")
        
        program_reporter_pattern = re.match(pattern, text)
        
        if program_reporter_pattern:
            groups = program_reporter_pattern.groups()
            log_debug(f"Pattern matched! Program: {groups[0]}, Reporter: {groups[1]}, Title: {groups[2]}")
            return True
        else:
            log_debug("Pattern did not match, not a HackerOne notification")
    
    return False

def _is_new_report_notification(event_or_text: Any) -> bool:
    """
    Check if the message is a notification about a new report.
    
    Args:
        event_or_text: The Slack event data or message text
        
    Returns:
        bool: True if the message is about a new report, False otherwise
    """
    log_debug(f"Checking if message is a new report notification")
    
    # Handle both event and text for backward compatibility
    if isinstance(event_or_text, dict):
        # For attachment-based detection, we already verified it's a new report
        # in _is_hackerone_notification by checking for "new hackerone report"
        # So we can just return True here
        return True
    elif isinstance(event_or_text, str):
        # Legacy text-based detection for backward compatibility with tests
        text = event_or_text
        log_debug(f"Using legacy text-based detection: {repr(text)}")
        
        # Check if the message contains "reported" but not "closed as" or "awarded a bounty"
        has_reported = 'reported' in text
        has_closed = 'closed as' in text
        has_bounty = 'awarded a bounty' in text
        
        log_debug(f"Message contains 'reported': {has_reported}")
        log_debug(f"Message contains 'closed as': {has_closed}")
        log_debug(f"Message contains 'awarded a bounty': {has_bounty}")
        
        result = (has_reported and not has_closed and not has_bounty)
        log_debug(f"Is new report notification: {result}")
        
        return result
    else:
        log_debug(f"Unsupported type for _is_new_report_notification: {type(event_or_text)}")
        return False

def _extract_report_id_from_event(event: Dict[str, Any]) -> Optional[str]:
    """
    Extract the HackerOne report ID from a Slack event message.
    
    Args:
        event: The Slack event dictionary.
        
    Returns:
        Optional[str]: The report ID if found, None otherwise
    """
    log_debug("Starting report ID extraction process")
    
    # Check for attachments
    attachments = event.get('attachments', [])
    if not attachments:
        log_debug("No attachments found in the event. Exiting.")
        return None
    
    # 1. First try to extract from structured fields
    for attachment in attachments:
        fields = attachment.get('fields', [])
        for field in fields:
            if field.get('title') == 'Report ID':
                report_id = field.get('value', '').lstrip('#').strip()
                if report_id:
                    log_debug(f"Extracted Report ID from 'fields': {report_id}")
                    return report_id
    
    # 2. If not found in fields, check in attachment text fields
    text_fields = ['text', 'pretext', 'fallback']
    for attachment in attachments:
        for field_name in text_fields:
            text = attachment.get(field_name, '')
            log_debug(f"Checking {field_name} for report ID: {repr(text)}")
            
            # Try the standard pattern first
            match = re.search(r'Report\s+ID\s*#?\s*(\d{6,8})', text)
            if match:
                report_id = match.group(1)
                log_debug(f"Extracted Report ID using standard pattern from '{field_name}': {report_id}")
                return report_id
            
            # Try the more flexible pattern as fallback
            match = re.search(r'reports?[/#](\d{6,8})', text, re.IGNORECASE)
            if match:
                report_id = match.group(1)
                log_debug(f"Extracted Report ID using flexible pattern from '{field_name}': {report_id}")
                return report_id
    
    # 3. As a last resort, check the main message text
    if 'text' in event:
        text = event['text']
        log_debug(f"Checking main message text for report ID: {repr(text)}")
        
        # Try both patterns
        match = re.search(r'Report\s+ID\s*#?\s*(\d{6,8})', text)
        if match:
            report_id = match.group(1)
            log_debug(f"Extracted Report ID from main text: {report_id}")
            return report_id
        
        match = re.search(r'reports?[/#](\d{6,8})', text, re.IGNORECASE)
        if match:
            report_id = match.group(1)
            log_debug(f"Extracted Report ID using flexible pattern from main text: {report_id}")
            return report_id
    
    log_debug("No Report ID found in event")
    return None

def _extract_report_id(text: str) -> Optional[str]:
    """
    Extract the report ID from a HackerOne notification message.
    
    Args:
        text: The message text
        
    Returns:
        Optional[str]: The report ID if found, None otherwise
    """
    log_debug(f"Extracting report ID from: {repr(text)}")
    
    # Look for the report ID pattern at the end of the message
    # Using a more flexible pattern to handle potential invisible characters or formatting
    pattern = r'Report\s+ID\s*#?\s*(\d{6,8})'
    log_debug(f"Using report ID pattern: {pattern}")
    
    match = re.search(pattern, text)
    if match:
        report_id = match.group(1)
        log_debug(f"Found report ID: {report_id}")
        return report_id
    else:
        log_debug("No report ID found in the message")
        return None

def _is_valid_report_id(report_id: str) -> bool:
    """
    Validate that a report ID is within reasonable bounds for HackerOne.
    
    Args:
        report_id: The report ID to validate
        
    Returns:
        True if valid, False otherwise
    """
    log_debug(f"Validating report ID: {report_id}")
    
    try:
        id_int = int(report_id)
        log_debug(f"Converted report ID to integer: {id_int}")
        
        # HackerOne report IDs typically start around 100000 and go up to ~99999999
        is_valid = 100000 <= id_int <= 99999999
        log_debug(f"Report ID validation result: {is_valid}")
        
        return is_valid
    except ValueError:
        log_debug(f"Failed to convert report ID to integer: {report_id}")
        return False

def handle_hackerone_message(event: Dict[str, Any], client: Any = None) -> None:
    """
    Handle HackerOne notification messages with reaction support.
    
    Args:
        event: The Slack event data
        client: Optional Slack client for adding reactions
    """
    log_info("Handling HackerOne message")
    request_start = datetime.utcnow()
    report_id = None  # Initialize to prevent UnboundLocalError in exception handler
    
    try:
        # Extract the report ID
        report_id = _extract_report_id_from_event(event)
        
        # If we couldn't extract from attachments, try the text field (for backward compatibility with tests)
        if not report_id and 'text' in event:
            log_debug("Falling back to text-based report ID extraction")
            report_id = _extract_report_id(event['text'])
        
        if not report_id:
            log_event("Could not extract report ID from HackerOne notification")
            return
        
        # Validate the report ID
        if not _is_valid_report_id(report_id):
            log_event(f"Invalid report ID extracted from HackerOne notification: {report_id}")
            return
        
        # Check if channel is allowed
        channel_id = event['channel']
        channel_name = slack.get_channel_name(channel_id)
        allowed_channels = get_allowed_channels()
        
        # Block if no allowed channels configured OR channel not in allowed list
        channel_formatted = f"#{channel_name}" if channel_name else "#None"
        
        if not allowed_channels or channel_formatted not in allowed_channels:
            log_event(f"Blocked automatic analysis in unauthorized channel: #{channel_name} (ID: {channel_id})")
            return
        
        log_event(f"Automatically analyzing report {report_id} from HackerOne notification")
        
        # Send initial response in a thread
        response = slack.send_message(
            text=f"Analyzing report {report_id}... Please wait.",
            channel=channel_id,
            thread_ts=event['ts']
        )
        
        # Analyze the report and get the results
        # We need to modify analyze_report_with_logging to return the results
        # For now, we'll use a direct call to the HackerOne API
        try:
            # Get the report data from HackerOne
            report_data = hackerone.get_report(report_id)
            
            if report_data and 'data' in report_data:
                # Extract the certainty score and predicted validity
                attributes = report_data.get('data', {}).get('attributes', {})
                certainty_score = attributes.get('validityCertaintyScore')
                predicted_validity = attributes.get('predictedValidity')
                
                log_debug(f"Report analysis results - Certainty: {certainty_score}, Validity: {predicted_validity}")
                
                # Reaction functionality has been removed
        except Exception as e:
            log_error(e, f"Error getting report data from HackerOne: {e}")
        
        # This will send the analysis results to the thread
        analyze_report_with_logging(report_id, channel_id, event['ts'], event, request_start)
        
    except Exception as e:
        log_error(e, "Error handling HackerOne notification message")
        
        # Log error interaction with safe report_id handling
        log_mention_interaction(
            event=event,
            report_id=report_id if report_id else "ERROR",
            response_text=f"Error handling HackerOne notification: {str(e)}",
            duration=(datetime.utcnow() - request_start).total_seconds(),
            request_timestamp=request_start
        )

@require_authorization
def handle_message(event: Dict[str, Any], client: Any = None) -> None:
    """
    Handle message events from the HackerOne App.
    
    This handler specifically looks for notifications about new reports
    and automatically analyzes them.
    
    Args:
        event: The Slack event data
        client: Optional Slack client for adding reactions
    """
    request_start = datetime.utcnow()
    report_id = None  # Initialize to prevent UnboundLocalError in exception handler
    
    try:
        log_debug(f"Received message event: {event}")
        
        # Skip messages without text and attachments
        if 'text' not in event and 'attachments' not in event:
            log_debug("Message has no text or attachments field, ignoring")
            return
        
        # Skip messages that don't match the HackerOne notification format
        if not _is_hackerone_notification(event):
            log_debug("Message is not a HackerOne notification, ignoring")
            return
        
        log_debug(f"Processing HackerOne notification")
        
        # Handle the HackerOne message
        handle_hackerone_message(event, client)
        
    except Exception as e:
        log_error(e, "Error handling HackerOne notification message")
        
        # Log error interaction with safe report_id handling
        log_mention_interaction(
            event=event,
            report_id=report_id if report_id else "ERROR",
            response_text=f"Error handling HackerOne notification: {str(e)}",
            duration=(datetime.utcnow() - request_start).total_seconds(),
            request_timestamp=request_start
        )
