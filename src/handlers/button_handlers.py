"""
Button handlers for Hai.
Handles Slack button click events.
"""

import re
import os
import time
from datetime import datetime
from typing import Dict, Any, Optional, List
from concurrent.futures import ThreadPoolExecutor, as_completed
from ..api.hackerone import HackerOneAPI
from ..api.slack import SlackAPI
from ..utils.logging import log_button_press, log_error, log_info
from ..utils.structured_logging import log_button_interaction, log_modal_interaction
from ..utils.formatting import convert_markdown_to_slack
from ..utils.url_processing import process_report_content
from ..utils.authorization import require_authorization
from ..utils.mermaid import MermaidGenerator
from ..models import CredibilityScore
from .mention_handlers import follow_up_options_store
from .file_type_helpers import (
    is_code_file, is_text_file, is_document_file,
    create_image_analysis_prompt, create_code_analysis_prompt,
    create_text_analysis_prompt, create_document_analysis_prompt,
    create_generic_analysis_prompt
)

# Initialize API clients
hackerone = HackerOneAPI()
slack = SlackAPI()

def analyze_single_attachment(attachment: Dict[str, Any], rep_id: str, index: int) -> Dict[str, Any]:
    """
    Analyze a single attachment and return the result.
    
    Args:
        attachment: The attachment data
        rep_id: The report ID
        index: The attachment index
        
    Returns:
        Dict containing the analysis result and blocks
    """
    try:
        # Extract attachment details
        attachment_id = attachment['id']
        filename = attachment['filename']
        file_type = attachment['type']
        file_extension = os.path.splitext(filename)[1].lower()
        
        log_info(f"Analyzing attachment {attachment_id}: {filename} ({file_type}) for Report #{rep_id}")
        
        # Create blocks for this attachment
        blocks = []
        
        # Add attachment filename
        blocks.append(slack.create_section_block(
            text=f"*Attachment {index+1}: {attachment['filename']}*"
        ))
        
        # Extract the ID from the filename if possible
        display_id = "unknown"
        match = re.search(r'F(\d+)', attachment['filename'])
        if match:
            display_id = match.group(1)
            blocks.append(slack.create_context_block([
                {"type": "mrkdwn", "text": f"ID: F{display_id} | Type: {attachment['type']}"}
            ]))
        
        # Add the image or file link
        if attachment['type'].startswith('image/'):
            blocks.append(slack.create_image_block(
                image_url=attachment['url'],
                alt_text=attachment['filename'],
                title=attachment['filename']
            ))
        else:
            # Use filename for display while keeping original URL for link
            blocks.append(slack.create_section_block(
                text=f"📎 <{attachment['url']}|{attachment['filename']}> ({attachment['type']})"
            ))
        
        # Determine file type and create appropriate prompt
        if file_type.startswith('image/'):
            # For images, we can use the image_url parameter
            prompt = create_image_analysis_prompt(rep_id)
            analysis = hackerone.analyze_report(rep_id, prompt, image_url=attachment['url'])
        else:
            # For non-image files, we can't pass the file directly
            # Instead, create a prompt with file information
            if is_code_file(file_extension):
                base_prompt = create_code_analysis_prompt(rep_id, file_extension)
            elif is_text_file(file_type, file_extension):
                base_prompt = create_text_analysis_prompt(rep_id)
            elif is_document_file(file_type, file_extension):
                base_prompt = create_document_analysis_prompt(rep_id)
            else:
                base_prompt = create_generic_analysis_prompt(rep_id, file_type)
            
            # Add file information to the prompt
            enhanced_prompt = (
                f"{base_prompt}\n\n"
                f"File details:\n"
                f"- Filename: {filename}\n"
                f"- Type: {file_type}\n"
                f"- Extension: {file_extension}\n\n"
                f"Note: The file content is not directly accessible, but please provide an analysis "
                f"based on the report context and what you know about this type of file."
            )
            
            analysis = hackerone.analyze_report(rep_id, enhanced_prompt)
        
        if analysis:
            # Convert Markdown bold formatting to Slack bold formatting
            formatted_analysis = convert_markdown_to_slack(analysis)
            
            # Add a header for the analysis
            blocks.append(slack.create_section_block(text="*Hai Analysis:*"))
            
            # Use the new method to handle potentially long text
            analysis_blocks = slack.create_section_blocks_for_long_text(formatted_analysis)
            blocks.extend(analysis_blocks)
        
        return {
            'success': True,
            'blocks': blocks,
            'attachment_id': attachment_id,
            'filename': filename
        }
        
    except Exception as e:
        log_error(e, f"Error analyzing attachment {attachment.get('filename', 'unknown')}")
        return {
            'success': False,
            'blocks': [],
            'attachment_id': attachment.get('id', 'unknown'),
            'filename': attachment.get('filename', 'unknown'),
            'error': str(e)
        }

def extract_report_info(value: str) -> tuple:
    """
    Extract report ID and other info from button value.
    
    Args:
        value: Button value string
        
    Returns:
        tuple: (report_id, other parts)
    """
    parts = value.split("_")
    if len(parts) >= 2:
        return parts[-1], parts[:-1]
    return None, parts

@require_authorization
def handle_analyze_profile(ack: Any, body: Dict[str, Any], say: Any) -> None:
    """Handle AI analysis button click."""
    ack()  # Acknowledge the action
    
    # Extract the username and report ID from the button value
    value = body["actions"][0]["value"]
    parts = value.split("_")
    username = parts[2]
    rep_id = parts[3]
    
    log_button_press(f"Analyze profile for Reporter", rep_id)
    
    # Get thread_ts from the button event or fallback to stored thread
    thread_ts = body.get("message", {}).get("thread_ts") or slack.get_thread(rep_id)
    
    # If username is "unknown", try to get the actual username from the report
    if username == "unknown":
        try:
            # Get report details to extract the username
            report = hackerone.get_report(rep_id)
            if 'reporter' in report['data']['relationships']:
                reporter_data = report['data']['relationships']['reporter']['data']
                if 'attributes' in reporter_data and 'username' in reporter_data['attributes']:
                    username = reporter_data['attributes']['username']
        except Exception as e:
            log_error(e, "Error getting username from report")
    
    # Get the hacker's profile
    profile = hackerone.get_user_profile(username)
    
    # Send initial response
    slack.send_message(
        text=f"Analyzing {username} hacker profile and metrics...",
        thread_ts=thread_ts,
        channel=body["channel"]["id"]
    )
    
    try:
        # Analyze the hacker's profile using HackerOne Hai
        prompt = (
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
        
        analysis = convert_markdown_to_slack(hackerone.analyze_report(rep_id, prompt))
        
        # Don't log the full analysis to keep logs cleaner
        
        # Create response blocks
        blocks = [
            slack.create_header_block(f"AI Analysis: {username}")
        ]
        
        # Add profile picture if available
        if 'profile_picture' in profile:
            blocks.extend([
                slack.create_image_block(
                    image_url=profile['profile_picture'],
                    alt_text=f"{profile['username']}'s profile picture",
                    title=f"{profile['username']}'s profile picture"
                ),
                slack.create_section_block(
                    text=f"*<{profile['url']}|{profile['username']}'s profile>*"
                )
            ])
        
        # Add user details in a cleaner, more formatted way
        metrics_section = []
        
        # Format reputation with emoji
        rep_value = profile.get('reputation', 'N/A')
        metrics_section.append({"type": "mrkdwn", "text": f"*🏆 Reputation:* {rep_value}"})
        
        # Format impact with emoji
        impact_value = profile.get('impact', 'N/A')
        metrics_section.append({"type": "mrkdwn", "text": f"*💥 Impact:* {impact_value}"})
        
        # Format signal with emoji
        signal_value = profile.get('signal', 'N/A')
        metrics_section.append({"type": "mrkdwn", "text": f"*📊 Signal:* {signal_value}"})
        
        # Format joined date with emoji if available
        if 'joined' in profile:
            joined_value = profile.get('joined', 'N/A')
            metrics_section.append({"type": "mrkdwn", "text": f"*📅 Joined:* {joined_value}"})
        
        # Add metrics in one nicely formatted section
        blocks.append(slack.create_section_block(
            text="*Hacker Metrics:*",
        ))
        
        # Display metrics in a two-column layout
        blocks.append(slack.create_section_block(
            text=" ",  # Use a space instead of empty string
            fields=metrics_section
        ))
        
        # Add divider before analysis
        blocks.append(slack.create_divider_block())
        
        # Parse out confidence score if available
        confidence_score = None
        score_match = re.search(r'Confidence Score: (\d+\.\d+)/10\.0', analysis)
        if score_match:
            try:
                score_value = float(score_match.group(1))
                # Create a CredibilityScore object with the Hai-provided score
                confidence_score = CredibilityScore(
                    reputation_score=0,  # These values don't matter as we're 
                    impact_score=0,      # using the Hai-provided total score
                    signal_score=0,
                    account_age_modifier=0,
                    total_score=score_value  # Use Hai score directly
                )
                # Remove the confidence score line from the analysis
                analysis = re.sub(r'Confidence Score: \d+\.\d+/10\.0', '', analysis).strip()
            except ValueError:
                pass
        
        # Add analysis
        blocks.append(slack.create_section_block(
            text=f"*Analysis by HackerOne Hai:*\n{analysis}"
        ))
        
        # Add confidence score with visualization if available
        if confidence_score:
            blocks.append(slack.create_section_block(
                text=f"*Hacker Confidence:* {confidence_score.visual_score}"
            ))
        
        # Add report ID context
        blocks.append(slack.create_context_block([
            {"type": "mrkdwn", "text": f"For report #{rep_id}"}
        ]))
        
        # Add standard action buttons
        add_action_buttons(blocks, rep_id)
        
        # Send the analysis
        slack.send_message(
            text=f"AI Analysis of {username}'s profile",
            blocks=blocks,
            thread_ts=thread_ts,
            channel=body["channel"]["id"]
        )
        
    except Exception as e:
        log_error(e, "Error analyzing hacker profile")
        slack.send_message(
            text=f"Error analyzing {username}'s profile: {str(e)}",
            thread_ts=thread_ts,
            channel=body["channel"]["id"]
        )

def handle_view_profile(ack: Any, body: Dict[str, Any], say: Any) -> None:
    """Handle view profile button click."""
    ack()  # Acknowledge the action
    
    # Extract the username and report ID from the button value
    value = body["actions"][0]["value"]
    parts = value.split("_")
    username = parts[2]
    rep_id = parts[3]
    
    log_button_press("View profile", rep_id)
    
    # Get the hacker's profile
    profile = hackerone.get_user_profile(username)
    
    # Get thread_ts from the button event or fallback to stored thread
    thread_ts = body.get("message", {}).get("thread_ts") or slack.get_thread(rep_id)
    
    # Create response blocks
    blocks = [
        slack.create_header_block(f"Profile Details: {username}")
    ]
    
    # Add profile picture if available
    if 'profile_picture' in profile:
        blocks.append(slack.create_context_block([
            {
                "type": "image",
                "image_url": profile['profile_picture'],
                "alt_text": f"{profile['username']}'s profile picture"
            },
            {
                "type": "mrkdwn",
                "text": f"*<{profile['url']}|{profile['username']}'s profile>*"
            }
        ]))
    
    # Add user details in a cleaner, more formatted way
    metrics_section = []
    
    # Format reputation with emoji
    rep_value = profile.get('reputation', 'N/A')
    metrics_section.append({"type": "mrkdwn", "text": f"*🏆 Reputation:* {rep_value}"})
    
    # Format impact with emoji
    impact_value = profile.get('impact', 'N/A')
    metrics_section.append({"type": "mrkdwn", "text": f"*💥 Impact:* {impact_value}"})
    
    # Format signal with emoji
    signal_value = profile.get('signal', 'N/A')
    metrics_section.append({"type": "mrkdwn", "text": f"*📊 Signal:* {signal_value}"})
    
    # Format joined date with emoji if available
    if 'joined' in profile:
        joined_value = profile.get('joined', 'N/A')
        metrics_section.append({"type": "mrkdwn", "text": f"*📅 Joined:* {joined_value}"})
    
    # Add metrics in one nicely formatted section
    blocks.append(slack.create_section_block(
        text="*Hacker Metrics:*",
    ))
    
    # Display metrics in a two-column layout
    blocks.append(slack.create_section_block(
        text=" ",  # Use a space instead of empty string
        fields=metrics_section
    ))
    
    # Add report ID context
    blocks.append(slack.create_context_block([
        {"type": "mrkdwn", "text": f"For report #{rep_id}"}
    ]))
    
    # Add standard action buttons
    add_action_buttons(blocks, rep_id)
    
    # Send the profile details
    slack.send_message(
        text=f"Profile details for {username}",
        blocks=blocks,
        thread_ts=thread_ts,
        channel=body["channel"]["id"]
    )

@require_authorization
def handle_attachment_analysis(ack: Any, body: Dict[str, Any], say: Any) -> None:
    """Handle attachment analysis button click with block management."""
    ack()  # Acknowledge the action
    
    request_start = datetime.utcnow()
    
    # Extract the report ID from the button value
    value = body["actions"][0]["value"]
    rep_id = value.split("_")[2]
    
    log_button_press("Attachment Analysis", rep_id)
    
    # Get thread_ts from the button event or fallback to stored thread
    thread_ts = body.get("message", {}).get("thread_ts") or slack.get_thread(rep_id)
    
    # Send initial response
    slack.send_message(
        text=f"Analyzing attachments for report #{rep_id}... This may take a minute.",
        thread_ts=thread_ts,
        channel=body["channel"]["id"]
    )
    
    try:
        # Import block management utilities
        from ..utils.block_management import BlockManager
        
        # Get attachments from the full report
        report = hackerone.get_report(rep_id)
        attachments = hackerone.get_report_attachments(rep_id, report)
        
        if not attachments:
            slack.send_message(
                text=f"No attachments found for report #{rep_id}.",
                thread_ts=thread_ts,
                channel=body["channel"]["id"]
            )
            return
        
        # Process attachments in parallel for better performance
        log_info(f"Starting parallel analysis of {len(attachments)} attachments for report #{rep_id}")
        
        # Use ThreadPoolExecutor to analyze attachments in parallel
        with ThreadPoolExecutor(max_workers=min(len(attachments), 3)) as executor:
            # Submit all attachment analysis tasks
            future_to_attachment = {
                executor.submit(analyze_single_attachment, attachment, rep_id, i): (attachment, i)
                for i, attachment in enumerate(attachments)
            }
            
            # Collect results as they complete
            attachment_results = []
            for future in as_completed(future_to_attachment):
                attachment, index = future_to_attachment[future]
                try:
                    result = future.result()
                    attachment_results.append((index, result))
                    if result['success']:
                        log_info(f"Completed analysis for attachment {result['filename']} (index {index})")
                    else:
                        log_error(None, f"Failed to analyze attachment {result['filename']}: {result.get('error', 'Unknown error')}")
                except Exception as e:
                    log_error(e, f"Error in parallel attachment analysis for {attachment.get('filename', 'unknown')}")
                    attachment_results.append((index, {
                        'success': False,
                        'blocks': [],
                        'attachment_id': attachment.get('id', 'unknown'),
                        'filename': attachment.get('filename', 'unknown'),
                        'error': str(e)
                    }))
        
        # Sort results by original index to maintain order
        attachment_results.sort(key=lambda x: x[0])
        
        # Build blocks with smart chunking
        all_blocks = []
        processed_count = 0
        
        # Start with header
        header_block = slack.create_header_block(f"Attachment Analysis for Report #{rep_id}")
        all_blocks.append(header_block)
        
        # Process each attachment result
        for i, (index, result) in enumerate(attachment_results):
            # Calculate blocks needed for this attachment
            attachment_blocks = []
            
            # Add divider between attachments (except for first)
            if i > 0:
                attachment_blocks.append(slack.create_divider_block())
            
            if result['success']:
                attachment_blocks.extend(result['blocks'])
                processed_count += 1
            else:
                # Add error information for failed analysis
                attachment_blocks.append(slack.create_section_block(
                    text=f"*Attachment {index+1}: {result['filename']}*"
                ))
                attachment_blocks.append(slack.create_section_block(
                    text=f"❌ Error analyzing attachment: {result.get('error', 'Unknown error')}"
                ))
            
            # Check if adding these blocks would exceed the limit
            if not BlockManager.is_safe_to_add(all_blocks, attachment_blocks):
                # Send current blocks as a chunk
                log_info(f"Sending attachment analysis chunk with {len(all_blocks)} blocks")
                
                # Add action buttons to current chunk
                all_blocks.append(slack.create_divider_block())
                all_blocks.append(slack.create_action_button_block(rep_id))
                
                # Validate and send current chunk
                if BlockManager.validate_blocks(all_blocks, f"for attachment analysis chunk"):
                    slack.send_message(
                        text=f"Attachment analysis for report #{rep_id} (Part 1)",
                        blocks=all_blocks,
                        thread_ts=thread_ts,
                        channel=body["channel"]["id"]
                    )
                
                # Start new chunk with continuation header
                remaining_attachments = len(attachment_results) - i
                continuation_header = BlockManager.create_continuation_header(
                    2, 2, f"Attachment Analysis for Report #{rep_id}"
                )
                all_blocks = [continuation_header]
            
            # Add the attachment blocks
            all_blocks.extend(attachment_blocks)
        
        # Add summary block
        summary_block = BlockManager.create_attachment_summary_block(attachments, processed_count)
        all_blocks.append(summary_block)
        
        log_info(f"Completed parallel analysis of {len(attachments)} attachments for report #{rep_id}")
        
        # Add standard action buttons
        all_blocks.append(slack.create_divider_block())
        all_blocks.append(slack.create_action_button_block(rep_id))
        
        # Validate and send final blocks
        if BlockManager.validate_blocks(all_blocks, f"for final attachment analysis"):
            slack.send_message(
                text=f"Attachment analysis for report #{rep_id}",
                blocks=all_blocks,
                thread_ts=thread_ts,
                channel=body["channel"]["id"]
            )
        else:
            # If still too many blocks, use chunking
            chunks = BlockManager.chunk_blocks(all_blocks, include_action_buttons=True)
            for i, chunk in enumerate(chunks):
                if i == len(chunks) - 1:
                    # Last chunk gets action buttons
                    chunk.append(slack.create_divider_block())
                    chunk.append(slack.create_action_button_block(rep_id))
                
                chunk_title = f"Attachment analysis for report #{rep_id}"
                if len(chunks) > 1:
                    chunk_title += f" (Part {i+1}/{len(chunks)})"
                
                slack.send_message(
                    text=chunk_title,
                    blocks=chunk,
                    thread_ts=thread_ts,
                    channel=body["channel"]["id"]
                )
        
        # Log successful interaction
        duration = (datetime.utcnow() - request_start).total_seconds()
        log_button_interaction(
            user_id=body["user"]["id"],
            channel_id=body["channel"]["id"],
            thread_id=thread_ts or "",
            button_action="Attachment Analysis",
            report_id=rep_id,
            response_text=f"Successfully analyzed {len(attachments)} attachments with {processed_count} successful analyses",
            duration=duration,
            request_timestamp=request_start
        )
        
    except Exception as e:
        log_error(e, "Error analyzing attachments")
        
        # Log error interaction
        duration = (datetime.utcnow() - request_start).total_seconds()
        log_button_interaction(
            user_id=body["user"]["id"],
            channel_id=body["channel"]["id"],
            thread_id=thread_ts or "",
            button_action="Attachment Analysis",
            report_id=rep_id,
            response_text=f"Error analyzing attachments: {str(e)}",
            duration=duration,
            request_timestamp=request_start
        )
        
        slack.send_message(
            text=f"Error analyzing attachments for report #{rep_id}: {str(e)}",
            thread_ts=thread_ts,
            channel=body["channel"]["id"]
        )

def process_report_text_with_attachments(text: str, attachments: List[Dict[str, Any]]) -> tuple:
    """
    Process report text and replace attachment references with actual attachments.
    
    Args:
        text: The report text containing attachment references
        attachments: List of attachment details
        
    Returns:
        tuple: (List of Slack blocks with processed text and attachments, Set of used attachment IDs)
    """
    blocks = []
    current_text = ""
    used_attachment_ids = set()
    
    # Convert Markdown bold formatting to Slack bold formatting
    text = convert_markdown_to_slack(text)
    
    # Create a map of attachment IDs to details
    attachment_map = {}
    for attachment in attachments:
        # Use the raw ID from the API
        attachment_id = attachment['id']
        attachment_map[attachment_id] = attachment
        
        # Also try to extract ID from filename as a fallback (e.g., "F12345.png" -> "12345")
        match = re.search(r'F(\d+)', attachment['filename'])
        if match:
            extracted_id = match.group(1)
            attachment_map[extracted_id] = attachment
    
    # Split text by attachment references
    parts = re.split(r'(\{F\d+\})', text)
    
    for part in parts:
        # Check if this part is an attachment reference (in format {F12345})
        match = re.match(r'\{F(\d+)\}', part)
        
        if match:
            # If we have accumulated text, add it as a section
            if current_text:
                # Use the new method to handle potentially long text
                text_blocks = slack.create_section_blocks_for_long_text(current_text)
                blocks.extend(text_blocks)
                current_text = ""
            
            # Get attachment details
            attachment_id = match.group(1)
            if attachment_id in attachment_map:
                attachment = attachment_map[attachment_id]
                
                # Track that this attachment was used inline
                used_attachment_ids.add(attachment['id'])
                
                # Handle different file types
                if attachment['type'].startswith('image/'):
                    blocks.extend([
                        slack.create_image_block(
                            image_url=attachment['url'],
                            alt_text=attachment['filename'],
                            title=attachment['filename']
                        )
                    ])
                else:
                    # Use filename as display text for better user experience
                    blocks.append(slack.create_section_block(
                        text=f"📎 <{attachment['url']}|{attachment['filename']}> ({attachment['type']})"
                    ))
        else:
            current_text += part
    
    # Add any remaining text
    if current_text:
        # Use the new method to handle potentially long text
        text_blocks = slack.create_section_blocks_for_long_text(current_text)
        blocks.extend(text_blocks)
    
    return blocks, used_attachment_ids

@require_authorization
def handle_full_report_analysis(ack: Any, body: Dict[str, Any], say: Any) -> None:
    """Handle full report analysis button click with block management."""
    ack()  # Acknowledge the action
    
    request_start = datetime.utcnow()
    
    # Extract the report ID from the button value
    value = body["actions"][0]["value"]
    rep_id = value.split("_")[2]
    
    log_button_press("Full Report Analysis", rep_id)
    
    # Get thread_ts from the button event or fallback to stored thread
    thread_ts = body.get("message", {}).get("thread_ts") or slack.get_thread(rep_id)
    
    # Send initial response
    slack.send_message(
        text=f"Preparing full report for #{rep_id}... Please wait.",
        thread_ts=thread_ts,
        channel=body["channel"]["id"]
    )
    
    try:
        # Import block management utilities
        from ..utils.block_management import BlockManager
        
        # Get the full report data
        report = hackerone.get_report(rep_id)
        
        # Create response blocks
        blocks = [
            slack.create_header_block(f"Full Report Analysis: #{rep_id}")
        ]
        
        # Add report details
        if 'title' in report['data']['attributes']:
            blocks.append(slack.create_section_block(
                text=f"*Title:* {report['data']['attributes']['title']}"
            ))
        
        # Add report state and created date
        report_state = report['data']['attributes'].get('state', 'unknown')
        created_at = report['data']['attributes'].get('created_at', 'unknown')
        
        blocks.append(slack.create_section_block(
            text=" ",  # Use a space instead of empty string
            fields=[
                {"type": "mrkdwn", "text": f"*State:* {report_state}"},
                {"type": "mrkdwn", "text": f"*Submitted:* {created_at}"}
            ]
        ))
        
        # Add reporter information
        if 'reporter' in report['data']['relationships']:
            reporter_data = report['data']['relationships']['reporter']['data']
            if 'attributes' in reporter_data and 'username' in reporter_data['attributes']:
                username = reporter_data['attributes']['username']
                from ..config import get_hackerone_web_base_url
                blocks.append(slack.create_section_block(
                    text=f"*Reporter:* <{get_hackerone_web_base_url()}/{username}?type=user|{username}>"
                ))
        
        # Add divider before content
        blocks.append(slack.create_divider_block())
        
        # Get attachments from the report data
        attachments = hackerone.get_report_attachments(rep_id, report)
        
        # Track which attachments are used inline
        used_attachment_ids = set()
        
        # Add vulnerability information with inline attachments
        inline_blocks, used_ids = process_report_text_with_attachments(
            f"*Vulnerability Information:*\n{report['data']['attributes']['vulnerability_information']}",
            attachments
        )
        
        # Check if adding these blocks would exceed the limit
        if not BlockManager.is_safe_to_add(blocks, inline_blocks):
            # Send current blocks as first chunk
            blocks.append(slack.create_divider_block())
            blocks.append(slack.create_action_button_block(rep_id))
            
            slack.send_message(
                text=f"Full report analysis for #{rep_id} (Part 1)",
                blocks=blocks,
                thread_ts=thread_ts,
                channel=body["channel"]["id"]
            )
            
            # Start new chunk with continuation header
            blocks = [BlockManager.create_continuation_header(2, 2, f"Full Report Analysis: #{rep_id}")]
        
        blocks.extend(inline_blocks)
        used_attachment_ids.update(used_ids)
        
        # Add reproduction steps if available
        if 'reproduction_steps' in report['data']['attributes']:
            repro_blocks = [slack.create_divider_block()]
            inline_blocks, used_ids = process_report_text_with_attachments(
                f"*Reproduction Steps:*\n{report['data']['attributes']['reproduction_steps']}",
                attachments
            )
            repro_blocks.extend(inline_blocks)
            
            # Check if adding these blocks would exceed the limit
            if not BlockManager.is_safe_to_add(blocks, repro_blocks):
                # Send current blocks as chunk
                blocks.append(slack.create_divider_block())
                blocks.append(slack.create_action_button_block(rep_id))
                
                slack.send_message(
                    text=f"Full report analysis for #{rep_id} (Continued)",
                    blocks=blocks,
                    thread_ts=thread_ts,
                    channel=body["channel"]["id"]
                )
                
                # Start new chunk
                blocks = [BlockManager.create_continuation_header(3, 3, f"Full Report Analysis: #{rep_id}")]
            
            blocks.extend(repro_blocks)
            used_attachment_ids.update(used_ids)
        
        # Add proof of concept if available
        if 'proof_of_concept' in report['data']['attributes']:
            poc_blocks = [slack.create_divider_block()]
            inline_blocks, used_ids = process_report_text_with_attachments(
                f"*Proof of Concept:*\n{report['data']['attributes']['proof_of_concept']}",
                attachments
            )
            poc_blocks.extend(inline_blocks)
            
            # Check if adding these blocks would exceed the limit
            if not BlockManager.is_safe_to_add(blocks, poc_blocks):
                # Send current blocks as chunk
                blocks.append(slack.create_divider_block())
                blocks.append(slack.create_action_button_block(rep_id))
                
                slack.send_message(
                    text=f"Full report analysis for #{rep_id} (Continued)",
                    blocks=blocks,
                    thread_ts=thread_ts,
                    channel=body["channel"]["id"]
                )
                
                # Start new chunk
                blocks = [BlockManager.create_continuation_header(4, 4, f"Full Report Analysis: #{rep_id}")]
            
            blocks.extend(poc_blocks)
            used_attachment_ids.update(used_ids)
        
        # Find attachments that weren't used inline
        unused_attachments = [
            attachment for attachment in attachments 
            if attachment['id'] not in used_attachment_ids
        ]
        
        # If there are unused attachments, add them as links at the end
        if unused_attachments:
            attachment_blocks = [
                slack.create_divider_block(),
                slack.create_section_block(text="*Attachments:*")
            ]
            
            # Add each attachment link as its own section to preserve formatting
            for attachment in unused_attachments:
                attachment_blocks.append(slack.create_section_block(
                    text=f"• <{attachment['url']}|{attachment['filename']}> ({attachment['type']})"
                ))
            
            # Check if adding these blocks would exceed the limit
            if not BlockManager.is_safe_to_add(blocks, attachment_blocks):
                # Send current blocks as chunk
                blocks.append(slack.create_divider_block())
                blocks.append(slack.create_action_button_block(rep_id))
                
                slack.send_message(
                    text=f"Full report analysis for #{rep_id} (Continued)",
                    blocks=blocks,
                    thread_ts=thread_ts,
                    channel=body["channel"]["id"]
                )
                
                # Start new chunk for attachments
                blocks = [BlockManager.create_continuation_header(5, 5, f"Full Report Analysis: #{rep_id}")]
            
            blocks.extend(attachment_blocks)
        
        # Add standard action buttons
        blocks.append(slack.create_divider_block())
        blocks.append(slack.create_action_button_block(rep_id))
        
        # Validate and send final blocks
        if BlockManager.validate_blocks(blocks, f"for final full report analysis"):
            slack.send_message(
                text=f"Full report analysis for #{rep_id}",
                blocks=blocks,
                thread_ts=thread_ts,
                channel=body["channel"]["id"]
            )
        else:
            # If still too many blocks, use chunking as fallback
            chunks = BlockManager.chunk_blocks(blocks, include_action_buttons=True)
            for i, chunk in enumerate(chunks):
                if i == len(chunks) - 1:
                    # Last chunk gets action buttons
                    chunk.append(slack.create_divider_block())
                    chunk.append(slack.create_action_button_block(rep_id))
                
                chunk_title = f"Full report analysis for #{rep_id}"
                if len(chunks) > 1:
                    chunk_title += f" (Part {i+1}/{len(chunks)})"
                
                slack.send_message(
                    text=chunk_title,
                    blocks=chunk,
                    thread_ts=thread_ts,
                    channel=body["channel"]["id"]
                )
        
        # Log successful interaction
        duration = (datetime.utcnow() - request_start).total_seconds()
        log_button_interaction(
            user_id=body["user"]["id"],
            channel_id=body["channel"]["id"],
            thread_id=thread_ts or "",
            button_action="Full Report Analysis",
            report_id=rep_id,
            response_text="Successfully generated full report analysis with attachments and content",
            duration=duration,
            request_timestamp=request_start
        )
        
    except Exception as e:
        log_error(e, "Error generating full report analysis")
        
        # Log error interaction
        duration = (datetime.utcnow() - request_start).total_seconds()
        log_button_interaction(
            user_id=body["user"]["id"],
            channel_id=body["channel"]["id"],
            thread_id=thread_ts or "",
            button_action="Full Report Analysis",
            report_id=rep_id,
            response_text=f"Error generating full report analysis: {str(e)}",
            duration=duration,
            request_timestamp=request_start
        )
        
        slack.send_message(
            text=f"Error generating full report analysis for #{rep_id}: {str(e)}",
            thread_ts=thread_ts,
            channel=body["channel"]["id"]
        )

@require_authorization
def handle_suggest_followup(ack: Any, body: Dict[str, Any], say: Any) -> None:
    """Handle suggest follow-up options button click."""
    ack()  # Acknowledge the action
    
    # Extract the report ID from the button value
    value = body["actions"][0]["value"]
    rep_id = value.split("_")[2]
    
    log_button_press("Suggest Follow-up", rep_id)
    
    # Get thread_ts from the button event or fallback to stored thread
    thread_ts = body.get("message", {}).get("thread_ts") or slack.get_thread(rep_id)
    
    try:
        # Check if we have stored follow-up options
        if str(rep_id) not in follow_up_options_store:
            slack.send_message(
                text=f"No follow-up options found for report #{rep_id}. Please try analyzing the report again.",
                thread_ts=thread_ts,
                channel=body["channel"]["id"]
            )
            return
        
        # Get the stored follow-up options
        follow_up_options = follow_up_options_store[str(rep_id)]
        
        # Create response blocks
        blocks = [
            slack.create_header_block(f"Follow-up Options for Report #{rep_id}")
        ]
        
        # Add each follow-up option with its own button
        for i, option in enumerate(follow_up_options):
            # Add the option text and button in the same section
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": option
                },
                "accessory": {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "Select",
                        "emoji": True
                    },
                    "value": f"followup_{i}_{rep_id}",
                    "action_id": f"followup_option_{i}"
                }
            })
        
        # Add divider before other action buttons
        blocks.append(slack.create_divider_block())
        
        # Add other action buttons
        blocks.append(slack.create_action_button_block(rep_id))
        
        # Send the response
        slack.send_message(
            text=f"Follow-up suggestions for report #{rep_id}",
            blocks=blocks,
            thread_ts=thread_ts,
            channel=body["channel"]["id"]
        )
        
    except Exception as e:
        log_error(e, "Error generating follow-up suggestions")
        slack.send_message(
            text=f"Error generating follow-up suggestions for #{rep_id}: {str(e)}",
            thread_ts=thread_ts,
            channel=body["channel"]["id"]
        )

def add_action_buttons(blocks: list, rep_id: str) -> None:
    """Add standard action buttons to the block list."""
    blocks.append(slack.create_divider_block())
    blocks.append(slack.create_action_button_block(rep_id))

@require_authorization
def handle_followup_option(ack: Any, body: Dict[str, Any], say: Any) -> None:
    """Handle follow-up option button click."""
    ack()  # Acknowledge the action
    
    # Extract the option index and report ID from the button value
    value = body["actions"][0]["value"]
    option_index, rep_id = map(int, value.split("_")[1:])
    
    log_button_press(f"Follow-up Option {option_index}", str(rep_id))
    
    # Get thread_ts from the button event or fallback to stored thread
    thread_ts = body.get("message", {}).get("thread_ts") or slack.get_thread(str(rep_id))
    
    # Send acknowledgment
    slack.send_message(
        text=f"Processing follow-up option {option_index+1} for report #{rep_id}... Please wait.",
        thread_ts=thread_ts,
        channel=body["channel"]["id"]
    )
    
    try:
        # Get the report details
        report = hackerone.get_report(str(rep_id))
        
        # Get the follow-up option text
        follow_up_option = follow_up_options_store[str(rep_id)][option_index]
        
        # Generate response using HackerOne Hai
        prompt = (
            f"Based on the provided information, please provide a detailed response to "
            f"this follow-up question about report {rep_id}:\n\n"
            f"{follow_up_option}\n\n"
            f"Your response should be thorough and technically accurate, addressing all aspects "
            f"of the question. Include specific details, examples, and recommendations where applicable."
        )
        
        response = convert_markdown_to_slack(hackerone.analyze_report(str(rep_id), prompt))
        
        # Create response blocks
        blocks = [
            slack.create_header_block("Follow-up Response"),
            slack.create_section_block(text=f"*Selected Option:*\n{follow_up_option}"),
            slack.create_divider_block(),
            slack.create_section_block(text="*Response:*")
        ]
        
        # Use the new method to handle potentially long text
        response_blocks = slack.create_section_blocks_for_long_text(response)
        blocks.extend(response_blocks)
        
        # Add context
        blocks.append(slack.create_context_block([
            {"type": "mrkdwn", "text": f"For report #{rep_id}"}
        ]))
        
        # Add standard action buttons
        add_action_buttons(blocks, str(rep_id))
        
        # Send the response
        slack.send_message(
            text=f"Follow-up response for report #{rep_id}",
            blocks=blocks,
            thread_ts=thread_ts,
            channel=body["channel"]["id"]
        )
        
    except Exception as e:
        log_error(e, "Error generating follow-up response")
        slack.send_message(
            text=f"Error generating follow-up response for #{rep_id}: {str(e)}",
            thread_ts=thread_ts,
            channel=body["channel"]["id"]
        )

@require_authorization
def handle_generate_eraser_diagram(ack: Any, body: Dict[str, Any], say: Any) -> None:
    """Handle generate Eraser diagram button click."""
    ack()  # Acknowledge the action
    
    # Extract the report ID from the button value
    value = body["actions"][0]["value"]
    rep_id = value.split("_")[2]
    
    log_button_press("Generate Eraser Diagrams", rep_id)
    
    # Get thread_ts from the button event or fallback to stored thread
    thread_ts = body.get("message", {}).get("thread_ts") or slack.get_thread(rep_id)
    
    # Send acknowledgment
    slack.send_message(
        text=f"Generating Eraser diagrams for report #{rep_id}... Please wait.",
        thread_ts=thread_ts,
        channel=body["channel"]["id"]
    )
    
    try:
        # Get the report details
        report = hackerone.get_report(rep_id)
        
        # Extract relevant information from the report
        title = report['data']['attributes'].get('title', f'Report #{rep_id}')
        vulnerability_info = report['data']['attributes'].get('vulnerability_information', '')
        
        # Initialize the Eraser API client
        from ..api.eraser_api import EraserAPI
        eraser = EraserAPI()
        
        # Import the image processing utility
        from ..utils.image_processing import remove_transparency
        
        # Create the prompt for architecture diagram
        arch_prompt = (
            f"Create a diagram for the following security vulnerability:\n\n"
            f"Title: {title}\n\n"
            f"Description:\n{vulnerability_info}\n\n"
            f"Please visualize the attack flow, vulnerability, or system architecture "
            f"to help understand the technical aspects of this security issue. "
            f"Ensure the diagram has a left-to-right flow direction for clarity and readability."
        )
        
        # Create the prompt for sequence diagram
        seq_prompt = (
            f"IMPORTANT: Please carefully analyze and study the following security vulnerability information in great detail before creating the sequence diagram.\n\n"
            f"Security Vulnerability Report:\n"
            f"Title: {title}\n\n"
            f"Detailed Description:\n{vulnerability_info}\n\n"
            f"ANALYSIS REQUIREMENTS:\n"
            f"1. Thoroughly examine all steps, interactions, and technical details provided\n"
            f"2. Identify all actors, systems, and components involved in the vulnerability\n"
            f"3. Map the exact sequence of events that lead to the security issue\n"
            f"4. Understand the timing and order of all interactions\n"
            f"5. Note any authentication, authorization, or validation steps that are bypassed\n\n"
            f"SEQUENCE DIAGRAM REQUIREMENTS:\n"
            f"- Create a detailed sequence diagram showing the complete vulnerability exploitation flow\n"
            f"- Include all relevant actors (attacker, user, system components, databases, etc.)\n"
            f"- Show the exact sequence of messages, requests, and responses\n"
            f"- Highlight where the vulnerability occurs in the interaction flow\n"
            f"- Use proper sequence diagram notation and timing\n"
            f"- Include error conditions and security bypass points\n"
            f"- Label all interactions with technically accurate descriptions\n\n"
            f"Please study the vulnerability information meticulously to ensure the sequence accurately reflects the security issue described."
        )
        
        # Generate both diagrams in parallel for better performance
        log_info(f"Starting parallel Eraser diagram generation for report #{rep_id}")
        
        with ThreadPoolExecutor(max_workers=2) as executor:
            # Submit both diagram generation tasks
            arch_future = executor.submit(eraser.generate_diagram_from_prompt, arch_prompt)
            seq_future = executor.submit(eraser.generate_sequence_diagram_from_prompt, seq_prompt)
            
            # Wait for both to complete
            arch_result = arch_future.result()
            seq_result = seq_future.result()
            
            log_info(f"Completed parallel Eraser diagram generation for report #{rep_id}")
        
        arch_url = arch_result.get('url')
        seq_url = seq_result.get('url')
        
        # Send combined message FIRST if at least one diagram was generated
        if arch_url or seq_url:
            # Create combined header and description
            combined_blocks = [
                slack.create_header_block(f"Eraser Diagrams for Report #{rep_id}"),
                slack.create_section_block(
                    text=(
                        f"*Architecture Diagram:* Visualizes the system architecture and attack flow\n"
                        f"*Sequence Diagram:* Shows the step-by-step interaction flow"
                    )
                )
            ]
            
            # Send the combined message FIRST
            slack.send_message(
                text=f"Eraser diagrams for report #{rep_id}",
                blocks=combined_blocks,
                thread_ts=thread_ts,
                channel=body["channel"]["id"]
            )
        
        # Now process and upload the diagrams
        arch_temp_path = None
        seq_temp_path = None
        
        # Process architecture diagram if available
        if arch_url:
            # Process the image to remove transparency
            arch_temp_path = remove_transparency(arch_url)
            
            if arch_temp_path:
                # Upload the processed image to Slack
                arch_upload = slack.upload_image(
                    file_path=arch_temp_path,
                    title=f"Architecture Diagram for Report #{rep_id}",
                    channel_id=body["channel"]["id"],
                    thread_ts=thread_ts
                )
                log_info(f"Architecture diagram upload initiated for report #{rep_id}")
            else:
                # If processing failed, log the error
                log_error(None, f"Failed to process architecture diagram for report #{rep_id}")
        
        # Process sequence diagram if available
        if seq_url:
            # Process the image to remove transparency
            seq_temp_path = remove_transparency(seq_url)
            
            if seq_temp_path:
                # Upload the processed image to Slack
                seq_upload = slack.upload_image(
                    file_path=seq_temp_path,
                    title=f"Sequence Diagram for Report #{rep_id}",
                    channel_id=body["channel"]["id"],
                    thread_ts=thread_ts
                )
                log_info(f"Sequence diagram upload initiated for report #{rep_id}")
                
                # Wait 15 seconds after sequence diagram upload to ensure both diagrams are uploaded
                log_info(f"Waiting 15 seconds for diagram uploads to complete for report #{rep_id}")
                time.sleep(15)
                
                # Send action buttons after delay
                button_blocks = [
                    slack.create_divider_block(),
                    slack.create_action_button_block(rep_id)
                ]
                
                slack.send_message(
                    text=f"Actions for report #{rep_id}",
                    blocks=button_blocks,
                    thread_ts=thread_ts,
                    channel=body["channel"]["id"]
                )
            else:
                # If processing failed, log the error
                log_error(None, f"Failed to process sequence diagram for report #{rep_id}")
        
        # If neither diagram was generated successfully
        if not (arch_url or seq_url):
            slack.send_message(
                text=f"Could not generate Eraser diagrams for report #{rep_id}. No URLs returned.",
                thread_ts=thread_ts,
                channel=body["channel"]["id"]
            )
        
        # Clean up temporary files
        import os
        if arch_temp_path and os.path.exists(arch_temp_path):
            os.remove(arch_temp_path)
        if seq_temp_path and os.path.exists(seq_temp_path):
            os.remove(seq_temp_path)
        
    except Exception as e:
        log_error(e, "Error generating Eraser diagrams")
        slack.send_message(
            text=f"Error generating Eraser diagrams for #{rep_id}: {str(e)}",
            thread_ts=thread_ts,
            channel=body["channel"]["id"]
        )

@require_authorization
def handle_generate_mermaid(ack: Any, body: Dict[str, Any], say: Any) -> None:
    """Handle generate mermaid diagram button click."""
    ack()  # Acknowledge the action
    
    # Extract the report ID from the button value
    value = body["actions"][0]["value"]
    rep_id = value.split("_")[1]
    
    log_button_press("Generate Mermaid", rep_id)
    
    # Get thread_ts from the button event or fallback to stored thread
    thread_ts = body.get("message", {}).get("thread_ts") or slack.get_thread(rep_id)
    
    # Send acknowledgment
    slack.send_message(
        text=f"Generating mermaid diagram for report #{rep_id}... Please wait.",
        thread_ts=thread_ts,
        channel=body["channel"]["id"]
    )
    
    try:
        # Get the report details
        report = hackerone.get_report(rep_id)
        
        # Generate diagram using HackerOne Hai
        prompt = (
            f"Based on the vulnerability described in report {rep_id}, create a mermaid diagram "
            f"that visualizes the attack flow, vulnerability, or system architecture. "
            f"The diagram should help understand the technical aspects of the vulnerability.\n\n"
            
            f"IMPORTANT SYNTAX REQUIREMENTS:\n"
            f"When creating the diagram, ensure you use Mermaid syntax correctly and safely by following these rules:\n"
            f"1. Use special characters ONLY for their intended Mermaid syntax purposes:\n"
            f"   - Curly braces {{ }} only for styling and directives\n"
            f"   - Parentheses ( ) only for flowchart syntax and round edges\n"
            f"   - Square brackets [ ] only for node declarations\n"
            f"   - Angle brackets < > only in link/arrow notation (-->, -.->)\n"
            f"   - Hyphens - only in link syntax\n"
            f"   - Double quotes \" only for properly quoted attributes and labels\n"
            f"   - Single quotes ' only when properly paired in attribute values\n"
            f"   - Colons : only in class and subgraph declarations\n"
            f"   - Hash # only for colors and class selectors\n"
            f"   - Backticks ` only when properly paired\n"
            f"   - Periods . only in link styles and CSS class names\n"
            f"   - Backslashes \\ only as escape characters\n"
            f"   - Semicolons ; only to end lines in appropriate diagram types\n"
            f"   - Avoid using &, %, @ in node text as they may cause encoding issues\n\n"
            
            f"2. For node text and labels:\n"
            f"   - Use simple, descriptive text without special characters\n"
            f"   - If you need to include code or commands in node text, simplify the syntax\n"
            f"   - Do not include HTML, XML, or other markup in node text\n\n"
            
            f"3. Structure:\n"
            f"   - Use only standard Mermaid diagram types (flowchart, sequenceDiagram, etc.)\n"
            f"   - Ensure all nodes and connections use valid Mermaid syntax\n"
            f"   - Keep the diagram focused and readable\n\n"
            
            f"Include the mermaid code block in your response, surrounded by triple backticks and 'mermaid' "
            f"like this: ```mermaid\n[your diagram code here]\n```\n\n"
            f"Also provide a brief explanation of what the diagram shows."
        )
        
        response = hackerone.analyze_report(rep_id, prompt)
        
        # Extract mermaid code
        mermaid_code = MermaidGenerator.extract_mermaid_code(response)
        
        if mermaid_code:
            # Generate URL
            url = MermaidGenerator.generate_url(mermaid_code)
            
            # Split the response into parts before and after the mermaid code
            parts = response.split(mermaid_code)
            
            # Take only the text that comes after the mermaid code block as the explanation
            # This skips the introductory text completely
            if len(parts) > 1 and parts[1].strip():
                raw_explanation = parts[1].strip()
                
                # Remove any trailing backticks from the code block
                raw_explanation = raw_explanation.lstrip('`')
                
                # Remove any complete code block markers that might be present
                if raw_explanation.startswith('```'):
                    end_marker = raw_explanation.find('```', 3)
                    if end_marker != -1:
                        raw_explanation = raw_explanation[end_marker + 3:].strip()
                    else:
                        raw_explanation = raw_explanation[3:].strip()
                
                # Further clean up: look for explanation markers
                explanation_markers = ["### Explanation", "## Explanation", "# Explanation", "Explanation:", "Explanation of the Diagram"]
                for marker in explanation_markers:
                    if marker in raw_explanation:
                        # Extract everything after the marker
                        marker_index = raw_explanation.find(marker)
                        if marker_index != -1:
                            raw_explanation = raw_explanation[marker_index:].strip()
                            break
            else:
                # Fallback if there's nothing after the mermaid code
                raw_explanation = "Diagram shows the vulnerability flow."
            
            # Convert Markdown bold formatting to Slack formatting
            explanation = convert_markdown_to_slack(raw_explanation)
            
            # Create blocks with buttons automatically included
            blocks = MermaidGenerator.create_slack_blocks(
                mermaid_code=mermaid_code,
                title=f"Mermaid for Report #{rep_id}",
                description=explanation
            )
            
            # Add standard action buttons
            add_action_buttons(blocks, rep_id)
            
            # No need to add buttons separately as they're now included in MermaidGenerator.create_slack_blocks
            
            # Send the response
            slack.send_message(
                text=f"Mermaid diagram for report #{rep_id}",
                blocks=blocks,
                thread_ts=thread_ts,
                channel=body["channel"]["id"]
            )
        else:
            slack.send_message(
                text=f"Could not generate mermaid diagram for report #{rep_id}",
                thread_ts=thread_ts,
                channel=body["channel"]["id"]
            )
        
    except Exception as e:
        log_error(e, "Error generating mermaid diagram")
        slack.send_message(
            text=f"Error generating mermaid diagram for #{rep_id}: {str(e)}",
            thread_ts=thread_ts,
            channel=body["channel"]["id"]
        )

@require_authorization
def handle_retry_analysis(ack: Any, body: Dict[str, Any], say: Any) -> None:
    """Handle retry analysis button click."""
    ack()  # Acknowledge the action
    
    # Extract the report ID from the button value
    value = body["actions"][0]["value"]
    rep_id = value.split("_")[1]
    
    log_button_press("Retry Analysis", rep_id)
    
    # Get thread_ts from the button event or fallback to stored thread
    thread_ts = body.get("message", {}).get("thread_ts") or slack.get_thread(rep_id)
    
    # Send acknowledgment
    slack.send_message(
        text=f"Retrying analysis for report #{rep_id}... Please wait.",
        thread_ts=thread_ts,
        channel=body["channel"]["id"]
    )
    
    try:
        # Double the timeout for retry attempts
        from ..config import get_api_timeout
        from ..handlers.mention_handlers import analyze_report
        
        doubled_timeout = get_api_timeout() * 2
        log_info(f"Doubling timeout for retry analysis of report #{rep_id}: {get_api_timeout()} → {doubled_timeout} seconds")
        
        # Call the same analyze_report function used by handle_mention, but with doubled timeout
        analyze_report(rep_id, body["channel"]["id"], thread_ts, timeout=doubled_timeout)
        
    except Exception as e:
        log_error(e, "Error retrying analysis")
        slack.send_message(
            text=f"Error retrying analysis for #{rep_id}: {str(e)}",
            thread_ts=thread_ts,
            channel=body["channel"]["id"]
        )

@require_authorization
def handle_update_status(ack: Any, body: Dict[str, Any], client: Any) -> None:
    """Handle update status button click."""
    ack()  # Acknowledge the action
    
    # Extract the report ID from the button value
    value = body["actions"][0]["value"]
    rep_id = value.split("_")[2]
    
    log_button_press("Update Status", rep_id)
    
    # Store the channel ID for later use
    channel_id = body["channel"]["id"]
    thread_ts = body.get("message", {}).get("thread_ts")
    
    # Store the thread_ts and channel_id for this report
    if thread_ts:
        slack.store_thread(rep_id, thread_ts, channel_id)
        log_info(f"Stored thread_ts {thread_ts} and channel_id {channel_id} for report #{rep_id}")
    
    # Fetch the current state of the report
    current_state = "unknown"
    try:
        report = hackerone.get_report(rep_id)
        current_state = report["data"]["attributes"]["state"]
        log_info(f"Current state for report #{rep_id}: {current_state}")
    except Exception as e:
        log_error(e, f"Error fetching current state for report #{rep_id}")
    
    # Define all available states
    all_states = [
        {"text": {"type": "plain_text", "text": "new"}, "value": "new"},
        {"text": {"type": "plain_text", "text": "pending-program-review"}, "value": "pending-program-review"},
        {"text": {"type": "plain_text", "text": "needs-more-info"}, "value": "needs-more-info"},
        {"text": {"type": "plain_text", "text": "informative"}, "value": "informative"},
        {"text": {"type": "plain_text", "text": "duplicate"}, "value": "duplicate"},
        {"text": {"type": "plain_text", "text": "spam (-10)"}, "value": "spam"},
        {"text": {"type": "plain_text", "text": "not-applicable (-5)"}, "value": "not-applicable"}
    ]
    
    # Filter out the current state
    available_states = [state for state in all_states if state["value"] != current_state]
    
    # Create a modal dialog with a dropdown
    modal = {
        "type": "modal",
        "callback_id": "update_status_modal",
        "title": {
            "type": "plain_text",
            "text": "Update Report Status"
        },
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"⚠️ *Warning:* This will update the report status and notify the reporter and may deduct reputation points based on your selection.\n\n*Current status:* `{current_state}`"
                }
            },
            {
                "type": "input",
                "block_id": "status_block",
                "element": {
                    "type": "static_select",
                    "action_id": "status_select",
                    "placeholder": {
                        "type": "plain_text",
                        "text": "Select a status"
                    },
                    "options": available_states
                },
                "label": {
                    "type": "plain_text",
                    "text": "New Status"
                }
            },
            {
                "type": "input",
                "block_id": "message_block",
                "optional": True,
                "element": {
                    "type": "plain_text_input",
                    "action_id": "message_input",
                    "multiline": True,
                    "placeholder": {
                        "type": "plain_text",
                        "text": "Add a message to the reporter explaining this status change..."
                    }
                },
                "label": {
                    "type": "plain_text",
                    "text": "Message (optional)"
                }
            }
        ],
        "submit": {
            "type": "plain_text",
            "text": "Update Status"
        },
        "close": {
            "type": "plain_text",
            "text": "Cancel"
        },
        "private_metadata": rep_id  # Store the report ID for use in the submission handler
    }
    
    # Open the modal
    try:
        client.views_open(
            trigger_id=body["trigger_id"],
            view=modal
        )
    except Exception as e:
        log_error(e, "Error opening Update Status modal")

@require_authorization
def handle_update_status_submission(ack: Any, body: Dict[str, Any], view: Dict[str, Any], client: Any) -> None:
    """Handle the Update Status modal submission."""
    ack()  # Acknowledge the submission
    
    request_start = datetime.utcnow()
    
    # Extract the report ID from private_metadata
    rep_id = view["private_metadata"]
    
    # Get the selected status (new status)
    new_status = view["state"]["values"]["status_block"]["status_select"]["selected_option"]["value"]
    
    # Get the optional message
    message = view["state"]["values"]["message_block"]["message_input"]["value"]
    if not message:
        message = f"Status changed to {new_status}"
    
    # Get thread_ts for the report
    thread_ts = slack.get_thread(rep_id)
    
    # Get channel_id using multiple fallback methods
    channel_id = None
    
    # Method 1: Try to get from stored thread info
    channel_id = slack.get_channel(rep_id)
    
    # Method 2: Try to get from the view submission context
    if not channel_id:
        if "container" in body and "channel_id" in body["container"]:
            channel_id = body["container"]["channel_id"]
    
    # Method 3: Try to get from the thread info using conversations_replies
    if not channel_id and thread_ts:
        try:
            # First try with the user's team ID
            team_id = body["user"]["team_id"] if "user" in body and "team_id" in body["user"] else None
            if team_id:
                try:
                    thread_info = client.conversations_replies(
                        channel=team_id,
                        ts=thread_ts
                    )
                    if thread_info["ok"] and thread_info["messages"]:
                        channel_id = thread_info["channel"]
                except Exception as e:
                    log_error(e, f"Error getting thread info using team ID for {thread_ts}")
        except Exception as e:
            log_error(e, f"Error in method 3 for getting channel ID")
    
    # Method 4: Try to open a DM with the user
    if not channel_id:
        try:
            user_id = body["user"]["id"]
            dm = client.conversations_open(users=user_id)
            if dm["ok"]:
                channel_id = dm["channel"]["id"]
                log_info(f"Using DM channel {channel_id} for user {user_id}")
        except Exception as e:
            log_error(e, f"Error opening DM with user: {str(e)}")
    
    # Log the channel ID for debugging
    log_info(f"Final channel ID for report #{rep_id}: {channel_id}")
    
    # Get user info who made the change
    user_id = body["user"]["id"]
    username = "Unknown user"
    try:
        user_info = client.users_info(user=user_id)
        username = user_info["user"].get("profile", {}).get("display_name") or user_info["user"]["name"]
    except Exception as e:
        log_error(e, f"Error getting user info for user {user_id}")
    
    # Get current status of the report
    current_status = "unknown"
    try:
        report = hackerone.get_report(rep_id)
        current_status = report["data"]["attributes"]["state"]
    except Exception as e:
        log_error(e, f"Error getting current status for report #{rep_id}")
    
    # Log the status change at INFO level
    status_change_message = f"Report #{rep_id} status update by @{username}: {current_status} → {new_status} | Message: {message}"
    log_info(status_change_message)
    
    try:
        # Update the report status in HackerOne
        response = hackerone._make_request(
            f"reports/{rep_id}/state_changes",
            method='post',
            json_data={
                "data": {
                    "type": "state-change",
                    "attributes": {
                        "message": message,
                        "state": new_status
                    }
                }
            }
        )
        
        # Only send a message if we have a channel ID
        if channel_id:
            # Create blocks for the confirmation message
            blocks = [
                slack.create_section_block(
                    text=f"Report #{rep_id} status updated by @{username}\n" +
                         f"*Status change:* {current_status} → *{new_status}*\n" +
                         f"*Message:* {message}"
                )
            ]
            
            # Add standard action buttons
            add_action_buttons(blocks, rep_id)
            
            # Send a confirmation message with who made the change and what changed
            slack.send_message(
                text=f"Report #{rep_id} status updated by @{username}",
                blocks=blocks,
                thread_ts=thread_ts,
                channel=channel_id
            )
        else:
            log_error(None, f"Could not send confirmation message for report #{rep_id}: No channel ID available")
        
        # Log successful interaction
        duration = (datetime.utcnow() - request_start).total_seconds()
        log_modal_interaction(
            user_id=user_id,
            channel_id=channel_id or "unknown",
            thread_id=thread_ts or "",
            modal_type="Update Status",
            user_input=f"Status: {new_status}, Message: {message}",
            report_id=rep_id,
            response_text=f"Successfully updated report status from {current_status} to {new_status}",
            duration=duration,
            request_timestamp=request_start
        )
        
    except Exception as e:
        log_error(e, f"Error updating status for report #{rep_id}")
        
        # Log error interaction
        duration = (datetime.utcnow() - request_start).total_seconds()
        log_modal_interaction(
            user_id=user_id,
            channel_id=channel_id or "unknown",
            thread_id=thread_ts or "",
            modal_type="Update Status",
            user_input=f"Status: {new_status}, Message: {message}",
            report_id=rep_id,
            response_text=f"Error updating status: {str(e)}",
            duration=duration,
            request_timestamp=request_start
        )
        
        # Send error message
        slack.send_message(
            text=f"Error updating status for report #{rep_id}: {str(e)}",
            thread_ts=thread_ts,
            channel=channel_id
        )

def handle_acknowledge_report(ack: Any, body: Dict[str, Any], say: Any) -> None:
    """Handle acknowledge report button click."""
    ack()  # Acknowledge the action
    
    # Extract the report ID from the button value
    value = body["actions"][0]["value"]
    rep_id = value.split("_")[1]
    
    log_button_press("Acknowledge Report", rep_id)
    
    # Get thread_ts from the button event or fallback to stored thread
    thread_ts = body.get("message", {}).get("thread_ts") or slack.get_thread(rep_id)
    
    # Send acknowledgment
    slack.send_message(
        text=f"Acknowledging report #{rep_id}... Please wait.",
        thread_ts=thread_ts,
        channel=body["channel"]["id"]
    )
    
    try:
        # Acknowledge the report
        response = hackerone.acknowledge_report(rep_id)
        
        # Send success message
        slack.send_message(
            text=f"✅ Report #{rep_id} has been acknowledged successfully.",
            thread_ts=thread_ts,
            channel=body["channel"]["id"]
        )
        
    except Exception as e:
        log_error(e, "Error acknowledging report")
        slack.send_message(
            text=f"Error acknowledging report #{rep_id}: {str(e)}",
            thread_ts=thread_ts,
            channel=body["channel"]["id"]
        )

@require_authorization
def handle_ask_harry(ack: Any, body: Dict[str, Any], client: Any) -> None:
    """Handle Ask Harry button click."""
    ack()  # Acknowledge the action
    
    # Extract the report ID from the button value
    value = body["actions"][0]["value"]
    rep_id = value.split("_")[2]
    
    log_button_press("Ask Harry", rep_id)
    
    # Store the channel ID for later use
    channel_id = body["channel"]["id"]
    thread_ts = body.get("message", {}).get("thread_ts")
    
    # Store the thread_ts and channel_id for this report
    if thread_ts:
        slack.store_thread(rep_id, thread_ts, channel_id)
        log_info(f"Stored thread_ts {thread_ts} and channel_id {channel_id} for report #{rep_id}")
    
    # Create a modal dialog for the user to ask a question
    modal = {
        "type": "modal",
        "callback_id": "ask_harry_modal",
        "title": {
            "type": "plain_text",
            "text": "Ask Harry"
        },
        "submit": {
            "type": "plain_text",
            "text": "Submit"
        },
        "close": {
            "type": "plain_text",
            "text": "Cancel"
        },
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Ask a question about report #{rep_id}*\nHarry will analyze your question in the context of this report."
                }
            },
            {
                "type": "input",
                "block_id": "question_block",
                "element": {
                    "type": "plain_text_input",
                    "action_id": "question_input",
                    "multiline": True,
                    "placeholder": {
                        "type": "plain_text",
                        "text": "Enter your question here..."
                    }
                },
                "label": {
                    "type": "plain_text",
                    "text": "Your Question"
                }
            }
        ],
        "private_metadata": rep_id  # Store the report ID for use in the submission handler
    }
    
    # Open the modal
    try:
        client.views_open(
            trigger_id=body["trigger_id"],
            view=modal
        )
    except Exception as e:
        log_error(e, "Error opening Ask Harry modal")

@require_authorization
def handle_ask_harry_submission(ack: Any, body: Dict[str, Any], view: Dict[str, Any], client: Any) -> None:
    """Handle the Ask Harry modal submission."""
    ack()  # Acknowledge the submission
    
    request_start = datetime.utcnow()
    
    # Extract the report ID from private_metadata
    rep_id = view["private_metadata"]
    
    # Get the user's question from the submitted view
    question = view["state"]["values"]["question_block"]["question_input"]["value"]
    
    # Log the question at INFO level
    log_info(f"Question for report #{rep_id}: {question}")
    
    # Get thread_ts for the report
    thread_ts = slack.get_thread(rep_id)
    
    # Log the thread_ts for debugging
    log_info(f"Thread timestamp for report #{rep_id}: {thread_ts}")
    
    # Get user info
    user_id = body["user"]["id"]
    
    try:
        # Get user info from Slack
        user_info = client.users_info(user=user_id)
        # Use display name if available, otherwise fall back to regular name
        user_name = user_info["user"].get("profile", {}).get("display_name") or user_info["user"]["name"]
        
        # Get the channel ID from the stored thread info
        channel_id = slack.get_channel(rep_id)
        
        # If we don't have a channel ID, try to get it from the view submission context
        if not channel_id:
            # Try to get the channel from the container
            if "container" in body and "channel_id" in body["container"]:
                channel_id = body["container"]["channel_id"]
        
        # If we still don't have a channel ID, log an error and use a fallback
        if not channel_id:
            log_error(None, f"Could not find channel ID for thread {thread_ts}")
            # Use a default channel as a last resort
            channel_id = body.get("user", {}).get("team_id")
        
        # Post the user's question in the thread with attribution
        slack.send_message(
            text=f"Question from @{user_name}:\n{question}",
            thread_ts=thread_ts,
            channel=channel_id
        )
        
        # Create prompt for HackerOne Hai
        prompt = (
            f"Please answer the following question about report #{rep_id}:\n\n"
            f"{question}\n\n"
            f"Provide a concise, technically accurate answer based on the information in the report. "
            f"If you need more information that isn't available in the report, please say so."
        )
        
        # Send initial message
        slack.send_message(
            text=f"Analyzing question... Please wait.",
            thread_ts=thread_ts,
            channel=channel_id
        )
        
        # Send the question to HackerOne Hai
        response = hackerone.analyze_report(rep_id, prompt)
        
        # Post the response in the thread
        formatted_response = convert_markdown_to_slack(response)
        
        # Create response blocks
        blocks = [
            slack.create_header_block("Harry's Response"),
            slack.create_section_block(
                text=f"*Question:*\n{question}"
            ),
            slack.create_divider_block(),
            slack.create_section_block(text="*Answer:*")
        ]
        
        # Use the new method to handle potentially long text
        response_blocks = slack.create_section_blocks_for_long_text(formatted_response)
        blocks.extend(response_blocks)
        
        # Add context
        blocks.append(slack.create_context_block([
            {"type": "mrkdwn", "text": f"For report #{rep_id}"}
        ]))
        
        # Add standard action buttons
        add_action_buttons(blocks, rep_id)
        
        # Send the response
        slack.send_message(
            text=f"Response to question about report #{rep_id}",
            blocks=blocks,
            thread_ts=thread_ts,
            channel=channel_id
        )
        
        # Log successful interaction
        duration = (datetime.utcnow() - request_start).total_seconds()
        log_modal_interaction(
            user_id=user_id,
            channel_id=channel_id or "unknown",
            thread_id=thread_ts or "",
            modal_type="Ask Harry",
            user_input=question,
            report_id=rep_id,
            response_text=f"Successfully answered question: {formatted_response[:100]}...",
            duration=duration,
            request_timestamp=request_start
        )
        
    except Exception as e:
        log_error(e, "Error processing Ask Harry submission")
        
        # Log error interaction
        duration = (datetime.utcnow() - request_start).total_seconds()
        log_modal_interaction(
            user_id=user_id,
            channel_id=channel_id or "unknown",
            thread_id=thread_ts or "",
            modal_type="Ask Harry",
            user_input=question,
            report_id=rep_id,
            response_text=f"Error processing question: {str(e)}",
            duration=duration,
            request_timestamp=request_start
        )
        
        # Try to send error message if possible
        try:
            slack.send_message(
                text=f"Error processing your question: {str(e)}",
                thread_ts=thread_ts,
                channel=body["user"]["team_id"]
            )
        except:
            pass  # If this fails too, just log the error
