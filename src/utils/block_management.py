"""
Block management utilities for Slack messages.
Handles block counting and chunking to prevent exceeding Slack's 50-block limit.
"""

from typing import List, Dict, Any, Tuple
from ..utils.logging import log_info, log_warning


class BlockManager:
    """Manages Slack blocks to prevent exceeding the 50-block limit."""
    
    MAX_BLOCKS_PER_MESSAGE = 50
    SAFETY_MARGIN = 5  # Reserve blocks for action buttons and dividers
    SAFE_BLOCK_LIMIT = MAX_BLOCKS_PER_MESSAGE - SAFETY_MARGIN
    
    @staticmethod
    def count_blocks(blocks: List[Dict[str, Any]]) -> int:
        """
        Count the number of blocks in a list.
        
        Args:
            blocks: List of Slack block dictionaries
            
        Returns:
            Number of blocks
        """
        return len(blocks)
    
    @staticmethod
    def is_safe_to_add(current_blocks: List[Dict[str, Any]], new_blocks: List[Dict[str, Any]]) -> bool:
        """
        Check if it's safe to add new blocks without exceeding the limit.
        
        Args:
            current_blocks: Current list of blocks
            new_blocks: New blocks to add
            
        Returns:
            True if safe to add, False otherwise
        """
        total_count = BlockManager.count_blocks(current_blocks) + BlockManager.count_blocks(new_blocks)
        return total_count <= BlockManager.SAFE_BLOCK_LIMIT
    
    @staticmethod
    def chunk_blocks(blocks: List[Dict[str, Any]], include_action_buttons: bool = True) -> List[List[Dict[str, Any]]]:
        """
        Split blocks into chunks that don't exceed the Slack limit.
        
        Args:
            blocks: List of blocks to chunk
            include_action_buttons: Whether to reserve space for action buttons
            
        Returns:
            List of block chunks
        """
        if not blocks:
            return []
        
        chunks = []
        current_chunk = []
        
        # Determine the limit based on whether we need action buttons
        limit = BlockManager.SAFE_BLOCK_LIMIT if include_action_buttons else BlockManager.MAX_BLOCKS_PER_MESSAGE
        
        for block in blocks:
            # Check if adding this block would exceed the limit
            if len(current_chunk) >= limit:
                # Start a new chunk
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = [block]
            else:
                current_chunk.append(block)
        
        # Add the last chunk if it has content
        if current_chunk:
            chunks.append(current_chunk)
        
        log_info(f"Split {len(blocks)} blocks into {len(chunks)} chunks")
        return chunks
    
    @staticmethod
    def validate_blocks(blocks: List[Dict[str, Any]], context: str = "") -> bool:
        """
        Validate that blocks don't exceed Slack limits.
        
        Args:
            blocks: List of blocks to validate
            context: Context string for logging
            
        Returns:
            True if valid, False if exceeds limits
        """
        block_count = BlockManager.count_blocks(blocks)
        
        if block_count > BlockManager.MAX_BLOCKS_PER_MESSAGE:
            log_warning(f"Block count ({block_count}) exceeds Slack limit ({BlockManager.MAX_BLOCKS_PER_MESSAGE}) {context}")
            return False
        elif block_count > BlockManager.SAFE_BLOCK_LIMIT:
            log_warning(f"Block count ({block_count}) exceeds safe limit ({BlockManager.SAFE_BLOCK_LIMIT}) {context}")
        
        return True
    
    @staticmethod
    def create_continuation_header(chunk_num: int, total_chunks: int, title: str) -> Dict[str, Any]:
        """
        Create a header block for continuation messages.
        
        Args:
            chunk_num: Current chunk number (1-based)
            total_chunks: Total number of chunks
            title: Base title for the message
            
        Returns:
            Header block dictionary
        """
        if total_chunks > 1:
            continuation_title = f"{title} (Part {chunk_num}/{total_chunks})"
        else:
            continuation_title = title
            
        return {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": continuation_title,
                "emoji": True
            }
        }
    
    @staticmethod
    def optimize_text_blocks(text: str, max_chars: int = 2500) -> List[Dict[str, Any]]:
        """
        Create optimized section blocks for long text with conservative character limits.
        
        Args:
            text: The text to include in the section(s)
            max_chars: Maximum characters per block (reduced from 2900 to be more conservative)
            
        Returns:
            List of section block dictionaries
        """
        blocks = []
        
        # If text is under the limit, just return a single block
        if len(text) <= max_chars:
            return [{
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": text
                }
            }]
        
        # Process the text in chunks, respecting word boundaries
        remaining_text = text
        while remaining_text:
            if len(remaining_text) <= max_chars:
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": remaining_text
                    }
                })
                break
                
            # Find the last space within the max_chars limit
            split_point = remaining_text[:max_chars].rfind(' ')
            
            # If no space found (very long word), split at max_chars
            if split_point == -1:
                split_point = max_chars
                
            # Create a block with the chunk
            chunk = remaining_text[:split_point]
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": chunk
                }
            })
            
            # Remove the processed chunk (and the space)
            remaining_text = remaining_text[split_point:].lstrip()
        
        return blocks
    
    @staticmethod
    def create_attachment_summary_block(attachments: List[Dict[str, Any]], processed_count: int) -> Dict[str, Any]:
        """
        Create a summary block for attachment processing.
        
        Args:
            attachments: List of all attachments
            processed_count: Number of attachments processed so far
            
        Returns:
            Summary block dictionary
        """
        total_count = len(attachments)
        remaining_count = total_count - processed_count
        
        if remaining_count > 0:
            summary_text = (
                f"*Attachment Analysis Summary:*\n"
                f"• Processed: {processed_count}/{total_count} attachments\n"
                f"• Remaining: {remaining_count} attachments (use attachment analysis again to continue)"
            )
        else:
            summary_text = f"*Attachment Analysis Complete:* {processed_count}/{total_count} attachments processed"
        
        return {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": summary_text
            }
        }
