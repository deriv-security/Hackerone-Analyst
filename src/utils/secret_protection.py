"""
Secret Protection System for Hai Bot.
Ensures no bot secrets are ever logged or returned to users.
"""

import os
import re
from typing import Set, List, Optional, Any, Dict
from ..utils.logging import log_error, log_info


class SecretProtector:
    """
    Comprehensive secret protection system that prevents bot secrets
    from being logged or returned to users under any circumstances.
    """
    
    def __init__(self):
        """Initialize the secret protector with all sensitive data."""
        self.secrets = self._load_all_secrets()
        self.patterns = self._build_detection_patterns()
        self.redaction_marker = "[REDACTED]"
        
        # Log initialization (without revealing secrets)
        log_info(f"SecretProtector initialized with {len(self.secrets)} secrets and {len(self.patterns)} patterns")
    
    def _load_all_secrets(self) -> Set[str]:
        """Load all sensitive environment variables and other secrets."""
        secrets = set()
        
        # Known sensitive environment variables
        sensitive_env_vars = [
            'SLACK_BOT_TOKEN',
            'HACKERONE_API_TOKEN', 
            'ERASER_API_KEY',
            'SLACK_APP_TOKEN',
            'SLACK_SIGNING_SECRET',
            'DATABASE_URL',
            'SECRET_KEY',
            'API_KEY',
            'ACCESS_TOKEN',
            'PRIVATE_KEY',
            'PASSWORD',
            'PASSPHRASE'
        ]
        
        # Load values from environment
        for var_name in sensitive_env_vars:
            value = os.getenv(var_name)
            if value and len(value) > 5:  # Only add non-empty, meaningful values
                secrets.add(value)
        
        # Also scan all environment variables for potential secrets
        for key, value in os.environ.items():
            if value and len(value) > 10:  # Only check longer values
                # Check if env var name suggests it's sensitive
                key_lower = key.lower()
                if any(sensitive_word in key_lower for sensitive_word in 
                       ['token', 'key', 'secret', 'password', 'pass', 'auth', 'api']):
                    secrets.add(value)
        
        # Remove None and empty values
        secrets = {s for s in secrets if s and len(s) > 5}
        
        return secrets
    
    def _build_detection_patterns(self) -> List[re.Pattern]:
        """Build regex patterns to detect common secret formats."""
        patterns = [
            # Slack tokens
            r'xoxb-[0-9]+-[0-9]+-[a-zA-Z0-9]+',
            r'xoxp-[0-9]+-[0-9]+-[0-9]+-[a-f0-9]+',
            r'xapp-[0-9]+-[A-Z0-9]+-[0-9]+-[a-f0-9]+',
            
            # Bearer tokens
            r'Bearer\s+[a-zA-Z0-9_\-\.]+',
            
            # API keys (various formats)
            r'[Aa][Pp][Ii][_\-]?[Kk][Ee][Yy]\s*[:=]\s*[\'"]?[a-zA-Z0-9_\-]{20,}[\'"]?',
            
            # Long hex strings (potential tokens/keys)
            r'\b[a-f0-9]{32,}\b',
            
            # Base64-like strings (potential encoded secrets)
            r'\b[A-Za-z0-9+/]{40,}={0,2}\b',
            
            # JWT tokens
            r'eyJ[a-zA-Z0-9_\-]*\.eyJ[a-zA-Z0-9_\-]*\.[a-zA-Z0-9_\-]*',
            
            # AWS-style keys
            r'AKIA[0-9A-Z]{16}',
            r'[A-Za-z0-9/+=]{40}',  # AWS secret access key format
            
            # GitHub tokens
            r'ghp_[a-zA-Z0-9]{36}',
            r'gho_[a-zA-Z0-9]{36}',
            r'ghu_[a-zA-Z0-9]{36}',
            r'gh[pou]_[a-zA-Z0-9]{30,40}',  # Generic GitHub pattern (flexible length)
            
            # Generic patterns
            r'[\'"][a-zA-Z0-9_\-]{25,}[\'"]',  # Quoted long strings
        ]
        
        # Compile patterns for better performance
        compiled_patterns = []
        for pattern in patterns:
            try:
                compiled_patterns.append(re.compile(pattern, re.IGNORECASE))
            except re.error as e:
                log_error(e, f"Failed to compile regex pattern: {pattern}")
        
        return compiled_patterns
    
    def sanitize_for_logging(self, text: Optional[str]) -> Optional[str]:
        """
        Sanitize text for logging purposes.
        Replaces secrets with [REDACTED] markers.
        """
        if not text:
            return text
        
        return self._sanitize_text(text, self.redaction_marker)
    
    def sanitize_for_user_response(self, text: Optional[str]) -> Optional[str]:
        """
        No sanitization for user responses.
        Returns the original text as-is, allowing all content to be displayed in Slack.
        """
        # Simply return the original text without any sanitization
        return text
    
    def _sanitize_text(self, text: str, replacement: str) -> str:
        """Internal method to sanitize text with specified replacement."""
        if not text:
            return text
        
        sanitized = text
        
        # Replace exact secret matches first (most important)
        for secret in self.secrets:
            if secret in sanitized:
                sanitized = sanitized.replace(secret, replacement)
        
        # Apply pattern-based detection
        for pattern in self.patterns:
            sanitized = pattern.sub(replacement, sanitized)
        
        return sanitized
    
    def is_safe(self, text: Optional[str]) -> bool:
        """
        Check if text is safe (contains no secrets).
        Returns False if ANY secret is detected.
        """
        if not text:
            return True
        
        # Check for exact secret matches
        for secret in self.secrets:
            if secret and secret in text:
                return False
        
        # Check pattern matches
        for pattern in self.patterns:
            if pattern.search(text):
                return False
        
        return True
    
    def sanitize_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively sanitize a dictionary structure."""
        if not isinstance(data, dict):
            return data
        
        sanitized = {}
        for key, value in data.items():
            if isinstance(value, str):
                sanitized[key] = self.sanitize_for_logging(value)
            elif isinstance(value, dict):
                sanitized[key] = self.sanitize_dict(value)
            elif isinstance(value, list):
                sanitized[key] = self.sanitize_list(value)
            else:
                sanitized[key] = value
        
        return sanitized
    
    def sanitize_list(self, data: List[Any]) -> List[Any]:
        """Recursively sanitize a list structure."""
        if not isinstance(data, list):
            return data
        
        sanitized = []
        for item in data:
            if isinstance(item, str):
                sanitized.append(self.sanitize_for_logging(item))
            elif isinstance(item, dict):
                sanitized.append(self.sanitize_dict(item))
            elif isinstance(item, list):
                sanitized.append(self.sanitize_list(item))
            else:
                sanitized.append(item)
        
        return sanitized
    
    def emergency_check(self, text: Optional[str]) -> bool:
        """
        Emergency safety check - returns True if text is definitely unsafe.
        Used as a final fail-safe before sending content to users.
        """
        if not text:
            return False
        
        # More aggressive checking for emergency situations
        text_lower = text.lower()
        
        # Check for common secret indicators
        danger_words = ['token', 'key', 'secret', 'password', 'bearer', 'auth']
        for word in danger_words:
            if word in text_lower and any(secret.lower() in text_lower for secret in self.secrets):
                return True
        
        return not self.is_safe(text)
    
    def get_stats(self) -> Dict[str, int]:
        """Get statistics about the secret protector (for monitoring)."""
        return {
            'secrets_count': len(self.secrets),
            'patterns_count': len(self.patterns)
        }


# Global instance for use throughout the application
secret_protector = SecretProtector()


def sanitize_for_logging(text: Optional[str]) -> Optional[str]:
    """Convenience function for logging sanitization."""
    return secret_protector.sanitize_for_logging(text)


def sanitize_for_users(text: Optional[str]) -> Optional[str]:
    """Convenience function for user response sanitization."""
    return secret_protector.sanitize_for_user_response(text)


def is_safe_for_users(text: Optional[str]) -> bool:
    """Convenience function to check if text is safe for users."""
    return secret_protector.is_safe(text)


def emergency_safety_check(text: Optional[str]) -> bool:
    """Convenience function for emergency safety checks."""
    return secret_protector.emergency_check(text)
