"""Data models for Toss Securities community crawler."""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class CommunityPost:
    """Represents a single community post."""
    opinion_text: str
    post_id: str = ""               # API comment id
    post_date: str = ""             # raw date string from DOM
    post_date_parsed: str = ""      # parsed ISO date string
    like_count: int = 0
    comment_count: int = 0
    author: str = ""
    stock_code: str = ""
    stock_name: str = ""
    scraped_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
