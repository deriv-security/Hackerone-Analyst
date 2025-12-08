"""
Mermaid diagram utility module.
Handles generation and rendering of Mermaid diagrams.
"""

import json
import zlib
import base64
from typing import Dict, Any, Optional
from ..utils.logging import log_error

class MermaidGenerator:
    """Utility class for generating and rendering Mermaid diagrams."""
    
    @staticmethod
    def generate_url(mermaid_code: str, theme: str = "default") -> str:
        """
        Generate a mermaid.live URL from mermaid code.
        
        Args:
            mermaid_code: The Mermaid diagram code
            theme: Optional theme name (default/dark/neutral)
            
        Returns:
            str: URL that can be used to view the diagram
        """
        if not mermaid_code:
            return ""
            
        try:
            # Remove 'mermaid' from the beginning if it exists
            if mermaid_code.startswith('mermaid\n'):
                mermaid_code = mermaid_code[8:]
            
            # Create JSON object with code and configuration
            data = {
                "code": mermaid_code,
                "mermaid": {
                    "theme": theme
                }
            }
            
            # Convert to JSON string
            json_str = json.dumps(data)
            
            # Compress using zlib
            compressed = zlib.compress(json_str.encode('utf-8'))
            
            # Convert to URL-safe base64 and remove padding
            encoded = base64.urlsafe_b64encode(compressed).decode('utf-8').rstrip('=')
            
            # Create the URL with pako format (view mode)
            from ..config import get_mermaid_live_base_url
            url = f"{get_mermaid_live_base_url()}{encoded}"
            
            return url
            
        except Exception as e:
            log_error(e, "Error generating Mermaid URL")
            return ""
    
    @staticmethod
    def create_slack_blocks(
        mermaid_code: str,
        title: str,
        description: Optional[str] = None,
        footer: Optional[str] = None,
        theme: Optional[str] = None
    ) -> list:
        """
        Create Slack blocks for displaying a Mermaid diagram.
        
        Args:
            mermaid_code: The Mermaid diagram code
            title: Title for the diagram
            description: Optional description of the diagram
            footer: Optional footer text
            theme: Optional theme for the diagram
            
        Returns:
            list: List of Slack blocks
        """
        if not mermaid_code and not title:
            return []
            
        # Generate URL for the diagram
        url = MermaidGenerator.generate_url(mermaid_code, theme or "default")
        
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": title or "Mermaid Diagram",
                    "emoji": True
                }
            }
        ]
        
        # Add description if provided
        if description:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": description
                }
            })
        
        # Add image block with fallback to link if URL is invalid
        if url:
            # For now, use a link instead of image to avoid Slack download issues
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"🔗 *View Diagram:* <{url}|Open Mermaid Diagram>"
                }
            })
        
        # Add mermaid code
        if mermaid_code:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"```{mermaid_code}```"
                }
            })
        
        # Add footer if provided
        if footer:
            blocks.append({
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": footer
                    }
                ]
            })
        
        return blocks
    
    @staticmethod
    def extract_mermaid_code(text: str) -> Optional[str]:
        """
        Extract Mermaid code from text that might contain other content.
        
        Args:
            text: Text that might contain Mermaid code
            
        Returns:
            str: Extracted Mermaid code, or None if no code found
        """
        if not text:
            return None
            
        import re
        
        # Try to find Mermaid code block (case insensitive)
        # Find all complete mermaid blocks (must have both opening and closing backticks)
        matches = list(re.finditer(
            r'```\s*mermaid\s*\n([\s\S]*?)```',
            text,
            re.DOTALL | re.IGNORECASE
        ))
        
        if matches:
            # Find the first match that contains a valid diagram type and is properly closed
            for match in matches:
                match_content = match.group(1)
                if re.search(r'(graph|sequenceDiagram|flowchart|classDiagram|stateDiagram|erDiagram|gantt|pie|journey)', match_content, re.IGNORECASE):
                    code = match_content.strip()
                    if not code.startswith('mermaid'):
                        code = 'mermaid\n' + code
                    return code
        
        # If no explicit mermaid blocks found, try to find blocks that start with diagram types
        match = re.search(
            r'```\s*(graph|sequenceDiagram|flowchart|classDiagram|stateDiagram|erDiagram|gantt|pie|journey)[\s\S]*?```',
            text,
            re.DOTALL | re.IGNORECASE
        )
        
        if match:
            # Extract the code and clean it up
            code = match.group(0).strip('`').strip()
            if not code.startswith('mermaid'):
                code = 'mermaid\n' + code
            return code
        
        return None
