"""
Formatting utility module.
Handles message formatting and text manipulation.
"""

from typing import Dict, Any, List, Optional, Union
from datetime import datetime

def truncate_text(text: str, max_length: int = 3000) -> str:
    """
    Truncate text to max_length and add ellipsis if needed.
    
    Args:
        text: Text to truncate
        max_length: Maximum length before truncating
        
    Returns:
        str: Truncated text
    """
    if not text or len(text) <= max_length:
        return text
    return text[:max_length-3] + "..."

def split_text_into_blocks(
    text: str,
    prefix: str = "",
    max_length: int = 2900
) -> List[Dict[str, Any]]:
    """
    Split text into multiple Slack blocks if it's too long.
    
    Args:
        text: Text to split
        prefix: Optional prefix for the first block
        max_length: Maximum length per block
        
    Returns:
        List[Dict]: List of Slack blocks
    """
    if not text:
        return []
    
    # Truncate the text if it's too long
    text = truncate_text(text, max_length=max_length*3)  # Allow for 3 blocks max
    
    # If the text is short enough, return it as a single block
    if len(text) <= max_length:
        return [{
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"{prefix}\n{text}" if prefix else text
            }
        }]
    
    # Split the text into multiple blocks
    blocks = []
    remaining_text = text
    part_num = 1
    
    while remaining_text and len(blocks) < 3:  # Limit to 3 blocks
        # Calculate how much text to include in this block
        if len(remaining_text) <= max_length:
            # Last block
            current_text = remaining_text
            remaining_text = ""
        else:
            # Find a good breaking point (newline or space)
            break_point = remaining_text.rfind('\n', 0, max_length)
            if break_point == -1:
                break_point = remaining_text.rfind(' ', 0, max_length)
            if break_point == -1:
                break_point = max_length
            
            current_text = remaining_text[:break_point]
            remaining_text = remaining_text[break_point:].lstrip()
        
        # Create the block
        if part_num == 1:
            block_text = f"{prefix}\n{current_text}" if prefix else current_text
        else:
            block_text = f"(continued {part_num})...\n{current_text}"
        
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": block_text
            }
        })
        
        part_num += 1
    
    # If there's still remaining text, add an ellipsis to the last block
    if remaining_text:
        last_block = blocks[-1]
        last_text = last_block["text"]["text"]
        last_block["text"]["text"] = f"{last_text}\n...(text truncated due to length)..."
    
    return blocks

def format_date(date_str: str, input_format: Optional[str] = None) -> str:
    """
    Format a date string into a consistent format.
    
    Args:
        date_str: Date string to format
        input_format: Optional input format string
        
    Returns:
        str: Formatted date string
    """
    try:
        if input_format:
            dt = datetime.strptime(date_str, input_format)
        else:
            # Try common formats
            for fmt in [
                '%Y-%m-%dT%H:%M:%S.%fZ',  # ISO format with microseconds
                '%Y-%m-%dT%H:%M:%SZ',     # ISO format
                '%Y-%m-%d %H:%M:%S',      # Standard format
                '%b %d, %Y',              # Month name format
                '%Y-%m-%d'                # Date only
            ]:
                try:
                    dt = datetime.strptime(date_str, fmt)
                    break
                except ValueError:
                    continue
            else:
                return date_str  # Return original if no format matches
        
        return dt.strftime('%b %d, %Y')
    except Exception:
        return date_str

def format_number(value: Union[int, float, str], decimal_places: int = 2) -> str:
    """
    Format a number with consistent decimal places.
    
    Args:
        value: Number to format
        decimal_places: Number of decimal places
        
    Returns:
        str: Formatted number string
    """
    try:
        if isinstance(value, str):
            if value == 'N/A':
                return value
            value = float(value)
        
        if isinstance(value, (int, float)):
            return f"{value:.{decimal_places}f}"
        
        return str(value)
    except ValueError:
        return str(value)

def create_bullet_points(items: List[str], bullet: str = "•") -> str:
    """
    Create a bulleted list with consistent formatting.
    
    Args:
        items: List of items to bullet
        bullet: Bullet character to use
        
    Returns:
        str: Formatted bullet point list
    """
    return "\n".join(f"{bullet} {item.strip()}" for item in items if item.strip())

def format_code_block(code: str, language: Optional[str] = None) -> str:
    """
    Format code in a Slack-compatible code block.
    
    Args:
        code: Code to format
        language: Optional language for syntax highlighting
        
    Returns:
        str: Formatted code block
    """
    if language:
        return f"```{language}\n{code}\n```"
    return f"```{code}```"

def format_link(url: str, text: Optional[str] = None) -> str:
    """
    Format a URL as a Slack-compatible link.
    
    Args:
        url: URL to format
        text: Optional display text
        
    Returns:
        str: Formatted link
    """
    if text:
        return f"<{url}|{text}>"
    return f"<{url}>"

def format_user_mention(user_id: str) -> str:
    """
    Format a user ID as a Slack mention.
    
    Args:
        user_id: User ID to mention
        
    Returns:
        str: Formatted mention
    """
    return f"<@{user_id}>"

def format_channel_mention(channel_id: str) -> str:
    """
    Format a channel ID as a Slack channel mention.
    
    Args:
        channel_id: Channel ID to mention
        
    Returns:
        str: Formatted channel mention
    """
    return f"<#{channel_id}>"

def convert_markdown_to_slack(text: str) -> str:
    """
    Convert Markdown formatting to Slack formatting.
    Currently handles:
    - Bold: **text** -> *text*
    
    Args:
        text: The text to convert
        
    Returns:
        The converted text with Slack formatting
    """
    import re
    if not text:
        return text
        
    # Convert bold: **text** -> *text*
    return re.sub(r'\*\*(.*?)\*\*', r'*\1*', text)
