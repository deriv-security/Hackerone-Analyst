"""
Slash command handlers for Hai bot.
Handles all slash commands including /report for weekly summaries.
"""

import logging
import csv
import os
import tempfile
import json
from datetime import datetime, timedelta
from typing import Dict, Any, List
from slack_bolt import Ack, Respond
from slack_sdk import WebClient

from ..utils.authorization import require_authorization
from ..utils.structured_logging import log_interaction
from ..utils.secret_protection import sanitize_for_users
from ..utils.report_analytics import WeeklyReportAnalyzer
from ..utils.logging import log_info, log_error
from ..api.hackerone import HackerOneAPI
from ..config import get_hackerone_web_base_url, get_organization_program_mappings, get_organization_domains


@require_authorization
def handle_report_command(ack: Ack, respond: Respond, command: Dict[str, Any], client: WebClient):
    """
    Handle the /report slash command to generate weekly HackerOne report summaries.
    
    Args:
        ack: Slack acknowledgment function
        respond: Slack response function  
        command: Slack command object
        client: Slack WebClient instance
    """
    # Acknowledge the command immediately
    ack()
    
    user_id = command.get('user_id')
    channel_id = command.get('channel_id')
    command_text = command.get('text', '').strip()
    
    log_info(f"SLASH COMMAND: /report executed by user {user_id} in channel {channel_id}")
    
    try:
        # Send initial response indicating processing has started
        respond({
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
        
        # Initialize the report analyzer
        analyzer = WeeklyReportAnalyzer()
        
        # Generate the weekly report
        report_data = analyzer.generate_weekly_summary()
        
        # Format the report for Slack
        blocks = _format_report_for_slack(report_data)
        
        # Send the final report with blocks
        respond({
            "response_type": "in_channel",  # Make it visible to everyone in channel
            "text": "Weekly HackerOne Report Summary",
            "blocks": blocks
        })
        
        # Log the interaction
        log_interaction(
            user_id=user_id,
            channel_id=channel_id,
            thread_id=None,
            user_message=f"Slash command: /report {command_text}",
            response_text="Weekly report generated successfully",
            duration=0.0  # Will be calculated by the logging system
        )
        
        log_info(f"Weekly report generated successfully for user {user_id}")
        
    except Exception as e:
        error_msg = f"Error generating weekly report: {str(e)}"
        log_error(e, "Failed to generate weekly report")
        
        # Send error response - use the original error message, not sanitized for users
        safe_error_msg = error_msg  # Don't sanitize for user responses
        
        # Check if this is an authorization error
        if "401" in error_msg or "Unauthorized" in error_msg:
            respond({
                "response_type": "ephemeral",
                "text": f"❌ API Token Permission Error",
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"❌ *API Token Permission Error*\n\nThe API token does not have permission to access the requested resource. The 'User managers' permission is required for this operation. Please contact the security team to update the API token permissions."
                        }
                    }
                ]
            })
        else:
            respond({
                "response_type": "ephemeral",
                "text": f"❌ {safe_error_msg}",
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"❌ *Error Generating Report*\n\n{safe_error_msg}\n\nPlease try again or contact support if the issue persists."
                        }
                    }
                ]
            })
        
        # Log the error interaction
        log_interaction(
            user_id=user_id,
            channel_id=channel_id,
            thread_id=None,
            user_message=f"Slash command: /report {command_text}",
            response_text=f"Error: {safe_error_msg}",
            duration=0.0
        )


def _escape_title_for_slack(title: str) -> str:
    """
    Escape title text to prevent auto-hyperlinking in Slack.
    
    Args:
        title: The original title text
        
    Returns:
        Escaped title text
    """
    escaped_title = title
    
    # Replace dots with middle dots to prevent auto-linking
    escaped_title = escaped_title.replace('.', '․')
    
    # Replace organization domains with escaped versions
    org_domains = get_organization_domains()
    for domain in org_domains:
        escaped_title = escaped_title.replace(domain, domain.replace('.', '․'))
    
    # Escape URLs and other patterns
    escaped_title = escaped_title.replace('https://', 'https\u200B://')
    escaped_title = escaped_title.replace('http://', 'http\u200B://')
    escaped_title = escaped_title.replace('app.', 'app\u200B.')
    escaped_title = escaped_title.replace(' De', ' De\u200B')
    
    return escaped_title


def _format_report_for_slack(report_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Format the weekly report data as Slack blocks.
    
    Args:
        report_data: Dictionary containing the report analysis
        
    Returns:
        List of Slack blocks for the message
    """
    # Build the blocks for the report
    blocks = []
    
    # Also build plain text version for backward compatibility
    report_lines = []
    
    # Header
    period_text = f"{report_data['period']['start_date']} to {report_data['period']['end_date']}"
    report_lines.append(f"*Report Period:* {period_text} (Friday to Friday)")
    report_lines.append("")
    
    # Extract data
    submissions = report_data['submissions']
    bounties = report_data['bounties']
    
    # Statistics
    report_lines.append("*Submission Statistics*")
    report_lines.append(f"• Total Reports: *{submissions['total']}* (actionable)")
    report_lines.append(f"• New: {submissions['new']}")
    report_lines.append(f"• Triaged: {submissions['triaged']}")
    report_lines.append(f"• Resolved: {submissions['resolved']}")
    report_lines.append("")
    
    report_lines.append("*Bounty Statistics*")
    if bounties['total_amount'] > 0:
        report_lines.append(f"• Total Awarded: `${bounties['total_amount']:,.2f}`")
        report_lines.append(f"• Highest Bounty: `${bounties['highest_amount']:,.2f}`")
        report_lines.append(f"• Reports with Bounties: {bounties['count']}")
    else:
        report_lines.append("• No bounties awarded this week")
    report_lines.append("")
    
    
    # Severity breakdown
    severity = report_data['severity_breakdown']
    severity_emojis = {
        'critical': '🔴',
        'high': '🟠',
        'medium': '🟡',
        'low': '🟢',
        'none': 'ℹ️',
        'pending': '⚪'
    }
    
    severity_items = []
    for level in ['critical', 'high', 'medium', 'low', 'none', 'pending']:
        if level in severity and severity[level]['count'] > 0:
            level_name = level.title() if level != 'none' else 'None'
            emoji = severity_emojis.get(level, '⚪')
            count = severity[level]['count']
            severity_items.append(f"{emoji} *{level_name}:* {count}")
    
    if severity_items:
        report_lines.append("*Severity Breakdown (Reported)*")
        report_lines.extend(severity_items)
        report_lines.append("")
    
    # Valid reports
    if 'detailed_reports' in report_data and report_data['detailed_reports']:
        valid_reports = [
            report for report in report_data['detailed_reports']
            if (report['state'] not in ['duplicate', 'not-applicable', 'spam', 'new', 'informative'] and
                report.get('created_this_week', False))
        ]
        
        if valid_reports:
            report_lines.append(f"*Valid Reports Submitted ({len(valid_reports)} reports):*")
            
            for report in valid_reports:
                severity_emoji = {
                    'critical': '🔴',
                    'high': '🟠',
                    'medium': '🟡',
                    'low': '🟢',
                    'none': 'ℹ️'
                }.get(report['severity'].lower(), '⚪')
                
                report_link = f"<{get_hackerone_web_base_url()}/reports/{report['id']}|#{report['id']}>"
                program_name = report.get('program', 'unknown')
                program_mappings = get_organization_program_mappings()
                program_display = program_mappings.get(program_name, program_name)
                
                bounty_text = ""
                if report.get('bounty_amount', 0) > 0:
                    bounty_text = f" `${report['bounty_amount']:,.0f}`"
                
                # Escape title to prevent auto-hyperlinking
                escaped_title = _escape_title_for_slack(report['title'])
                
                report_lines.append(
                    f"{severity_emoji} {report_link} {escaped_title} ({report['state'].title()}, {program_display}){bounty_text}"
                )
            
            report_lines.append("")
    
    # Older bounties
    if 'bounties' in report_data and 'recently_paid' in report_data['bounties'] and report_data['bounties']['recently_paid']:
        recently_paid = report_data['bounties']['recently_paid']
        
        older_bounties = []
        current_week_report_ids = set()
        if 'detailed_reports' in report_data:
            current_week_report_ids = {
                report['id'] for report in report_data['detailed_reports'] 
                if report.get('created_this_week', False)
            }
        
        for bounty in recently_paid:
            if bounty['id'] not in current_week_report_ids:
                older_bounties.append(bounty)
        
        if older_bounties:
            report_lines.append(f"*Older Reports with Recently Paid Bounties ({len(older_bounties)} bounties):*")
            
            for bounty in older_bounties:
                severity_emoji = {
                    'critical': '🔴',
                    'high': '🟠',
                    'medium': '🟡',
                    'low': '🟢',
                    'none': 'ℹ️'
                }.get(bounty['severity'].lower(), '⚪')
                
                report_link = f"<{get_hackerone_web_base_url()}/reports/{bounty['id']}|#{bounty['id']}>"
                program_name = bounty.get('program', 'unknown')
                program_mappings = get_organization_program_mappings()
                program_display = program_mappings.get(program_name, program_name)
                
                # Escape title
                escaped_title = _escape_title_for_slack(bounty['title'])
                
                report_lines.append(
                    f"{severity_emoji} {report_link} {escaped_title} ({bounty['severity'].title()}, `${bounty['bounty_amount']:,.0f}`, Paid on {bounty['formatted_date']})"
                )
            
            report_lines.append("")
    
    # Create Slack blocks
    blocks = []
    
    # Header block
    blocks.append({
        "type": "header",
        "text": {
            "type": "plain_text",
            "text": "Weekly HackerOne Report Summary",
            "emoji": True
        }
    })
    
    # Add a divider after the header
    blocks.append({
        "type": "divider"
    })
    
    # Period block
    period_text = f"{report_data['period']['start_date']} to {report_data['period']['end_date']} (Friday to Friday)"
    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": f"*Report Period:* {period_text}"
        }
    })
    
    # Stats block with fields
    stats_fields = []
    
    # Submission stats
    submission_stats = f"📊 *Submission Statistics*\n• Total Reports: *{submissions['total']}* (actionable)\n• New: {submissions['new']}\n• Triaged: {submissions['triaged']}\n• Resolved: {submissions['resolved']}"
    stats_fields.append({
        "type": "mrkdwn",
        "text": submission_stats
    })
    
    # Bounty stats
    if bounties['total_amount'] > 0:
        bounty_stats = f"💰 *Bounty Statistics*\n• Total Awarded: `${bounties['total_amount']:,.2f}`\n• Highest Bounty: `${bounties['highest_amount']:,.2f}`\n• Reports with Bounties: {bounties['count']}"
    else:
        bounty_stats = "💰 *Bounty Statistics*\n• No bounties awarded this week"
    stats_fields.append({
        "type": "mrkdwn",
        "text": bounty_stats
    })
    
    blocks.append({
        "type": "section",
        "fields": stats_fields
    })
    
    # Severity breakdown
    if severity_items:
        severity_text = "*Severity Breakdown (Reported)*\n" + "\n".join(severity_items)
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": severity_text
            }
        })
    
    # Trends block removed per user request
    
    # Add valid reports section to blocks
    if 'detailed_reports' in report_data and report_data['detailed_reports']:
        valid_reports = [
            report for report in report_data['detailed_reports']
            if (report['state'] not in ['duplicate', 'not-applicable', 'spam', 'new', 'informative'] and
                report.get('created_this_week', False))
        ]
        
        if valid_reports:
            # Add a divider before the valid reports section
            blocks.append({
                "type": "divider"
            })
            
            # Add a header for the valid reports section
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Valid Reports Submitted ({len(valid_reports)} reports):*"
                }
            })
            
            # Add each valid report as a separate section
            for report in valid_reports:
                severity_emoji = {
                    'critical': '🔴',
                    'high': '🟠',
                    'medium': '🟡',
                    'low': '🟢',
                    'none': 'ℹ️'
                }.get(report['severity'].lower(), '⚪')
                
                report_link = f"<{get_hackerone_web_base_url()}/reports/{report['id']}|#{report['id']}>"
                program_name = report.get('program', 'unknown')
                program_mappings = get_organization_program_mappings()
                program_display = program_mappings.get(program_name, program_name)
                
                bounty_text = ""
                if report.get('bounty_amount', 0) > 0:
                    bounty_text = f" `${report['bounty_amount']:,.0f}`"
                
                # Escape title to prevent auto-hyperlinking
                escaped_title = _escape_title_for_slack(report['title'])
                
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"{severity_emoji} {report_link} {escaped_title} ({report['state'].title()}, {program_display}){bounty_text}"
                    }
                })
    
    # Add recently paid bounties section to blocks
    if 'bounties' in report_data and 'recently_paid' in report_data['bounties'] and report_data['bounties']['recently_paid']:
        recently_paid = report_data['bounties']['recently_paid']
        
        older_bounties = []
        current_week_report_ids = set()
        if 'detailed_reports' in report_data:
            current_week_report_ids = {
                report['id'] for report in report_data['detailed_reports'] 
                if report.get('created_this_week', False)
            }
        
        for bounty in recently_paid:
            if bounty['id'] not in current_week_report_ids:
                older_bounties.append(bounty)
        
        if older_bounties:
            # Add a divider before the older bounties section
            blocks.append({
                "type": "divider"
            })
            
            # Add a header for the older bounties section
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Older Reports with Recently Paid Bounties ({len(older_bounties)} bounties):*"
                }
            })
            
            # Add each older bounty as a separate section
            for bounty in older_bounties:
                severity_emoji = {
                    'critical': '🔴',
                    'high': '🟠',
                    'medium': '🟡',
                    'low': '🟢',
                    'none': 'ℹ️'
                }.get(bounty['severity'].lower(), '⚪')
                
                report_link = f"<{get_hackerone_web_base_url()}/reports/{bounty['id']}|#{bounty['id']}>"
                program_name = bounty.get('program', 'unknown')
                program_mappings = get_organization_program_mappings()
                program_display = program_mappings.get(program_name, program_name)
                
                # Escape title
                escaped_title = _escape_title_for_slack(bounty['title'])
                
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"{severity_emoji} {report_link} {escaped_title} ({bounty['severity'].title()}, `${bounty['bounty_amount']:,.0f}`, Paid on {bounty['formatted_date']})"
                    }
                })
    
    # Processing time in context block
    if 'processing_time' in report_data:
        # Add a divider before the processing time
        blocks.append({
            "type": "divider"
        })
        
        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"Generated in {report_data['processing_time']:.1f}s | {report_data.get('generated_at', datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC'))}"
                }
            ]
        })
    
    # For backward compatibility, also return the plain text version
    plain_text = "\n".join(report_lines)
    
    # Update the handle_report_command function to use blocks
    return blocks
