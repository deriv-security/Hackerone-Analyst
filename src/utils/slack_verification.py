"""
Slack request verification utilities for Hai Bot.
Ensures all incoming Slack requests are authentic.
"""

import hmac
import hashlib
import time
from typing import Dict, Any, Optional
from ..utils.logging import log_error, log_debug

def get_slack_signing_secret() -> str:
    """
    Get the Slack signing secret from environment variables.
    
    Returns:
        The Slack signing secret
    """
    from ..config import get_slack_tokens
    import os
    
    # Try to get from environment directly first
    signing_secret = os.environ.get('SLACK_SIGNING_SECRET')
    
    # If not available, use a fallback method
    if not signing_secret:
        # This is a fallback and not ideal - in production, 
        # SLACK_SIGNING_SECRET should be set separately
        log_debug("SLACK_SIGNING_SECRET not found, using fallback method")
        
    return signing_secret

def verify_slack_request(headers: Dict[str, str], body: str) -> bool:
    """
    Verify that a request came from Slack.
    
    Args:
        headers: Request headers
        body: Request body as string
        
    Returns:
        True if verified, False otherwise
    """
    try:
        # Get Slack signing secret
        signing_secret = get_slack_signing_secret()
        if not signing_secret:
            log_error(None, "Slack signing secret not configured")
            return False
        
        # Get request timestamp and signature
        timestamp = headers.get("X-Slack-Request-Timestamp", "")
        signature = headers.get("X-Slack-Signature", "")
        
        if not timestamp or not signature:
            log_error(None, "Missing Slack verification headers")
            return False
        
        # Check timestamp to prevent replay attacks
        current_timestamp = int(time.time())
        if abs(current_timestamp - int(timestamp)) > 60 * 5:
            log_error(None, f"Slack request timestamp too old: {timestamp}")
            return False
        
        # Create signature base string
        sig_basestring = f"v0:{timestamp}:{body}"
        
        # Calculate HMAC signature
        my_signature = "v0=" + hmac.new(
            signing_secret.encode(),
            sig_basestring.encode(),
            hashlib.sha256
        ).hexdigest()
        
        # Compare signatures
        is_valid = hmac.compare_digest(my_signature, signature)
        
        if not is_valid:
            log_error(None, "Slack request signature verification failed")
            
        return is_valid
        
    except Exception as e:
        log_error(e, "Error verifying Slack request")
        return False

def verify_slack_token(token: Optional[str]) -> bool:
    """
    Verify a Slack verification token.
    
    Args:
        token: The token to verify
        
    Returns:
        True if verified, False otherwise
    """
    import os
    
    if not token:
        return False
        
    expected_token = os.environ.get('SLACK_VERIFICATION_TOKEN')
    if not expected_token:
        log_error(None, "Slack verification token not configured")
        return False
        
    return hmac.compare_digest(token, expected_token)

def log_verification_attempt(success: bool, request_info: Dict[str, Any]) -> None:
    """
    Log a verification attempt for security monitoring.
    
    Args:
        success: Whether verification succeeded
        request_info: Information about the request
    """
    import json
    from datetime import datetime
    
    # Create log entry
    log_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "success": success,
        "ip": request_info.get("ip", "unknown"),
        "endpoint": request_info.get("endpoint", "unknown"),
        "user_agent": request_info.get("user_agent", "unknown")
    }
    
    # Log at appropriate level
    if success:
        log_debug(f"Slack verification succeeded: {json.dumps(log_entry)}")
    else:
        log_error(None, f"Slack verification failed: {json.dumps(log_entry)}")
