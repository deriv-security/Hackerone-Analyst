"""
URL processing utility module.
Handles extremely long URLs in report content to prevent API payload issues.
"""

import re
from typing import Tuple, List
from urllib.parse import urlparse, parse_qs
from .logging import log_debug, log_info

def is_s3_url(url: str) -> bool:
    """
    Check if a URL is an Amazon S3 URL.
    
    Args:
        url: The URL to check
        
    Returns:
        bool: True if the URL is an S3 URL
    """
    if not url:
        return False
        
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        
        # Check for various S3 URL patterns
        s3_patterns = [
            r'.*\.s3\.amazonaws\.com$',
            r'.*\.s3\.[a-z0-9-]+\.amazonaws\.com$',
            r'^s3\.amazonaws\.com$',
            r'^s3\.[a-z0-9-]+\.amazonaws\.com$'
        ]
        
        for pattern in s3_patterns:
            if re.match(pattern, domain):
                return True
                
        return False
    except Exception:
        return False

def truncate_s3_url(url: str, max_length: int = 200) -> str:
    """
    Intelligently truncate an Amazon S3 URL while preserving key information.
    
    Args:
        url: The S3 URL to truncate
        max_length: Maximum length for the truncated URL
        
    Returns:
        str: Truncated S3 URL with important parts preserved
    """
    try:
        parsed = urlparse(url)
        domain = parsed.netloc
        path = parsed.path
        query = parsed.query
        
        # Extract bucket name and object key
        bucket_name = ""
        object_key = ""
        
        if domain.startswith('s3.') or domain == 's3.amazonaws.com':
            # Format: s3.amazonaws.com/bucket-name/object-key
            path_parts = [p for p in path.split('/') if p]
            if path_parts:
                bucket_name = path_parts[0]
                object_key = '/'.join(path_parts[1:]) if len(path_parts) > 1 else ""
        else:
            # Format: bucket-name.s3.amazonaws.com/object-key
            bucket_name = domain.split('.')[0]
            object_key = path.lstrip('/')
        
        # Create a readable S3 format
        if object_key:
            # Get filename from object key
            object_parts = object_key.split('/')
            filename = object_parts[-1] if object_parts else ""
            
            # Create shortened format
            if len(object_parts) > 2:
                # Show first directory and filename
                short_key = f"{object_parts[0]}/.../{filename}"
            else:
                short_key = object_key
            
            base_format = f"s3://{bucket_name}/{short_key}"
        else:
            base_format = f"s3://{bucket_name}/"
        
        # Add indication of query parameters if they exist
        if query:
            # Check for common S3 parameters
            query_params = parse_qs(query)
            param_indicators = []
            
            if any(key.startswith(('X-Amz', 'AWSAccessKeyId', 'Signature')) for key in query_params):
                param_indicators.append("auth")
            if 'response-content-disposition' in query_params:
                param_indicators.append("download")
            if 'versionId' in query_params:
                param_indicators.append("version")
            
            if param_indicators:
                base_format += f" [+{', '.join(param_indicators)}]"
            else:
                base_format += " [+params]"
        
        # If still too long, truncate further
        if len(base_format) > max_length:
            if object_key and len(object_parts) > 1:
                # Just show bucket and filename
                filename = object_parts[-1]
                if len(filename) > 30:
                    filename = filename[:27] + "..."
                base_format = f"s3://{bucket_name}/.../{filename}"
                if query:
                    base_format += " [+params]"
            
            # Final truncation if still too long
            if len(base_format) > max_length:
                base_format = base_format[:max_length-3] + "..."
        
        return base_format
        
    except Exception:
        # Fallback to generic truncation
        return url[:max_length-3] + "..."

def truncate_url(url: str, max_length: int = 200) -> str:
    """
    Intelligently truncate a URL while preserving important parts.
    
    Args:
        url: The URL to truncate
        max_length: Maximum length for the truncated URL
        
    Returns:
        str: Truncated URL with important parts preserved
    """
    # Handle None and empty string cases
    if not url:
        return ""
    
    if len(url) <= max_length:
        return url
    
    # Check if this is an S3 URL and handle it specially
    if is_s3_url(url):
        return truncate_s3_url(url, max_length)
    
    try:
        parsed = urlparse(url)
        
        # Always preserve the scheme and domain
        base = f"{parsed.scheme}://{parsed.netloc}"
        
        # If just the base is too long, truncate the domain
        if len(base) > max_length - 10:  # Leave room for "..."
            domain_parts = parsed.netloc.split('.')
            if len(domain_parts) > 2:
                # Keep first and last part of domain
                truncated_domain = f"{domain_parts[0]}...{domain_parts[-1]}"
                base = f"{parsed.scheme}://{truncated_domain}"
            
            if len(base) > max_length - 3:
                return base[:max_length-3] + "..."
        
        remaining_length = max_length - len(base) - 3  # 3 for "..."
        
        # Try to include some path information
        if parsed.path and remaining_length > 10:
            path_parts = parsed.path.split('/')
            if len(path_parts) > 3:
                # Keep first and last meaningful parts
                meaningful_parts = [p for p in path_parts if p]
                if len(meaningful_parts) > 2:
                    truncated_path = f"/{meaningful_parts[0]}/.../{meaningful_parts[-1]}"
                else:
                    truncated_path = parsed.path[:remaining_length-3] + "..."
            else:
                truncated_path = parsed.path[:remaining_length]
            
            return f"{base}{truncated_path}..."
        
        return f"{base}..."
        
    except Exception:
        # Fallback to simple truncation if URL parsing fails
        return url[:max_length-3] + "..."

def extract_and_process_urls(text: str, max_url_length: int = 200) -> Tuple[str, List[str]]:
    """
    Extract URLs from text, truncate long ones, and return processed text with URL list.
    
    Args:
        text: Text containing URLs
        max_url_length: Maximum length for URLs before truncation
        
    Returns:
        Tuple of (processed_text, list_of_original_urls)
    """
    if not text:
        return text or "", []
    
    # Pattern to match URLs (http/https)
    url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+[^\s<>"{}|\\^`\[\].,;:!?)]'
    
    urls_found = re.findall(url_pattern, text)
    long_urls = []
    processed_text = text
    
    for url in urls_found:
        if len(url) > max_url_length:
            long_urls.append(url)
            truncated_url = truncate_url(url, max_url_length)
            processed_text = processed_text.replace(url, truncated_url)
            log_debug(f"Truncated URL from {len(url)} to {len(truncated_url)} characters")
    
    if long_urls:
        log_info(f"Processed {len(long_urls)} long URLs in text content")
    
    # Return all URLs found, not just the long ones
    return processed_text, urls_found

def process_report_content(content: str, max_url_length: int = 200, max_total_length: int = 8000) -> str:
    """
    Process report content to handle long URLs and overall length.
    
    Args:
        content: Report content to process
        max_url_length: Maximum length for individual URLs
        max_total_length: Maximum total length for the content
        
    Returns:
        str: Processed content with URLs truncated and length managed
    """
    if not content:
        return content or ""
    
    # First, handle long URLs
    processed_content, all_urls = extract_and_process_urls(content, max_url_length)
    
    # Count how many URLs were actually truncated
    long_urls_count = 0
    for url in all_urls:
        if len(url) > max_url_length:
            long_urls_count += 1
    
    # If we still have very long content, apply overall truncation
    if len(processed_content) > max_total_length:
        log_info(f"Content length {len(processed_content)} exceeds limit, truncating to {max_total_length}")
        processed_content = processed_content[:max_total_length-100] + "\n\n[Content truncated due to length...]"
    
    # Add a note about URL processing if we truncated any URLs
    if long_urls_count > 0:
        url_note = f"\n\n[Note: {long_urls_count} long URL(s) were truncated for processing. Full URLs are preserved in the original report.]"
        # Make sure we don't exceed the limit with the note
        if len(processed_content) + len(url_note) > max_total_length:
            processed_content = processed_content[:max_total_length-len(url_note)] + url_note
        else:
            processed_content += url_note
    
    return processed_content

def create_url_summary(urls: List[str], max_urls: int = 5) -> str:
    """
    Create a summary of URLs for reference.
    
    Args:
        urls: List of URLs to summarize
        max_urls: Maximum number of URLs to include in summary
        
    Returns:
        str: Formatted URL summary
    """
    if not urls:
        return ""
    
    summary_urls = urls[:max_urls]
    summary = "**Referenced URLs:**\n"
    
    for i, url in enumerate(summary_urls, 1):
        try:
            parsed = urlparse(url)
            domain = parsed.netloc
            path_info = parsed.path[:50] + "..." if len(parsed.path) > 50 else parsed.path
            summary += f"{i}. {domain}{path_info}\n"
        except Exception:
            # Fallback to showing first part of URL
            url_preview = url[:80] + "..." if len(url) > 80 else url
            summary += f"{i}. {url_preview}\n"
    
    if len(urls) > max_urls:
        summary += f"... and {len(urls) - max_urls} more URLs\n"
    
    return summary
