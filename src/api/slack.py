"""
Slack API module.
Handles Slack bot setup and message formatting.
"""

from typing import Dict, Any, List, Optional
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from ..config import get_slack_tokens
from ..utils.logging import log_error

class SlackAPI:
    """Client for interacting with the Slack API."""
    
    def __init__(self):
        """Initialize the Slack API client."""
        bot_token, app_token = get_slack_tokens()
        self.app = App(token=bot_token)
        self.handler = SocketModeHandler(self.app, app_token)
        
        # Store message threads for replies
        self.message_threads = {}
        
        # Cache for bot user ID
        self.bot_user_id = None
    
    def start(self) -> None:
        """Start the Slack bot."""
        self.handler.start()
    
    def store_thread(self, report_id: str, thread_ts: str, channel_id: Optional[str] = None) -> None:
        """
        Store a message thread timestamp and channel for a report.
        
        Args:
            report_id: The report ID
            thread_ts: The thread timestamp
            channel_id: Optional channel ID
        """
        if channel_id:
            self.message_threads[str(report_id)] = {"thread_ts": thread_ts, "channel_id": channel_id}
        else:
            # For backward compatibility
            self.message_threads[str(report_id)] = thread_ts
    
    def get_thread(self, report_id: str) -> Optional[str]:
        """
        Get the thread timestamp for a report.
        
        Args:
            report_id: The report ID
            
        Returns:
            The thread timestamp if found, None otherwise
        """
        thread_info = self.message_threads.get(str(report_id))
        if isinstance(thread_info, dict):
            return thread_info.get("thread_ts")
        return thread_info
    
    def get_channel(self, report_id: str) -> Optional[str]:
        """
        Get the channel ID for a report.
        
        Args:
            report_id: The report ID
            
        Returns:
            The channel ID if found, None otherwise
        """
        thread_info = self.message_threads.get(str(report_id))
        if isinstance(thread_info, dict):
            return thread_info.get("channel_id")
        return None
    
    def create_blocks(self, *blocks: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Create a list of Slack blocks.
        
        Args:
            *blocks: Variable number of block dictionaries
            
        Returns:
            List of block dictionaries
        """
        return list(blocks)
    
    def create_header_block(self, text: str) -> Dict[str, Any]:
        """
        Create a header block.
        
        Args:
            text: The header text
            
        Returns:
            Header block dictionary
        """
        return {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": text,
                "emoji": True
            }
        }
    
    def create_section_block(
        self,
        text: str,
        fields: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        """
        Create a section block.
        
        Args:
            text: The section text
            fields: Optional list of field dictionaries
            
        Returns:
            Section block dictionary
        """
        block = {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": text
            }
        }
        
        if fields:
            block["fields"] = fields
        
        return block
    
    def create_section_blocks_for_long_text(
        self,
        text: str,
        max_chars: int = 2500
    ) -> List[Dict[str, Any]]:
        """
        Create multiple section blocks for text that might exceed Slack's character limit.
        Splits text on word boundaries to avoid cutting words in half.
        Uses conservative character limits to prevent block overflow.
        
        Args:
            text: The text to include in the section(s)
            max_chars: Maximum characters per block (reduced from 2900 to be more conservative)
            
        Returns:
            List of section block dictionaries
        """
        from ..utils.block_management import BlockManager
        return BlockManager.optimize_text_blocks(text, max_chars)
    
    def create_divider_block(self) -> Dict[str, Any]:
        """
        Create a divider block.
        
        Returns:
            Divider block dictionary
        """
        return {"type": "divider"}
    
    def create_button_block(
        self,
        text: str,
        action_id: str,
        value: str,
        style: Optional[str] = None,
        confirm: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create a button element.
        
        Args:
            text: Button text
            action_id: Button action ID
            value: Button value
            style: Optional button style (primary/danger)
            confirm: Optional confirmation dialog
            
        Returns:
            Button element dictionary
        """
        button = {
            "type": "button",
            "text": {
                "type": "plain_text",
                "text": text,
                "emoji": True
            },
            "value": value,
            "action_id": action_id
        }
        
        if style:
            button["style"] = style
        
        if confirm:
            button["confirm"] = confirm
        
        return button
    
    def create_context_block(self, elements: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Create a context block.
        
        Args:
            elements: List of context elements
            
        Returns:
            Context block dictionary
        """
        return {
            "type": "context",
            "elements": elements
        }
    
    def create_image_block(
        self,
        image_url: str,
        alt_text: str,
        title: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create an image block.
        
        Args:
            image_url: URL of the image
            alt_text: Alternative text for the image
            title: Optional image title
            
        Returns:
            Image block dictionary
        """
        block = {
            "type": "image",
            "image_url": image_url,
            "alt_text": alt_text
        }
        
        if title:
            block["title"] = {
                "type": "plain_text",
                "text": title,
                "emoji": True
            }
        
        return block
    
    def create_action_button(
        self,
        text: str,
        action_id: str,
        value: str,
        style: Optional[str] = None,
        confirm: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create a standard button with consistent styling and behavior.
        
        Args:
            text: Button text
            action_id: Button action ID
            value: Button value
            style: Optional button style (primary/danger)
            confirm: Optional confirmation dialog
            
        Returns:
            Button element dictionary
        """
        button = {
            "type": "button",
            "text": {
                "type": "plain_text",
                "text": text,
                "emoji": True
            },
            "value": value,
            "action_id": action_id
        }
        
        if style:
            button["style"] = style
            
        if confirm:
            button["confirm"] = confirm
            
        return button
    
    def get_standard_buttons(self, report_id: str) -> List[Dict[str, Any]]:
        """
        Get the standard set of action buttons for a report.
        
        Args:
            report_id: The report ID
            
        Returns:
            List of button elements
        """
        # Create standard buttons in specified order
        buttons = [
            self.create_action_button(
                text="Full Report",
                style="primary",
                action_id="full_report",
                value=f"full_report_{report_id}"
            ),
            self.create_action_button(
                text=":eraser: Eraser",
                style="primary",
                action_id="generate_eraser_diagram",
                value=f"eraser_diagram_{report_id}"
            ),
            self.create_action_button(
                text=":mermaid-live: Mermaid",
                style="primary",
                action_id="generate_mermaid",
                value=f"mermaid_{report_id}"
            ),
            self.create_action_button(
                text=":mag: Attachments",
                style="primary",
                action_id="analyze_attachments",
                value=f"attachment_analysis_{report_id}"
            ),
            self.create_action_button(
                text=":arrow_right_hook: Follow-ups",
                style="primary",
                action_id="suggest_followup",
                value=f"suggest_followup_{report_id}"
            ),
            self.create_action_button(
                text="Hacker Review",
                style="primary", 
                action_id="analyze_profile",
                value=f"analyze_profile_unknown_{report_id}"
            ),
            self.create_action_button(
                text="Ask Harry",
                style="primary",
                action_id="ask_harry",
                value=f"ask_harry_{report_id}"
            ),
            self.create_action_button(
                text="Update Status",
                style="danger",
                action_id="update_status",
                value=f"update_status_{report_id}"
            )
        ]
        
        return buttons
    
    def create_action_button_block(self, report_id: str) -> Dict[str, Any]:
        """
        Create a complete action button block for a report.
        
        Args:
            report_id: The report ID
            
        Returns:
            Action button block dictionary
        """
        return {
            "type": "actions",
            "elements": self.get_standard_buttons(report_id)
        }
    
    def send_message(
        self,
        text: str,
        channel: Optional[str] = None,
        thread_ts: Optional[str] = None,
        blocks: Optional[List[Dict[str, Any]]] = None
    ) -> None:
        """
        Send a message to Slack with block validation.
        
        Args:
            text: The message text
            channel: Optional channel to send to
            thread_ts: Optional thread timestamp to reply to
            blocks: Optional list of blocks
        """
        try:
            # Validate blocks before sending
            if blocks:
                from ..utils.block_management import BlockManager
                
                # Validate block count
                if not BlockManager.validate_blocks(blocks, f"for message: {text[:50]}..."):
                    # If blocks exceed limit, chunk them
                    chunks = BlockManager.chunk_blocks(blocks, include_action_buttons=False)
                    log_error(None, f"Message blocks exceeded limit, splitting into {len(chunks)} chunks")
                    
                    # Send each chunk as a separate message
                    for i, chunk in enumerate(chunks):
                        chunk_text = text
                        if len(chunks) > 1:
                            chunk_text += f" (Part {i+1}/{len(chunks)})"
                        
                        self._send_single_message(chunk_text, channel, thread_ts, chunk)
                    return
            
            # Send the message normally if blocks are within limits
            self._send_single_message(text, channel, thread_ts, blocks)
            
        except Exception as e:
            log_error(e, "Failed to send Slack message")
    
    def _send_single_message(
        self,
        text: str,
        channel: Optional[str] = None,
        thread_ts: Optional[str] = None,
        blocks: Optional[List[Dict[str, Any]]] = None
    ) -> None:
        """
        Send a single message to Slack without validation.
        
        Args:
            text: The message text
            channel: Optional channel to send to
            thread_ts: Optional thread timestamp to reply to
            blocks: Optional list of blocks
        """
        # Add :h1: emoji prefix to the message text
        prefixed_text = f":h1: {text}"
        message = {"text": prefixed_text}
        
        if channel:
            message["channel"] = channel
        
        if thread_ts:
            message["thread_ts"] = thread_ts
        
        if blocks:
            message["blocks"] = blocks
        
        # Completely disable URL previews and media unfurling
        message["unfurl_links"] = False
        message["unfurl_media"] = False
        
        self.app.client.chat_postMessage(**message)
    
    def update_message(
        self,
        channel: str,
        ts: str,
        text: str,
        blocks: Optional[List[Dict[str, Any]]] = None
    ) -> None:
        """
        Update an existing message.
        
        Args:
            channel: Channel containing the message
            ts: Timestamp of the message to update
            text: New message text
            blocks: Optional new blocks
        """
        try:
            message = {
                "channel": channel,
                "ts": ts,
                "text": text
            }
            
            if blocks:
                message["blocks"] = blocks
            
            self.app.client.chat_update(**message)
            
        except Exception as e:
            log_error(e, "Failed to update Slack message")
            
    def upload_image(
        self,
        file_path: str,
        title: str,
        channel_id: str,
        thread_ts: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Upload an image file to Slack.
        
        Args:
            file_path: Path to the image file
            title: Title for the image
            channel_id: Channel ID to upload to
            thread_ts: Optional thread timestamp
            
        Returns:
            Dict: Response from Slack API
        """
        try:
            # Create parameters dictionary
            params = {
                "file": file_path,
                "title": title,
                "channel": channel_id  # Use 'channel' instead of 'channels' as recommended
            }
            
            # Add thread_ts if provided
            if thread_ts:
                params["thread_ts"] = thread_ts
            
            # Upload the file
            response = self.app.client.files_upload_v2(**params)
            return response
        except Exception as e:
            log_error(e, "Failed to upload image to Slack")
            return {}
    
    def get_channel_name(self, channel_id: str) -> Optional[str]:
        """
        Get channel name from channel ID.
        
        Args:
            channel_id: The Slack channel ID
            
        Returns:
            Channel name without # prefix, or None if not found
        """
        try:
            response = self.app.client.conversations_info(channel=channel_id)
            if response.get("ok"):
                return response["channel"]["name"]
            return None
        except Exception as e:
            log_error(e, f"Failed to get channel name for {channel_id}")
            return None
