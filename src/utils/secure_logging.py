"""
Secure logging utilities to prevent secret leakage.
Provides functions to safely log errors and responses without exposing sensitive information.
"""

import re
import logging
from typing import Optional, Dict, Any

# Patterns to detect and mask common secrets
SECRET_PATTERNS = [
    # Tokens and keys
    (r'token["\s]*[:=]["\s]*[a-zA-Z0-9_.-]{10,}', 'token=***'),
    (r'key["\s]*[:=]["\s]*[a-zA-Z0-9_.-]{10,}', 'key=***'),
    (r'secret["\s]*[:=]["\s]*[a-zA-Z0-9_.-]{10,}', 'secret=***'),
    (r'password["\s]*[:=]["\s]*[a-zA-Z0-9_.-]{8,}', 'password=***'),
    (r'auth["\s]*[:=]["\s]*[a-zA-Z0-9_.-]{10,}', 'auth=***'),
    
    # Authorization headers
    (r'authorization["\s]*[:=]["\s]*[a-zA-Z0-9_.-]+', 'authorization=***'),
    (r'bearer\s+[a-zA-Z0-9_.-]+', 'bearer ***'),
    (r'basic\s+[a-zA-Z0-9+/=]+', 'basic ***'),
    (r'authorization:\s*bearer\s+[a-zA-Z0-9_.-]+', 'authorization: bearer ***'),
    
    # API keys in URLs
    (r'[?&]api_key=[a-zA-Z0-9_.-]+', '?api_key=***'),
    (r'[?&]token=[a-zA-Z0-9_.-]+', '?token=***'),
    
    # Slack tokens (specific patterns)
    (r'xoxb-[a-zA-Z0-9-]+', 'xoxb-***'),
    (r'xoxp-[a-zA-Z0-9-]+', 'xoxp-***'),
    (r'xapp-[a-zA-Z0-9-]+', 'xapp-***'),
    
    # HackerOne tokens (username:token format)
    (r'[a-zA-Z0-9_.-]+:[a-zA-Z0-9_.-]{20,}', '***:***'),
    
    # Base64 encoded data (potential secrets)
    (r'[a-zA-Z0-9+/]{40,}={0,2}', '***base64***'),
]

# Safe headers that can be logged
SAFE_HEADERS = {
    'content-type', 'content-length', 'date', 'server', 'cache-control',
    'expires', 'last-modified', 'etag', 'vary', 'x-request-id',
    'x-ratelimit-limit', 'x-ratelimit-remaining', 'x-ratelimit-reset'
}

def sanitize_text(text: str) -> str:
    """
    Sanitize text by removing or masking potential secrets.
    
    Args:
        text: The text to sanitize
        
    Returns:
        Sanitized text with secrets masked
    """
    if not text:
        return text
    
    sanitized = text
    
    # Apply all secret patterns
    for pattern, replacement in SECRET_PATTERNS:
        sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE)
    
    return sanitized

def sanitize_headers(headers: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sanitize HTTP headers by removing sensitive ones.
    
    Args:
        headers: Dictionary of HTTP headers
        
    Returns:
        Dictionary with only safe headers
    """
    if not headers:
        return {}
    
    safe_headers = {}
    for key, value in headers.items():
        if key.lower() in SAFE_HEADERS:
            safe_headers[key] = value
        else:
            safe_headers[key] = '***'
    
    return safe_headers

def safe_log_error(error: Exception, context: str = "") -> None:
    """
    Safely log an error without exposing secrets.
    
    Args:
        error: The exception to log
        context: Optional context about where the error occurred
    """
    error_msg = sanitize_text(str(error))
    
    if context:
        logging.error(f"Error in {context}: {error_msg}")
    else:
        logging.error(error_msg)

def safe_log_response_error(error: Exception, url: str, response=None) -> None:
    """
    Safely log an API response error without exposing secrets.
    
    Args:
        error: The exception that occurred
        url: The API URL (will be sanitized)
        response: The response object (optional)
    """
    sanitized_url = sanitize_text(url)
    safe_log_error(error, f"API request to {sanitized_url}")
    
    if response is not None:
        # Log status code (safe)
        if hasattr(response, 'status_code'):
            logging.error(f"Response status code: {response.status_code}")
        
        # Log only safe headers
        if hasattr(response, 'headers'):
            safe_headers = sanitize_headers(dict(response.headers))
            logging.error(f"Response headers (sanitized): {safe_headers}")
        
        # Never log response content - it may contain secrets
        logging.error("Response content: [REDACTED FOR SECURITY]")

def safe_log_debug_response(response_text: str, max_length: int = 500) -> None:
    """
    Safely log API response content at debug level with sanitization.
    
    Args:
        response_text: The response text to log
        max_length: Maximum length before truncating
    """
    if not response_text:
        return
    
    # Sanitize the response text
    sanitized_text = sanitize_text(response_text)
    
    # Truncate if too long
    if len(sanitized_text) > max_length:
        sanitized_text = sanitized_text[:max_length] + "... [TRUNCATED]"
    
    logging.debug(f"Response content (sanitized): {sanitized_text}")

def safe_str(obj: Any) -> str:
    """
    Safely convert an object to string, sanitizing any potential secrets.
    
    Args:
        obj: The object to convert to string
        
    Returns:
        Sanitized string representation
    """
    return sanitize_text(str(obj))
