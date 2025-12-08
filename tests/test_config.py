"""
Tests for the config module.
"""

import os
import pytest
from unittest.mock import patch
from src.config import (
    validate_config, 
    get_slack_tokens, 
    get_hackerone_auth,
    get_allowed_channels,
    get_max_followup_options
)

def test_validate_config_with_valid_env_vars(mock_env_vars):
    """
    Test that validate_config does not raise an exception when all required
    environment variables are present.
    """
    # Should not raise an exception
    validate_config()

@patch('src.config.load_dotenv')
def test_validate_config_with_missing_env_vars(mock_load_dotenv, monkeypatch):
    """
    Test that validate_config raises a ValueError when required environment
    variables are missing.
    """
    # Mock load_dotenv to do nothing
    mock_load_dotenv.return_value = None
    
    # Mock the environment variables to be empty
    monkeypatch.setenv('TOKEN_NAME', '')
    monkeypatch.setenv('TOKEN_VALUE', '')
    monkeypatch.setenv('SLACK_BOT_TOKEN', '')
    monkeypatch.setenv('SLACK_APP_TOKEN', '')
    
    # Force reload of config module to apply new environment variables
    import importlib
    import src.config
    importlib.reload(src.config)
    
    # Should raise ValueError
    with pytest.raises(ValueError):
        src.config.validate_config()

def test_get_slack_tokens(mock_env_vars):
    """
    Test that get_slack_tokens returns the correct values.
    """
    # Test the function
    bot_token, app_token = get_slack_tokens()
    assert bot_token == 'xoxb-test'
    assert app_token == 'xapp-test'

def test_get_hackerone_auth(mock_env_vars):
    """
    Test that get_hackerone_auth returns the correct values.
    """
    # Test the function
    token_name, token_value = get_hackerone_auth()
    assert token_name == 'test_token'
    assert token_value == 'test_value'

def test_get_allowed_channels(mock_env_vars):
    """
    Test that get_allowed_channels returns the correct values.
    """
    # Test the function
    channels = get_allowed_channels()
    assert channels == ['#test-channel', '#security']

def test_get_max_followup_options_default():
    """
    Test that get_max_followup_options returns the default value when not set.
    """
    # Test the function with default value
    max_options = get_max_followup_options()
    assert max_options == 3  # Default value from config.py

def test_get_max_followup_options_custom(monkeypatch):
    """
    Test that get_max_followup_options returns the custom value when set.
    """
    # Set custom value
    monkeypatch.setenv('MAX_FOLLOWUP_OPTIONS', '5')
    
    # Force reload of config module to apply new environment variables
    import importlib
    import src.config
    importlib.reload(src.config)
    
    # Test the function with custom value
    max_options = get_max_followup_options()
    assert max_options == 5
