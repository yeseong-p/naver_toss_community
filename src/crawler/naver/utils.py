"""Utility functions for Naver date parsing."""

from datetime import datetime
from typing import Optional


def parse_date(date_str: str) -> Optional[datetime]:
    """날짜 문자열을 datetime으로 파싱.

    Supported formats:
    - "2026.01.15 14:30"
    - "2026.01.15"
    """
    date_str = date_str.strip()
    for fmt in ("%Y.%m.%d %H:%M", "%Y.%m.%d"):
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return None
