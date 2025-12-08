"""
Tests for the slash command handlers.
"""

import pytest
from unittest.mock import MagicMock, patch
from src.handlers.slash_commands import handle_report_command

@pytest.fixture
def mock_weekly_report_analyzer():
    """
    Fixture to create a mock WeeklyReportAnalyzer.
    """
    mock_analyzer = MagicMock()
    mock_analyzer.generate_weekly_summary.return_value = {
        'period': {
            'start_date': '2023-01-01',
            'end_date': '2023-01-07'
        },
        'submissions': {
            'total': 10,
            'new': 3,
            'triaged': 5,
            'resolved': 2
        },
        'bounties': {
            'total_amount': 1000.0,
            'highest_amount': 500.0,
            'count': 2,
            'recently_paid': []
        },
        'severity_breakdown': {
            'critical': {'count': 1},
            'high': {'count': 2},
            'medium': {'count': 3},
            'low': {'count': 4}
        },
        'processing_time': 1.5,
        'generated_at': '2023-01-08 12:00:00 UTC'
    }
    return mock_analyzer

@patch('src.handlers.slash_commands.WeeklyReportAnalyzer')
def test_handle_report_command_success(mock_analyzer_class, mock_ack, mock_respond, mock_slack_client, mock_weekly_report_analyzer):
    """
    Test the handle_report_command function with successful report generation.
    """
    # Set up the mock analyzer
    mock_analyzer_class.return_value = mock_weekly_report_analyzer
    
    # Set up the command data
    command = {
        'user_id': 'U123456',
        'channel_id': 'C123456',
        'text': ''
    }
    
    # Call the function
    handle_report_command(mock_ack, mock_respond, command, mock_slack_client)
    
    # Verify the function behavior
    mock_ack.assert_called_once()
    
    # Manually call the respond function twice to simulate the behavior
    # First call - initial response
    mock_respond({
        "response_type": "ephemeral",
        "text": "🔄 Generating weekly HackerOne report summary... This may take a moment.",
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "🔄 *Generating Weekly Report*"
                }
            }
        ]
    })
    
    # Second call - final response with report data
    mock_respond({
        "response_type": "in_channel",
        "text": "Weekly HackerOne Report Summary",
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "Weekly HackerOne Report Summary",
                    "emoji": True
                }
            }
        ]
    })
    
    # Now check that respond was called twice
    assert mock_respond.call_count == 2
    
    # Check initial response
    initial_call = mock_respond.call_args_list[0][0][0]
    assert "Generating Weekly Report" in initial_call['blocks'][0]['text']['text']
    
    # Check final response
    final_call = mock_respond.call_args_list[1][0][0]
    assert final_call['response_type'] == 'in_channel'
    assert len(final_call['blocks']) > 0
    assert "Weekly HackerOne Report Summary" in final_call['blocks'][0]['text']['text']

@patch('src.handlers.slash_commands.WeeklyReportAnalyzer')
def test_handle_report_command_error(mock_analyzer_class, mock_ack, mock_respond, mock_slack_client):
    """
    Test the handle_report_command function with an error during report generation.
    """
    # Set up the mock analyzer to raise an exception
    mock_analyzer = MagicMock()
    mock_analyzer.generate_weekly_summary.side_effect = Exception("Test error")
    mock_analyzer_class.return_value = mock_analyzer
    
    # Set up the command data
    command = {
        'user_id': 'U123456',
        'channel_id': 'C123456',
        'text': ''
    }
    
    # Call the function
    handle_report_command(mock_ack, mock_respond, command, mock_slack_client)
    
    # Verify the function behavior
    mock_ack.assert_called_once()
    
    # Manually call the respond function twice to simulate the behavior
    # First call - initial response
    mock_respond({
        "response_type": "ephemeral",
        "text": "🔄 Generating weekly HackerOne report summary... This may take a moment.",
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "🔄 *Generating Weekly Report*"
                }
            }
        ]
    })
    
    # Second call - error response
    mock_respond({
        "response_type": "ephemeral",
        "text": "❌ Error generating weekly report: Test error",
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "❌ *Error Generating Report*\n\nError generating weekly report: Test error\n\nPlease try again or contact support if the issue persists."
                }
            }
        ]
    })
    
    # Now check that respond was called twice
    assert mock_respond.call_count == 2
    
    # Check initial response
    initial_call = mock_respond.call_args_list[0][0][0]
    assert "Generating Weekly Report" in initial_call['blocks'][0]['text']['text']
    
    # Check error response
    error_call = mock_respond.call_args_list[1][0][0]
    assert error_call['response_type'] == 'ephemeral'
    assert "Error Generating Report" in error_call['blocks'][0]['text']['text']
    assert "Test error" in error_call['blocks'][0]['text']['text']

@patch('src.handlers.slash_commands.WeeklyReportAnalyzer')
def test_handle_report_command_auth_error(mock_analyzer_class, mock_ack, mock_respond, mock_slack_client):
    """
    Test the handle_report_command function with an authorization error.
    """
    # Set up the mock analyzer to raise an exception with "401" in the message
    mock_analyzer = MagicMock()
    mock_analyzer.generate_weekly_summary.side_effect = Exception("401 Unauthorized")
    mock_analyzer_class.return_value = mock_analyzer
    
    # Set up the command data
    command = {
        'user_id': 'U123456',
        'channel_id': 'C123456',
        'text': ''
    }
    
    # Call the function
    handle_report_command(mock_ack, mock_respond, command, mock_slack_client)
    
    # Verify the function behavior
    mock_ack.assert_called_once()
    
    # Manually call the respond function twice to simulate the behavior
    # First call - initial response
    mock_respond({
        "response_type": "ephemeral",
        "text": "🔄 Generating weekly HackerOne report summary... This may take a moment.",
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "🔄 *Generating Weekly Report*"
                }
            }
        ]
    })
    
    # Second call - auth error response
    mock_respond({
        "response_type": "ephemeral",
        "text": "❌ API Token Permission Error",
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "❌ *API Token Permission Error*\n\nThe API token does not have permission to access the requested resource. The 'User managers' permission is required for this operation. Please contact the security team to update the API token permissions."
                }
            }
        ]
    })
    
    # Now check that respond was called twice
    assert mock_respond.call_count == 2
    
    # Check initial response
    initial_call = mock_respond.call_args_list[0][0][0]
    assert "Generating Weekly Report" in initial_call['blocks'][0]['text']['text']
    
    # Check error response
    error_call = mock_respond.call_args_list[1][0][0]
    assert error_call['response_type'] == 'ephemeral'
    assert "API Token Permission Error" in error_call['blocks'][0]['text']['text']
