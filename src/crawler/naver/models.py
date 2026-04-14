"""Data models for Naver stock discussion board crawler."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class NaverPost:
    """Represents a single Naver discussion board post."""
    title: str = ""
    content: str = ""
    date_str: str = ""
    post_date: Optional[datetime] = None
    nid: str = ""
    likes: int = 0
    dislikes: int = 0
    comment_count: int = 0
    stock_code: str = ""
    stock_name: str = ""
    interest_etf: int = 0
    invest_country: str = ""
    category_large: str = ""
    category_medium: str = ""
    category_small: str = ""
    scraped_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    def to_dict(self) -> dict:
        """board_crawl 출력 컬럼명과 일치하는 dict 반환."""
        return {
            "ETF종목코드": self.stock_code,
            "ETF명": self.stock_name,
            "관심ETF여부": self.interest_etf,
            "게시물ID": self.nid,
            "제목": self.title,
            "게시날짜": self.date_str,
            "내용": self.content,
            "추천수": self.likes,
            "비추천수": self.dislikes,
            "댓글수": self.comment_count,
            "출처": "네이버",
            "투자국가": self.invest_country,
            "대분류": self.category_large,
            "중분류": self.category_medium,
            "소분류": self.category_small,
        }
