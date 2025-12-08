"""
Configuration module for Hai.
Handles environment variables and configuration settings.
"""

import os
import logging
from typing import Optional, List
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Logging configuration
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')

# HackerOne API credentials
TOKEN_NAME = os.environ.get('TOKEN_NAME')
TOKEN_VALUE = os.environ.get('TOKEN_VALUE')

# Slack credentials
SLACK_BOT_TOKEN = os.environ.get('SLACK_BOT_TOKEN')
SLACK_APP_TOKEN = os.environ.get('SLACK_APP_TOKEN')

# API URLs and Endpoints
HACKERONE_API_BASE_URL = os.environ.get('HACKERONE_API_BASE_URL', 'https://api.hackerone.com/v1')
HACKERONE_WEB_BASE_URL = os.environ.get('HACKERONE_WEB_BASE_URL', 'https://hackerone.com')
HACKERONE_DEFAULT_AVATAR_URL = os.environ.get('HACKERONE_DEFAULT_AVATAR_URL', 'https://www.hackerone.com/sites/default/files/2020-11/h1-default-avatar.jpg')
ERASER_API_BASE_URL = os.environ.get('ERASER_API_BASE_URL', 'https://app.eraser.io/api/render/prompt')
MERMAID_LIVE_BASE_URL = os.environ.get('MERMAID_LIVE_BASE_URL', 'https://mermaid.live/edit#pako:')
SLACK_API_BASE_URL = os.environ.get('SLACK_API_BASE_URL', 'https://slack.com/api')

# Application configuration
MAX_FOLLOWUP_OPTIONS = int(os.environ.get('MAX_FOLLOWUP_OPTIONS', '3'))
API_TIMEOUT = int(os.environ.get('API_TIMEOUT', '90'))  # Default to 90 seconds
ERASER_API_TIMEOUT = int(os.environ.get('ERASER_API_TIMEOUT', '180'))  # Eraser API timeout
ERASER_API_KEY = os.environ.get('ERASER_API_KEY')

# Pagination and Limits
HACKERONE_PAGE_SIZE = int(os.environ.get('HACKERONE_PAGE_SIZE', '100'))  # Maximum page size for HackerOne API
REPORT_ANALYTICS_TIMEOUT = int(os.environ.get('REPORT_ANALYTICS_TIMEOUT', '30'))  # Timeout for report analytics

# Text Processing Limits
MAX_TEXT_LENGTH = int(os.environ.get('MAX_TEXT_LENGTH', '3000'))  # Maximum text length for truncation
MAX_CONTENT_LENGTH = int(os.environ.get('MAX_CONTENT_LENGTH', '2000'))  # Maximum content length before truncation
URL_TRUNCATE_LENGTH = int(os.environ.get('URL_TRUNCATE_LENGTH', '80'))  # Maximum URL display length
PATH_TRUNCATE_LENGTH = int(os.environ.get('PATH_TRUNCATE_LENGTH', '50'))  # Maximum path display length
TITLE_TRUNCATE_LENGTH = int(os.environ.get('TITLE_TRUNCATE_LENGTH', '100'))  # Maximum title length in logs
SHORT_TITLE_LENGTH = int(os.environ.get('SHORT_TITLE_LENGTH', '50'))  # Short title length for compact display

# Slack Block Management
SLACK_MAX_BLOCKS_PER_MESSAGE = int(os.environ.get('SLACK_MAX_BLOCKS_PER_MESSAGE', '50'))  # Slack's block limit
SLACK_BLOCK_SAFETY_MARGIN = int(os.environ.get('SLACK_BLOCK_SAFETY_MARGIN', '5'))  # Reserve blocks for action buttons
SLACK_SAFE_BLOCK_LIMIT = SLACK_MAX_BLOCKS_PER_MESSAGE - SLACK_BLOCK_SAFETY_MARGIN

# Retry and Polling Configuration
API_RETRY_SLEEP_SECONDS = int(os.environ.get('API_RETRY_SLEEP_SECONDS', '2'))  # Sleep between API retries
DIAGRAM_UPLOAD_WAIT_SECONDS = int(os.environ.get('DIAGRAM_UPLOAD_WAIT_SECONDS', '15'))  # Wait time for diagram uploads

# Security and Validation
SUSPICIOUS_INPUT_MIN_LENGTH = int(os.environ.get('SUSPICIOUS_INPUT_MIN_LENGTH', '50'))  # Minimum length for suspicious input detection
VALIDITY_SCORE_RANGE = int(os.environ.get('VALIDITY_SCORE_RANGE', '100'))  # Range for validity certainty scores (0-100)

# Eraser API Configuration
ERASER_DIAGRAM_SPACING_HORIZONTAL = int(os.environ.get('ERASER_DIAGRAM_SPACING_HORIZONTAL', '80'))
ERASER_DIAGRAM_SPACING_VERTICAL = int(os.environ.get('ERASER_DIAGRAM_SPACING_VERTICAL', '80'))

# Severity Score Mapping (for report analytics)
SEVERITY_SCORES = {
    'critical': float(os.environ.get('SEVERITY_SCORE_CRITICAL', '2000.0')),
    'high': float(os.environ.get('SEVERITY_SCORE_HIGH', '1000.0')),
    'medium': float(os.environ.get('SEVERITY_SCORE_MEDIUM', '500.0')),
    'low': float(os.environ.get('SEVERITY_SCORE_LOW', '100.0')),
    'none': float(os.environ.get('SEVERITY_SCORE_NONE', '0.0'))
}

# Channel restrictions
ALLOWED_CHANNELS = os.environ.get('ALLOWED_CHANNELS', '')

# Logging Configuration
LOG_SEPARATOR_LENGTH = int(os.environ.get('LOG_SEPARATOR_LENGTH', '50'))  # Length of log separator lines
SLACK_BOT_ID = os.environ.get('SLACK_BOT_ID', '')  # Slack bot user ID for logging
SLACK_BOT_TYPE = os.environ.get('SLACK_BOT_TYPE', 'security_analyst')  # Bot type for logging

# Organization Configuration
ORGANIZATION_NAME = os.environ.get('ORGANIZATION_NAME', 'YourOrg')
ORGANIZATION_SECURITY_TEAM_NAME = os.environ.get('ORGANIZATION_SECURITY_TEAM_NAME', 'YourOrg Security Team')
ORGANIZATION_DOMAINS = os.environ.get('ORGANIZATION_DOMAINS', 'yourorg.com')
ORGANIZATION_PROGRAMS = os.environ.get('ORGANIZATION_PROGRAMS', 'yourorg:PUBLIC')
ORGANIZATION_PROGRAM_PATTERNS = os.environ.get('ORGANIZATION_PROGRAM_PATTERNS', 'YourOrg\\.com')

# Bot Identity Configuration
BOT_NAME = os.environ.get('BOT_NAME', 'H1 Analyst Agent')
BOT_RESTRICTION_MESSAGE_TEMPLATE = os.environ.get('BOT_RESTRICTION_MESSAGE_TEMPLATE', 
    'This {bot_name} is RESTRICTED to authorized {security_team} members only')
BOT_CONTACT_MESSAGE_TEMPLATE = os.environ.get('BOT_CONTACT_MESSAGE_TEMPLATE',
    'If you believe you should have access, please contact the {security_team} directly')
BOT_UNAUTHORIZED_ACCESS_MESSAGE = os.environ.get('BOT_UNAUTHORIZED_ACCESS_MESSAGE',
    'UNAUTHORIZED ACCESS - {security_team} Only')

def validate_config() -> None:
    """
    Validate required environment variables are present.
    Raises ValueError if required variables are missing.
    """
    required_vars = [
        ('TOKEN_NAME', TOKEN_NAME),
        ('TOKEN_VALUE', TOKEN_VALUE),
        ('SLACK_BOT_TOKEN', SLACK_BOT_TOKEN),
        ('SLACK_APP_TOKEN', SLACK_APP_TOKEN)
    ]
    
    missing_vars = [name for name, value in required_vars if not value]
    
    if missing_vars:
        raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")

def get_hackerone_auth() -> tuple:
    """
    Get HackerOne API authentication tuple.
    Returns a tuple of (token_name, token_value).
    """
    return (TOKEN_NAME, TOKEN_VALUE)

def get_slack_tokens() -> tuple:
    """
    Get Slack API tokens.
    Returns a tuple of (bot_token, app_token).
    """
    return (SLACK_BOT_TOKEN, SLACK_APP_TOKEN)

def get_max_followup_options() -> int:
    """
    Get the maximum number of follow-up options to support.
    Returns an integer representing the maximum number of follow-up options.
    """
    return MAX_FOLLOWUP_OPTIONS

def get_api_timeout() -> int:
    """
    Get the API timeout in seconds.
    Returns an integer representing the timeout for API requests.
    """
    return API_TIMEOUT

def get_eraser_api_timeout() -> int:
    """
    Get the Eraser API timeout in seconds.
    Returns an integer representing the timeout for Eraser API requests.
    """
    return ERASER_API_TIMEOUT

def get_eraser_api_key() -> str:
    """
    Get the Eraser.io API key.
    Returns the API key as a string.
    """
    return ERASER_API_KEY

def get_allowed_channels() -> List[str]:
    """
    Get list of allowed channel names from environment.
    Returns a list of channel names (with # prefix).
    """
    channels = ALLOWED_CHANNELS or ""
    return [ch.strip() for ch in channels.split(",") if ch.strip()]

def get_hackerone_api_base_url() -> str:
    """Get the HackerOne API base URL."""
    return HACKERONE_API_BASE_URL

def get_hackerone_web_base_url() -> str:
    """Get the HackerOne web base URL."""
    return HACKERONE_WEB_BASE_URL

def get_hackerone_default_avatar_url() -> str:
    """Get the HackerOne default avatar URL."""
    return HACKERONE_DEFAULT_AVATAR_URL

def get_eraser_api_base_url() -> str:
    """Get the Eraser API base URL."""
    return ERASER_API_BASE_URL

def get_mermaid_live_base_url() -> str:
    """Get the Mermaid Live base URL."""
    return MERMAID_LIVE_BASE_URL

def get_hackerone_page_size() -> int:
    """Get the HackerOne API page size."""
    return HACKERONE_PAGE_SIZE

def get_report_analytics_timeout() -> int:
    """Get the report analytics timeout."""
    return REPORT_ANALYTICS_TIMEOUT

def get_max_text_length() -> int:
    """Get the maximum text length for truncation."""
    return MAX_TEXT_LENGTH

def get_max_content_length() -> int:
    """Get the maximum content length before truncation."""
    return MAX_CONTENT_LENGTH

def get_url_truncate_length() -> int:
    """Get the maximum URL display length."""
    return URL_TRUNCATE_LENGTH

def get_path_truncate_length() -> int:
    """Get the maximum path display length."""
    return PATH_TRUNCATE_LENGTH

def get_slack_max_blocks() -> int:
    """Get the Slack maximum blocks per message."""
    return SLACK_MAX_BLOCKS_PER_MESSAGE

def get_slack_safe_block_limit() -> int:
    """Get the safe Slack block limit (with safety margin)."""
    return SLACK_SAFE_BLOCK_LIMIT

def get_slack_block_safety_margin() -> int:
    """Get the Slack block safety margin."""
    return SLACK_BLOCK_SAFETY_MARGIN

def get_api_retry_sleep_seconds() -> int:
    """Get the sleep time between API retries."""
    return API_RETRY_SLEEP_SECONDS

def get_diagram_upload_wait_seconds() -> int:
    """Get the wait time for diagram uploads."""
    return DIAGRAM_UPLOAD_WAIT_SECONDS

def get_suspicious_input_min_length() -> int:
    """Get the minimum length for suspicious input detection."""
    return SUSPICIOUS_INPUT_MIN_LENGTH

def get_validity_score_range() -> int:
    """Get the range for validity certainty scores."""
    return VALIDITY_SCORE_RANGE

def get_eraser_diagram_spacing() -> dict:
    """Get the Eraser diagram spacing configuration."""
    return {
        'horizontal': ERASER_DIAGRAM_SPACING_HORIZONTAL,
        'vertical': ERASER_DIAGRAM_SPACING_VERTICAL
    }

def get_severity_scores() -> dict:
    """Get the severity score mapping."""
    return SEVERITY_SCORES

def get_log_separator_length() -> int:
    """Get the length of log separator lines."""
    return LOG_SEPARATOR_LENGTH

def get_title_truncate_length() -> int:
    """Get the maximum title length in logs."""
    return TITLE_TRUNCATE_LENGTH

def get_short_title_length() -> int:
    """Get the short title length for compact display."""
    return SHORT_TITLE_LENGTH

def get_slack_bot_id() -> str:
    """Get the Slack bot user ID for logging."""
    return SLACK_BOT_ID

def get_slack_bot_type() -> str:
    """Get the bot type for logging."""
    return SLACK_BOT_TYPE

def get_organization_name() -> str:
    """Get the organization name."""
    return ORGANIZATION_NAME

def get_organization_security_team_name() -> str:
    """Get the organization security team name."""
    return ORGANIZATION_SECURITY_TEAM_NAME

def get_organization_domains() -> List[str]:
    """Get list of organization domains."""
    domains = ORGANIZATION_DOMAINS or ""
    return [domain.strip() for domain in domains.split(",") if domain.strip()]

def get_organization_programs() -> dict:
    """
    Get organization programs mapping.
    Returns a dictionary mapping program handles to visibility (PUBLIC/PRIVATE).
    """
    programs = ORGANIZATION_PROGRAMS or ""
    program_dict = {}
    for program_entry in programs.split(","):
        if ":" in program_entry:
            handle, visibility = program_entry.strip().split(":", 1)
            program_dict[handle.strip()] = visibility.strip()
    return program_dict

def get_organization_program_handles() -> List[str]:
    """Get list of organization program handles."""
    return list(get_organization_programs().keys())

def get_organization_program_mappings() -> dict:
    """
    Get organization program mappings for display names.
    Returns a dictionary mapping program handles to display names.
    For now, this returns the same as get_organization_programs() but could be extended
    to provide custom display names for programs.
    """
    programs = get_organization_programs()
    # For now, return handle as display name, but this could be customized
    return {handle: handle.replace('_', ' ').title() for handle in programs.keys()}

def get_organization_program_patterns() -> List[str]:
    """Get list of organization program patterns for regex matching."""
    patterns = ORGANIZATION_PROGRAM_PATTERNS or ""
    return [pattern.strip() for pattern in patterns.split(",") if pattern.strip()]

def get_bot_name() -> str:
    """Get the bot name."""
    return BOT_NAME

def get_bot_restriction_message() -> str:
    """Get the bot restriction message with organization-specific formatting."""
    return BOT_RESTRICTION_MESSAGE_TEMPLATE.format(
        bot_name=get_bot_name(),
        security_team=get_organization_security_team_name()
    )

def get_bot_contact_message() -> str:
    """Get the bot contact message with organization-specific formatting."""
    return BOT_CONTACT_MESSAGE_TEMPLATE.format(
        security_team=get_organization_security_team_name()
    )

def get_bot_unauthorized_access_message() -> str:
    """Get the bot unauthorized access message with organization-specific formatting."""
    return BOT_UNAUTHORIZED_ACCESS_MESSAGE.format(
        security_team=get_organization_security_team_name()
    )

def get_organization_program_regex_pattern() -> str:
    """
    Get the regex pattern for matching organization program reports.
    Returns a compiled regex pattern string.
    """
    patterns = get_organization_program_patterns()
    if not patterns:
        return r'^\s*(Unknown Program)\s*:\s+([^\s]+)\s+reported\s+(.+)'
    
    # Join patterns with OR operator and escape properly
    pattern_str = "|".join(patterns)
    return rf'^\s*({pattern_str})\s*:\s+([^\s]+)\s+reported\s+(.+)'
