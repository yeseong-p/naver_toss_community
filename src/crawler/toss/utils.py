"""Utility functions for Toss date parsing."""

from datetime import datetime
from typing import Optional


def parse_iso_datetime(text: str) -> Optional[str]:
    """Parse ISO 8601 datetime string (from API) to readable format.

    Example: "2025-12-17T08:17:52+09:00" -> "2025-12-17 08:17"
    """
    if not text:
        return None
    try:
        # Handle timezone offset format
        dt = datetime.fromisoformat(text)
        return dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        return None
