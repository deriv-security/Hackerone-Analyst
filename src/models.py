"""
Data models and types for Hai.
Defines structured data types used across the application.
"""

from dataclasses import dataclass
from typing import Dict, Any, List, Optional
from datetime import datetime

@dataclass
class HackerProfile:
    """Represents a HackerOne hacker's profile."""
    username: str
    url: str
    reputation: str
    impact: str
    signal: str
    rank: str = 'N/A'
    profile_picture: Optional[str] = None
    joined: Optional[str] = None

@dataclass
class ReportAttachment:
    """Represents a HackerOne report attachment."""
    url: str
    filename: str
    content_type: str
    size: int

@dataclass
class ReportDetails:
    """Represents HackerOne report details."""
    id: str
    title: str
    state: str
    created_at: datetime
    vulnerability_information: str
    reproduction_steps: Optional[str] = None
    proof_of_concept: Optional[str] = None
    reporter_username: Optional[str] = None
    attachments: List[ReportAttachment] = None

    def __post_init__(self):
        """Convert string date to datetime if needed."""
        if isinstance(self.created_at, str):
            self.created_at = datetime.fromisoformat(
                self.created_at.replace('Z', '+00:00')
            )
        self.attachments = self.attachments or []

@dataclass
class AIAnalysis:
    """Represents an AI analysis result."""
    predicted_validity: str
    validity_certainty_score: float
    validity_reasoning: str
    reporter_username: Optional[str] = None
    follow_up_options: List[str] = None

    def __post_init__(self):
        """Initialize empty lists and normalize values."""
        self.follow_up_options = self.follow_up_options or []
        # Remove any % symbol and convert to float
        if isinstance(self.validity_certainty_score, str):
            self.validity_certainty_score = float(
                self.validity_certainty_score.rstrip('%')
            )

@dataclass
class SlackMessage:
    """Represents a formatted Slack message."""
    text: str
    blocks: List[Dict[str, Any]]
    thread_ts: Optional[str] = None
    channel: Optional[str] = None
    unfurl_links: bool = False

@dataclass
class CredibilityScore:
    """Represents a hacker's credibility score calculation."""
    reputation_score: float
    impact_score: float
    signal_score: float
    account_age_modifier: float
    total_score: float = 0.0

    def __post_init__(self):
        """Calculate total score after initialization if not already set."""
        # If total_score is already provided (e.g., from Hai), skip calculation
        if self.total_score == 0.0:
            # Reputation: Scale adjusted for higher ranges (max 4 points)
            reputation_points = min(self.reputation_score / 1000, 4)  # Now 4000 rep gives max points
            
            # Impact: Adjusted for 0-50 range (max 3 points)
            impact_points = 0
            if self.impact_score > 0:
                if self.impact_score < 10:
                    impact_points = 1
                elif self.impact_score < 25:
                    impact_points = 2
                else:
                    impact_points = 3

            # Signal: Adjusted for -10 to +7 range (max 2 points)
            signal_points = 0
            if self.signal_score < -5:
                signal_points = 0
            elif self.signal_score < 0:
                signal_points = 0.5
            elif self.signal_score < 3:
                signal_points = 1
            elif self.signal_score < 5:
                signal_points = 1.5
            else:
                signal_points = 2
            
            # Calculate total score with modifiers
            self.total_score = reputation_points + impact_points + signal_points + self.account_age_modifier
        
        # Always round to 1 decimal place and ensure between 0 and 10
        self.total_score = round(min(max(self.total_score, 0), 10), 1)

    @property
    def formatted_score(self) -> str:
        """Get the formatted total score."""
        return f"{self.total_score:.1f}/10"

    @property
    def visual_score(self) -> str:
        """Get a visual representation of the score using dots."""
        total_dots = 5
        
        # Special case for scores below 2.0
        if self.total_score < 2:
            full_dots = 0
            half_dot = True  # Always show a half dot for scores < 2.0
            empty_dots = total_dots - 1  # One half dot, rest empty
        else:
            # Normal case for scores 2.0 and above
            full_dots = int(self.total_score // 2)  # Integer division
            half_dot = (self.total_score % 2) >= 0.5  # Half dot if remainder >= 0.5
            empty_dots = total_dots - full_dots - (1 if half_dot else 0)
        
        # Ensure we don't exceed 5 dots (for score of 10)
        if full_dots == 5:
            half_dot = False
            empty_dots = 0
        
        # Character representations
        full_dot = "●"    # Full dot character (black circle U+25CF)
        half_dot_char = "◔"  # Quarter-filled dot character (U+25D4)
        empty_dot_char = "○"  # Empty dot character (white circle U+25CB)
        
        return (
            (full_dot * full_dots) +
            (half_dot_char if half_dot else "") +
            (empty_dot_char * empty_dots)
        )
