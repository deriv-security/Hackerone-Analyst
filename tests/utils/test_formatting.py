"""
Tests for the formatting utility module.
"""

import pytest
from src.utils.formatting import (
    truncate_text,
    format_date,
    format_number,
    create_bullet_points,
    format_code_block,
    format_link,
    format_user_mention,
    format_channel_mention,
    convert_markdown_to_slack
)

def test_truncate_text():
    """Test the truncate_text function."""
    # Test with text shorter than max_length
    assert truncate_text("Hello", 10) == "Hello"
    
    # Test with text equal to max_length
    assert truncate_text("Hello", 5) == "Hello"
    
    # Test with text longer than max_length
    assert truncate_text("Hello World", 8) == "Hello..."
    
    # Test with empty text
    assert truncate_text("", 10) == ""
    
    # Test with None
    assert truncate_text(None, 10) is None

def test_format_date():
    """Test the format_date function."""
    # Test with ISO format
    assert format_date("2023-01-15T12:30:45Z") == "Jan 15, 2023"
    
    # Test with date only
    assert format_date("2023-01-15") == "Jan 15, 2023"
    
    # Test with custom input format
    assert format_date("15/01/2023", input_format="%d/%m/%Y") == "Jan 15, 2023"
    
    # Test with invalid date
    assert format_date("invalid-date") == "invalid-date"

def test_format_number():
    """Test the format_number function."""
    # Test with integer
    assert format_number(42) == "42.00"
    
    # Test with float
    assert format_number(3.14159) == "3.14"
    
    # Test with string number
    assert format_number("123.456") == "123.46"
    
    # Test with custom decimal places
    assert format_number(3.14159, decimal_places=3) == "3.142"
    
    # Test with non-numeric string
    assert format_number("N/A") == "N/A"

def test_create_bullet_points():
    """Test the create_bullet_points function."""
    # Test with list of items
    items = ["First item", "Second item", "Third item"]
    expected = "• First item\n• Second item\n• Third item"
    assert create_bullet_points(items) == expected
    
    # Test with custom bullet
    assert create_bullet_points(items, bullet="-") == "- First item\n- Second item\n- Third item"
    
    # Test with empty list
    assert create_bullet_points([]) == ""
    
    # Test with list containing empty strings
    assert create_bullet_points(["First", "", "Third"]) == "• First\n• Third"

def test_format_code_block():
    """Test the format_code_block function."""
    # Test without language
    assert format_code_block("print('Hello')") == "```print('Hello')```"
    
    # Test with language
    assert format_code_block("print('Hello')", language="python") == "```python\nprint('Hello')\n```"

def test_format_link():
    """Test the format_link function."""
    # Test with URL only
    assert format_link("https://example.com") == "<https://example.com>"
    
    # Test with URL and text
    assert format_link("https://example.com", "Example") == "<https://example.com|Example>"

def test_format_user_mention():
    """Test the format_user_mention function."""
    assert format_user_mention("U123456") == "<@U123456>"

def test_format_channel_mention():
    """Test the format_channel_mention function."""
    assert format_channel_mention("C123456") == "<#C123456>"

def test_convert_markdown_to_slack():
    """Test the convert_markdown_to_slack function."""
    # Test bold conversion
    assert convert_markdown_to_slack("This is **bold** text") == "This is *bold* text"
    
    # Test multiple bold conversions
    assert convert_markdown_to_slack("**Bold1** and **Bold2**") == "*Bold1* and *Bold2*"
    
    # Test with no markdown
    assert convert_markdown_to_slack("Plain text") == "Plain text"
    
    # Test with empty string
    assert convert_markdown_to_slack("") == ""
    
    # Test with None
    assert convert_markdown_to_slack(None) is None
