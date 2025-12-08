"""
Mention handlers for Hai.
Handles Slack mention events.
"""

import re
import json
import time
from datetime import datetime
from typing import Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor
from ..api.hackerone import HackerOneAPI
from ..api.slack import SlackAPI
from ..utils.logging import log_error, log_event, log_debug, log_info
from ..utils.structured_logging import log_mention_interaction
from ..utils.formatting import convert_markdown_to_slack
from ..utils.authorization import require_authorization
from ..models import CredibilityScore
from ..config import (
    get_max_followup_options, 
    get_allowed_channels,
    get_bot_restriction_message,
    get_bot_contact_message,
    get_bot_unauthorized_access_message,
    get_organization_security_team_name
)

# Initialize store for follow-up options
follow_up_options_store = {}

# Initialize API clients
hackerone = HackerOneAPI()
slack = SlackAPI()

def _create_mock_handlers(event: Dict[str, Any], use_thread: bool = False):
    """
    Create mock ack and respond functions for slash command handling via mentions.
    
    Args:
        event: The Slack event data
        use_thread: Whether to use thread_ts for responses
        
    Returns:
        tuple: (mock_ack, mock_respond) functions
    """
    def mock_ack():
        pass
    
    def mock_respond(response_data):
        # Convert the response data to a format suitable for slack.send_message
        thread_ts = event['ts'] if use_thread else None
        
        if 'blocks' in response_data:
            slack.send_message(
                text=response_data.get('text', 'Processing command...'),
                blocks=response_data['blocks'],
                channel=event['channel'],
                thread_ts=thread_ts
            )
        else:
            slack.send_message(
                text=response_data.get('text', 'Processing command...'),
                channel=event['channel'],
                thread_ts=thread_ts
            )
    
    return mock_ack, mock_respond

def _is_suspicious_input(text: str) -> bool:
    """
    Check if input contains suspicious patterns that could indicate injection attempts.
    
    Args:
        text: The input text to validate
        
    Returns:
        True if input is suspicious, False otherwise
    """
    # Check for hex-encoded content (like the attack you found)
    hex_pattern = re.compile(r'^[0-9a-fA-F\s]+$')
    if len(text) > 50 and hex_pattern.match(text.replace('<@', '').replace('>', '').replace(' ', '')):
        return True
    
    # Check for excessive length (potential payload)
    if len(text) > 500:
        return True
    
    # Check for suspicious keywords that might indicate prompt injection
    suspicious_keywords = [
        'system prompt', 'ignore', 'override', 'bypass', 'jailbreak',
        'pretend', 'roleplay', 'act as', 'you are now', 'forget',
        'disregard', 'instructions', 'previous', 'above'
    ]
    
    text_lower = text.lower()
    for keyword in suspicious_keywords:
        if keyword in text_lower:
            return True
    
    # Check for encoded content patterns
    if any(pattern in text for pattern in ['%', '\\x', '\\u', 'base64']):
        return True
    
    return False

def _is_valid_report_id(report_id: str) -> bool:
    """
    Validate that a report ID is within reasonable bounds for HackerOne.
    
    Args:
        report_id: The report ID to validate
        
    Returns:
        True if valid, False otherwise
    """
    try:
        id_int = int(report_id)
        # HackerOne report IDs typically start around 100000 and go up to ~99999999
        return 100000 <= id_int <= 99999999
    except ValueError:
        return False

def analyze_report(rep_id: str, channel: str, thread_ts: str, timeout: Optional[int] = None) -> None:
    """
    Analyze a HackerOne report and send the results to Slack.
    
    Args:
        rep_id: The HackerOne report ID
        channel: The Slack channel ID to send the response to
        thread_ts: The thread timestamp to reply to
        timeout: Optional timeout override for the API request
    """
    try:
        log_event(f"Starting parallelized analysis for report {rep_id}")
        
        # Step 1: Fetch report details and user profile in parallel
        with ThreadPoolExecutor(max_workers=2) as executor:
            # Submit both tasks
            report_future = executor.submit(hackerone.get_report, rep_id)
            
            # Wait for report to get username, then fetch profile
            report = report_future.result()
            
            username = None
            profile_future = None
            if 'reporter' in report['data']['relationships']:
                reporter_data = report['data']['relationships']['reporter']['data']
                if 'attributes' in reporter_data and 'username' in reporter_data['attributes']:
                    username = reporter_data['attributes']['username']
                    # Start profile fetch in parallel
                    profile_future = executor.submit(hackerone.get_user_profile, username)
            
            # Get profile result if we started the fetch
            profile = profile_future.result() if profile_future else None
        
        log_event(f"Completed data fetching for report {rep_id}, starting Hai analyses")
        
        # Step 2: Run both Hai analyses in parallel
        credibility_score = None
        
        # Prepare prompts for both analyses
        report_prompt = (
            f"Based on the provided information your task is to evaluate the validity of the security report with ID #{rep_id}."
            
            
            f"1. Verify if the report is in scope by checking:"
            f"   - If it matches the program's policy requirements"
            f"   - If the affected assets are part of the program scope"
            f"   - If the vulnerability type is accepted by the program"
            
            f"2. Evaluate if the report:"
            f"   - Check the current state: If the report is closed as 'duplicate', 'not-applicable', or 'spam', it should be considered \"Invalid\" with 95% certainty"
            f"   - Check for duplicate or similar submissions in the program's history"
            f"   - Is complete and technically correct"
            f"   - Describes a valid security vulnerability"
            f"   - Includes sufficient proof of concept"
            f"   - The report has been updated since initial submission"
            
            f"3. DUPLICATE DETECTION:"
            f"   - If you identify duplicate reports, list their report IDs in the duplicateReportIds field"
            f"   - Only mention duplicates in your reasoning if they actually exist"
            f"   - If no duplicates are found, do NOT mention duplicate checking in your reasoning"

            f"4. CONFIDENCE CONSTRAINTS:"
            f"- Never express full certainty - security analysis requires humility"
            f"- Respond with 'Likely Valid' or 'Likely Invalid' for uncertain cases"
            f"- CRITICAL: If the report state is 'duplicate', 'not-applicable', or 'spam', mark as \"Invalid\" (not \"Likely Invalid\") with exactly 95% certainty"
            f"- Provide in your reasoning as a percentage value of how certain you are about both the validity of the report taking all information into account. "

            f"Also, generate {get_max_followup_options()} follow-up actions or questions that would help the HackerOne security team better analyze, validate, or respond to this report. These should be actionable items from a security team perspective, such as requesting additional information from the reporter, suggesting validation steps, or recommending next actions for the security team."
            
            f"Your response should be in, without any exception, valid JSON format with the "
            f"following structure:\n"
            f"{{\n"
            f"  \"predictedValidity\": [\"Valid\", \"Invalid\", \"Likely Valid\", or \"Likely Invalid\"],\n"
            f"  \"validityCertaintyScore\": [0-100],\n"
            f"  \"validityReasoning\": [Reasoning that only mentions duplicates if found],\n"
            f"  \"duplicateReportIds\": [Array of report ID strings if duplicates found, empty array otherwise],\n"
            f"  \"followUpOptions\": [Array of {get_max_followup_options()} complete strings with follow-up actions/questions]\n"
            f"}}\n\n"
            f"IMPORTANT: Ensure all strings in followUpOptions are complete and properly terminated. "
            f"Do not truncate or leave any strings unfinished."
        )
        
        hacker_prompt = None
        if username and profile:
            hacker_prompt = (
                f"Please analyze the HackerOne profile for user '{username}'.\n\n"
                f"Profile information:\n"
                f"- Username: {username}\n"
                f"- Reputation: {profile.get('reputation', 'N/A')}\n"
                f"- Impact: {profile.get('impact', 'N/A')}\n"
                f"- Signal: {profile.get('signal', 'N/A')}\n"
                f"- Joined: {profile.get('joined', 'N/A')}\n\n"
                f"Based on this information, provide a brief assessment of the hacker's skills, "
                f"experience, and reliability. Consider:\n"
                f"1. What does their reputation, impact, and signal suggest about their skill level?\n"
                f"2. How long have they been active on the platform?\n"
                f"3. What might be their areas of expertise based on these metrics?\n"
                f"4. How reliable might their reports be?\n\n"
                f"Provide a concise, professional analysis in 3-4 sentences.\n\n"
                f"Also, based on all the hacker's metrics and information, provide an overall confidence score "
                f"from 0.0-10.0 (with one decimal place precision), where 0.0 represents very low confidence and 10.0 "
                f"represents very high confidence in the reliability and quality of this hacker's reports. "
                f"Include this score at the end of your analysis in the format: 'Confidence Score: [X.X]/10.0'."
            )
        
        # Run Hai analyses in parallel
        with ThreadPoolExecutor(max_workers=2) as executor:
            log_event(f"Starting parallel Hai analyses for report {rep_id}")
            
            # Submit report analysis
            report_future = executor.submit(hackerone.analyze_report, rep_id, report_prompt, None, timeout)
            
            # Submit hacker analysis if we have a username
            hacker_future = None
            if hacker_prompt:
                log_event(f"Running parallel hacker confidence analysis for {username}")
                hacker_future = executor.submit(hackerone.analyze_report, rep_id, hacker_prompt, None, timeout)
            
            # Wait for both to complete
            raw_analysis = report_future.result()
            hacker_analysis = hacker_future.result() if hacker_future else None
            
            log_event(f"Completed parallel Hai analyses for report {rep_id}")
        
        try:
            # Try to clean up the response by finding the first { and last }
            json_start = raw_analysis.find('{')
            json_end = raw_analysis.rfind('}')
            if json_start != -1 and json_end != -1 and json_end > json_start:
                # Extract the JSON part
                json_str = raw_analysis[json_start:json_end+1]
                
                # Try to fix common issues with incomplete strings
                # Look for any unfinished array items in followUpOptions
                if '"followUpOptions": [' in json_str:
                    # Find the last complete string in followUpOptions
                    last_quote = json_str.rfind('"', 0, json_end)
                    if last_quote != -1:
                        # Find the start of this string
                        prev_quote = json_str.rfind('"', 0, last_quote)
                        if prev_quote != -1:
                            # If this string doesn't end with a comma or ], add one
                            next_char = json_str[last_quote+1:last_quote+2]
                            if next_char not in [',', ']']:
                                # Complete the array
                                json_str = json_str[:last_quote+1] + ']}'
                
                # Parse the JSON response
                analysis_json = json.loads(json_str)
            else:
                raise json.JSONDecodeError("No valid JSON object found", raw_analysis, 0)
            
            # Extract fields from JSON
            validity = analysis_json['predictedValidity']
            certainty = float(str(analysis_json['validityCertaintyScore']).rstrip('%'))
            analysis = convert_markdown_to_slack(analysis_json['validityReasoning'])
            
            # Extract duplicate report IDs if present
            duplicate_report_ids = analysis_json.get('duplicateReportIds', [])
            
            # Process hacker analysis if we got one from parallel execution
            hacker_reasoning = None
            if hacker_analysis and username:
                log_event(f"Processing parallel hacker confidence analysis for {username}")
                
                # Extract confidence score using regex pattern
                score_match = re.search(r'Confidence Score: (\d+\.\d+)/10\.0', hacker_analysis)
                if score_match:
                    try:
                        score_value = float(score_match.group(1))
                        # Create a CredibilityScore object
                        credibility_score = CredibilityScore(
                            reputation_score=0,  # These values don't matter as we're using the direct score
                            impact_score=0,
                            signal_score=0,
                            account_age_modifier=0,
                            total_score=score_value
                        )
                        log_event(f"Successfully calculated hacker confidence score: {credibility_score.formatted_score} for {username}")
                        
                        # Extract the analysis part (without the confidence score)
                        hacker_reasoning = convert_markdown_to_slack(
                            re.sub(r'Confidence Score: \d+\.\d+/10\.0', '', hacker_analysis).strip()
                        )
                    except ValueError:
                        log_error(ValueError(f"Failed to parse '{score_match.group(1)}' as float"), "Score parsing")
            
            # Store follow-up options for later use
            if 'followUpOptions' in analysis_json and isinstance(analysis_json['followUpOptions'], list):
                # Take only the first MAX_FOLLOWUP_OPTIONS items
                follow_up_options_store[str(rep_id)] = analysis_json['followUpOptions'][:get_max_followup_options()]
        except json.JSONDecodeError as e:
            log_error(e, "Error parsing Hai response")
            # Let Hai handle the error
            raise ValueError("Failed to parse Hai response")
        
        # Add emoji based on validity - handle both definitive and likely responses
        if validity.lower() in ["valid", "likely valid"]:
            validity_emoji = "✅"
        elif validity.lower() in ["invalid", "likely invalid"]:
            validity_emoji = "❌"
        else:
            validity_emoji = "❓"  # fallback for unexpected responses
        
        validity_text = f"{validity_emoji} {validity}"
        
        # Create response blocks with clickable report link
        from ..config import get_hackerone_web_base_url
        blocks = [
            slack.create_section_block(f"*Hai Report Analysis: <{get_hackerone_web_base_url()}/reports/{rep_id}|#{rep_id}>*")
        ]
        
        # Extract severity from report data
        severity_rating = "None"
        if 'severity' in report['data']['relationships']:
            severity_data = report['data']['relationships']['severity']['data']
            if severity_data and 'attributes' in severity_data and 'rating' in severity_data['attributes']:
                severity_rating = severity_data['attributes']['rating']
        
        # Add emoji based on severity (using smaller colored circles)
        severity_emojis = {
            'critical': '🔴',
            'high': '🟠',
            'medium': '🟡',
            'low': '🟢',
            'none': 'ℹ️',
            'pending': '⚪'
        }
        severity_emoji = severity_emojis.get(severity_rating.lower(), 'ℹ️')
        # Capitalize the first letter of the severity
        severity_display = f"{severity_emoji} {severity_rating.capitalize()}"

        # Add Hai Analysis and hacker username section with score visualization
        if username and credibility_score:
            blocks.append(slack.create_section_block(
                text=(
                    f"*Hai Analysis:*                     {validity_text} ({certainty}%)\n"
                    f"*Reported Severity:*            {severity_display}\n"
                    f"*Hacker Username:*             <{profile['url']}|{username}>\n"
                    f"*Hacker Confidence:*           {credibility_score.visual_score}"
                )
            ))

            # We no longer want to display the Hacker Assessment text in the initial analysis
            # Just show the confidence score visualization
        else:
            blocks.append(slack.create_section_block(
                text=(
                    f"*Hai Analysis:*                     {validity_text} ({certainty}%)\n"
                    f"*Reported Severity:*            {severity_display}"
                )
            ))
        
        # Add reasoning section
        blocks.append(slack.create_section_block(
            text=f"*Reasoning:*\n{analysis}"
        ))
        
        # Add duplicate reports section if any were found
        if duplicate_report_ids and len(duplicate_report_ids) > 0:
            from ..config import get_hackerone_web_base_url
            base_url = get_hackerone_web_base_url()
            
            # Create clickable links for each duplicate report
            duplicate_links = []
            for dup_id in duplicate_report_ids:
                # Clean the ID (remove # if present)
                clean_id = str(dup_id).replace('#', '').strip()
                if clean_id:
                    duplicate_links.append(f"<{base_url}/reports/{clean_id}|#{clean_id}>")
            
            if duplicate_links:
                blocks.append(slack.create_section_block(
                    text=f"*🔄 Duplicate Reports Found:*\n" + " • ".join(duplicate_links)
                ))
        
        # Add divider before buttons
        blocks.append(slack.create_divider_block())
        
        # Add standard action buttons
        blocks.append(slack.create_action_button_block(rep_id))
        
        # Send the response
        slack.send_message(
            text=f"Analysis for report #{rep_id}",
            blocks=blocks,
            channel=channel,
            thread_ts=thread_ts
        )
        
    except Exception as e:
        log_error(e, "Error analyzing report")
        error_message = str(e)
        if "Report could not be fetched" in error_message:
            error_message = (
                f"Unable to analyze report {rep_id}. The report either doesn't exist "
                f"or you don't have permission to access it."
            )
        elif "Hai analysis timed out" in error_message:
            blocks = [
                slack.create_section_block(text=f"⚠️ Analysis timed out for report <{get_hackerone_web_base_url()}/reports/{rep_id}|#{rep_id}>"),
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "Retry Analysis",
                                "emoji": True
                            },
                            "style": "primary",
                            "value": f"retry_{rep_id}",
                            "action_id": "retry_analysis"
                        }
                    ]
                }
            ]
            slack.send_message(
                text=f"Analysis timed out for report #{rep_id}",
                blocks=blocks,
                channel=channel,
                thread_ts=thread_ts
            )
            return
        
        slack.send_message(
            text=f"Error analyzing report: {error_message}",
            channel=channel,
            thread_ts=thread_ts
        )

def analyze_report_with_logging(rep_id: str, channel: str, thread_ts: str, event: Dict[str, Any], request_start: datetime, timeout: Optional[int] = None) -> None:
    """
    Wrapper around analyze_report that adds structured logging.
    
    Args:
        rep_id: The HackerOne report ID
        channel: The Slack channel ID to send the response to
        thread_ts: The thread timestamp to reply to
        event: Original Slack event data
        request_start: When the request started
        timeout: Optional timeout override for the API request
    """
    response_text = ""
    
    try:
        # Call the original analyze_report function
        analyze_report(rep_id, channel, thread_ts, timeout)
        
        # For successful analysis, we'll capture a generic success message
        # The actual Hai response is complex and would be captured in the Hai API layer
        response_text = f"Successfully analyzed report {rep_id} and sent results to Slack"
        
    except Exception as e:
        response_text = f"Error analyzing report {rep_id}: {str(e)}"
        raise  # Re-raise the exception so it's handled by the caller
        
    finally:
        # Log the complete interaction
        duration = (datetime.utcnow() - request_start).total_seconds()
        
        log_mention_interaction(
            event=event,
            report_id=rep_id,
            response_text=response_text,
            duration=duration,
            request_timestamp=request_start
        )

@require_authorization
def handle_mention(event: Dict[str, Any], say: Any) -> None:
    """
    Handle app mention events.
    
    Args:
        event: The Slack event data
        say: Function to send a message to Slack
    """
    request_start = datetime.utcnow()
    
    try:
        # Check if channel is allowed
        channel_id = event['channel']
        channel_name = slack.get_channel_name(channel_id)
        allowed_channels = get_allowed_channels()
        
        # Block if no allowed channels configured OR channel not in allowed list
        channel_formatted = f"#{channel_name}" if channel_name else "#None"
        
        if not allowed_channels or channel_formatted not in allowed_channels:
            log_event(f"Blocked mention in unauthorized channel: #{channel_name} (ID: {channel_id})")
            
            # Log unauthorized access attempt
            log_mention_interaction(
                event=event,
                report_id="UNAUTHORIZED",
                response_text=f"Unauthorized access blocked - restricted to {get_organization_security_team_name()}",
                duration=(datetime.utcnow() - request_start).total_seconds(),
                request_timestamp=request_start
            )
            
            # Send strong warning message to unauthorized channel
            warning_blocks = [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "🚨 *UNAUTHORIZED ACCESS DETECTED* 🚨"
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            f"⛔ *{get_bot_restriction_message()}*\n\n"
                            "⚠️ *This access attempt has been logged and reported to the Security Team.*\n\n"
                            f"❓ {get_bot_contact_message()}"
                        )
                    }
                },
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": f"🔍 Channel: #{channel_name} | 📅 {event.get('ts', 'Unknown timestamp')} | 👤 <@{event.get('user', 'Unknown user')}>"
                        }
                    ]
                }
            ]
            
            slack.send_message(
                text=f"🚨 {get_bot_unauthorized_access_message()}",
                blocks=warning_blocks,
                channel=event['channel'],
                thread_ts=event['ts']
            )
            return
        
        # Extract text after the mention
        text = event['text']
        log_event(f"Received mention with text: {text} in channel #{channel_name}")
        
        # Security: Check for suspicious input patterns
        if _is_suspicious_input(text):
            log_event(f"Blocked suspicious input: {text}")
            
            # Log suspicious input attempt
            log_mention_interaction(
                event=event,
                report_id="SUSPICIOUS_INPUT",
                response_text="Suspicious input detected and blocked",
                duration=(datetime.utcnow() - request_start).total_seconds(),
                request_timestamp=request_start
            )
            
            slack.send_message(
                text="🚨 Suspicious input detected and blocked.",
                blocks=[{
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "🚨 *Suspicious input detected and blocked.*\n\nPlease provide a valid HackerOne report ID.\nExample:\n• @Harry the H1 Analyst 123456\n• @Harry the H1 Analyst #123456"
                    }
                }],
                channel=event['channel'],
                thread_ts=event['ts']
            )
            return
        
        # Check if this is a /report command
        if re.search(r'<@[^>]+>\s*/report\b', text):
            log_event("Processing /report command via mention")
            
            # Import and call the report command handler
            from .slash_commands import handle_report_command
            from ..utils.structured_logging import log_interaction
            from ..utils.secret_protection import sanitize_for_users
            
            try:
                # Create a mock command object similar to what Slack would provide
                mock_command = {
                    'user_id': event.get('user', ''),
                    'channel_id': event.get('channel', ''),
                    'text': '',  # No additional text for report command
                    'command': '/report',
                    'is_mention': True  # Flag to indicate this is a mention
                }
                
                # Create mock ack and respond functions
                mock_ack, mock_respond = _create_mock_handlers(event, use_thread=False)
                
                # Call the report command handler with our mock objects
                from slack_sdk import WebClient
                from ..config import get_slack_tokens
                bot_token, _ = get_slack_tokens()
                client = WebClient(token=bot_token)
                
                handle_report_command(mock_ack, mock_respond, mock_command, client)
                
                # Log the interaction
                log_interaction(
                    user_id=event.get('user'),
                    channel_id=event['channel'],
                    thread_id=event['ts'],
                    user_message=f"Mention: /report",
                    response_text="Processing report command via mention",
                    duration=(datetime.utcnow() - request_start).total_seconds()
                )
                
                return
                
            except Exception as e:
                error_msg = f"Error processing /report command: {str(e)}"
                log_error(e, "Failed to process /report command via mention")
                
                # Send error response
                safe_error_msg = sanitize_for_users(error_msg)
                slack.send_message(
                    text=f"❌ {safe_error_msg}",
                    blocks=[
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": f"❌ *Error Processing /report Command*\n\n{safe_error_msg}\n\nPlease try again or use the slash command directly."
                            }
                        }
                    ],
                    channel=event['channel'],
                    thread_ts=event['ts']
                )
                
                # Log the error interaction
                log_interaction(
                    user_id=event.get('user'),
                    channel_id=event['channel'],
                    thread_id=event['ts'],
                    user_message=f"Mention: /report",
                    response_text=f"Error: {safe_error_msg}",
                    duration=(datetime.utcnow() - request_start).total_seconds()
                )
                return
        # Check if this is a /users command
        elif re.search(r'<@[^>]+>\s*/users\b', text):
            log_event("Processing /users command via mention")
            
            # Import and call the users command handler
            from .slash_commands import handle_users_command
            from ..utils.structured_logging import log_interaction
            from ..utils.secret_protection import sanitize_for_users
            
            try:
                # Extract organization name if provided
                org_match = re.search(r'<@[^>]+>\s*/users\s+(.+)', text)
                org_name = org_match.group(1).strip() if org_match else ""
                
                # Create a mock command object similar to what Slack would provide
                mock_command = {
                    'user_id': event.get('user', ''),
                    'channel_id': event.get('channel', ''),
                    'text': org_name,
                    'command': '/users'
                }
                
                # Create mock ack and respond functions
                mock_ack, mock_respond = _create_mock_handlers(event, use_thread=False)
                
                # Call the users command handler with our mock objects
                from slack_sdk import WebClient
                from ..config import get_slack_tokens
                bot_token, _ = get_slack_tokens()
                client = WebClient(token=bot_token)
                
                # Set a flag to indicate this is a mention, not a direct slash command
                mock_command['is_mention'] = True
                
                handle_users_command(mock_ack, mock_respond, mock_command, client)
                
                # Log the interaction
                log_interaction(
                    user_id=event.get('user'),
                    channel_id=event['channel'],
                    thread_id=event['ts'],
                    user_message=f"Mention: /users {org_name}",
                    response_text="Processing users command via mention",
                    duration=(datetime.utcnow() - request_start).total_seconds()
                )
                
                return
                
            except Exception as e:
                error_msg = f"Error processing /users command: {str(e)}"
                log_error(e, "Failed to process /users command via mention")
                
                # Send error response
                safe_error_msg = sanitize_for_users(error_msg)
                slack.send_message(
                    text=f"❌ {safe_error_msg}",
                    blocks=[
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": f"❌ *Error Processing /users Command*\n\n{safe_error_msg}\n\nPlease try again or use the slash command directly."
                            }
                        }
                    ],
                    channel=event['channel'],
                    thread_ts=event['ts']
                )
                
                # Log the error interaction
                log_interaction(
                    user_id=event.get('user'),
                    channel_id=event['channel'],
                    thread_id=event['ts'],
                    user_message=f"Mention: /users",
                    response_text=f"Error: {safe_error_msg}",
                    duration=(datetime.utcnow() - request_start).total_seconds()
                )
                return
            
            try:
                # Send initial response in main channel (not threaded)
                slack.send_message(
                    text="🔄 Generating weekly HackerOne report summary... This may take a moment.",
                    blocks=[
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": "🔄 *Generating Weekly Report*"
                            }
                        }
                    ],
                    channel=event['channel']
                    # Removed thread_ts to post in main channel
                )
                
                # Initialize the report analyzer
                analyzer = WeeklyReportAnalyzer()
                
                # Generate the weekly report
                report_data = analyzer.generate_weekly_summary()
                
                # Format the report for Slack
                formatted_report = _format_report_for_slack(report_data)
                
                # Send the final report in main channel (not threaded)
                slack.send_message(
                    text="📈 Weekly HackerOne Report Summary",
                    blocks=formatted_report,
                    channel=event['channel']
                    # Removed thread_ts to post in main channel
                )
                
                # Log the interaction
                log_interaction(
                    user_id=event.get('user'),
                    channel_id=event['channel'],
                    thread_id=event['ts'],
                    user_message=f"Mention: /report",
                    system_prompt="Generate weekly HackerOne report summary",
                    response_text="Weekly report generated successfully",
                    duration=(datetime.utcnow() - request_start).total_seconds()
                )
                
                log_event(f"Weekly report generated successfully for user {event.get('user')}")
                return
                
            except Exception as e:
                error_msg = f"Error generating weekly report: {str(e)}"
                log_error(e, "Failed to generate weekly report")
                
                # Send error response
                safe_error_msg = sanitize_for_users(error_msg)
                slack.send_message(
                    text=f"❌ {safe_error_msg}",
                    blocks=[
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": f"❌ *Error Generating Report*\n\n{safe_error_msg}\n\nPlease try again or contact support if the issue persists."
                            }
                        }
                    ],
                    channel=event['channel'],
                    thread_ts=event['ts']
                )
                
                # Log the error interaction
                log_interaction(
                    user_id=event.get('user'),
                    channel_id=event['channel'],
                    thread_id=event['ts'],
                    user_message=f"Mention: /report",
                    system_prompt="Generate weekly HackerOne report summary",
                    response_text=f"Error: {safe_error_msg}",
                    duration=(datetime.utcnow() - request_start).total_seconds()
                )
                return
        
        # Find report ID with enhanced validation - handle both plain numbers and tel: links
        match = re.search(r'<@[^>]+>\s*(?:#?(\d{6,8})(?:\s|$)|<tel:(\d{6,8})\|\d+>)', text)
        
        if not match:
            log_event("No valid report ID found in mention")
            
            # Log invalid format attempt
            log_mention_interaction(
                event=event,
                report_id="INVALID_FORMAT",
                response_text="Invalid report ID format - must be 6-8 digits",
                duration=(datetime.utcnow() - request_start).total_seconds(),
                request_timestamp=request_start
            )
            
            slack.send_message(
                text="❌ Error: Please provide a valid report ID.",
                blocks=[{
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "❌ Error: Please provide a valid HackerOne report ID (6-8 digits).\nExample:\n• @Harry the H1 Analyst 123456\n• @Harry the H1 Analyst #123456"
                    }
                }],
                channel=event['channel'],
                thread_ts=event['ts']
            )
            return
        
        # Extract report ID from either group (plain number or tel: link)
        rep_id = match.group(1) or match.group(2)
        
        # Additional validation: Check report ID range
        if not _is_valid_report_id(rep_id):
            log_event(f"Invalid report ID range: {rep_id}")
            
            # Log invalid range attempt
            log_mention_interaction(
                event=event,
                report_id=rep_id,
                response_text="Invalid report ID range - must be between 100000 and 99999999",
                duration=(datetime.utcnow() - request_start).total_seconds(),
                request_timestamp=request_start
            )
            
            slack.send_message(
                text="❌ Error: Invalid report ID.",
                blocks=[{
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "❌ Error: Report ID must be between 100000 and 99999999.\nExample:\n• @Harry the H1 Analyst 123456\n• @Harry the H1 Analyst #123456"
                    }
                }],
                channel=event['channel'],
                thread_ts=event['ts']
            )
            return
        
        log_event(f"Extracted and validated report ID: {rep_id}")
        
        # Store the original message timestamp and channel for threading
        slack.store_thread(rep_id, event['ts'], event['channel'])
        
        # Send initial response
        slack.send_message(
            text=f"Analyzing report {rep_id}... Please wait.",
            channel=event['channel'],
            thread_ts=event['ts']
        )
        
        # Analyze the report (this will be logged separately in analyze_report_with_logging)
        analyze_report_with_logging(rep_id, event['channel'], event['ts'], event, request_start)
        
    except Exception as e:
        log_error(e, "Error handling mention")
        
        # Log error interaction
        log_mention_interaction(
            event=event,
            report_id="ERROR",
            response_text=f"Error handling mention: {str(e)}",
            duration=(datetime.utcnow() - request_start).total_seconds(),
            request_timestamp=request_start
        )
        
        slack.send_message(
            text=f"Error handling mention: {str(e)}",
            channel=event['channel'],
            thread_ts=event['ts']
        )
