"""
Shared pytest fixtures for testing.
"""

import os
import pytest
from unittest.mock import MagicMock

@pytest.fixture
def mock_env_vars(monkeypatch):
    """
    Fixture to set up mock environment variables for testing.
    """
    # Set up environment variables
    monkeypatch.setenv('TOKEN_NAME', 'test_token')
    monkeypatch.setenv('TOKEN_VALUE', 'test_value')
    monkeypatch.setenv('SLACK_BOT_TOKEN', 'xoxb-test')
    monkeypatch.setenv('SLACK_APP_TOKEN', 'xapp-test')
    monkeypatch.setenv('ERASER_API_KEY', 'test_eraser_key')
    monkeypatch.setenv('AUTHORIZED_USERS', 'U123456,U654321')
    monkeypatch.setenv('ALLOWED_CHANNELS', '#test-channel,#security')
    monkeypatch.setenv('MAX_FOLLOWUP_OPTIONS', '3')
    
    # Force reload of config module to apply new environment variables
    import importlib
    import src.config
    importlib.reload(src.config)
    
    yield monkeypatch
    
    # Clean up is handled automatically by monkeypatch

@pytest.fixture
def mock_slack_client():
    """
    Fixture to create a mock Slack WebClient.
    """
    mock_client = MagicMock()
    
    # Mock common methods
    mock_client.chat_postMessage.return_value = {"ok": True, "ts": "1234567890.123456"}
    mock_client.files_upload_v2.return_value = {"ok": True, "file": {"id": "F12345"}}
    mock_client.users_info.return_value = {
        "ok": True,
        "user": {
            "id": "U123456",
            "name": "testuser",
            "real_name": "Test User",
            "profile": {
                "email": "test@example.com",
                "image_72": "https://example.com/avatar.jpg"
            }
        }
    }
    
    return mock_client

@pytest.fixture
def mock_hackerone_api():
    """
    Fixture to create a mock HackerOne API client.
    """
    mock_api = MagicMock()
    
    # Mock common methods
    mock_api.get_report.return_value = {
        "id": "123456",
        "title": "Test Report",
        "state": "triaged",
        "severity": "medium",
        "reporter": {
            "username": "tester",
            "reputation": 500,
            "signal": 4.5,
            "impact": 3.8
        }
    }
    
    mock_api.get_reporter_stats.return_value = {
        "username": "tester",
        "reputation": 500,
        "signal": 4.5,
        "impact": 3.8,
        "report_count": 42,
        "rank": 1000
    }
    
    return mock_api

@pytest.fixture
def mock_ack():
    """
    Fixture to create a mock Slack acknowledgment function.
    """
    return MagicMock()

@pytest.fixture
def mock_respond():
    """
    Fixture to create a mock Slack respond function.
    """
    return MagicMock()

@pytest.fixture
def mock_say():
    """
    Fixture to create a mock Slack say function.
    """
    return MagicMock()
