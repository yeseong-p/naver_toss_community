"""Scrape community posts from Toss Securities.

Strategy: Intercept /api/v3/comments API responses (structured JSON).
"""

import random

from playwright.async_api import async_playwright, Page, Response

from . import config
from .models import CommunityPost
from .utils import parse_iso_datetime


class TossCommunityScraper:
    """Scrapes community posts using API intercept + infinite scroll."""

    def __init__(self, start_date: str | None = None, end_date: str | None = None):
        self.posts: list[CommunityPost] = []
        self.seen_ids: set[str] = set()
        self._api_comments: list[dict] = []  # raw comments from API
        self._stock_code: str = ""
        self._stock_name: str = ""
        self._start_date: str | None = start_date   # "YYYY-MM-DD"
        self._end_date: str | None = end_date       # "YYYY-MM-DD"
        self._reached_start: bool = False            # start_date 이전 게시물 발견 시 True

    def _reset(self):
        """Reset state for a new scrape run."""
        self.posts.clear()
        self.seen_ids.clear()
        self._api_comments.clear()
        self._reached_start = False

    async def scrape_page(
        self,
        page: Page,
        stock_code: str = "",
        stock_name: str = "",
        url: str | None = None,
    ) -> list[CommunityPost]:
        """Scrape a single stock's community using an externally provided page.

        Args:
            page: Playwright page object (caller manages browser lifecycle).
            stock_code: Stock code (e.g. "A457480").
            stock_name: Stock name (e.g. "ACE 테슬라밸류체인액티브").
            url: Community URL. Defaults to config-based URL if not provided.
        """
        self._reset()
        self._stock_code = stock_code or config.STOCK_CODE
        self._stock_name = stock_name

        target_url = url or f"{config.BASE_URL}/stocks/{self._stock_code}/community"

        page.set_default_timeout(config.PAGE_LOAD_TIMEOUT)

        # Set up API response interception
        page.on("response", self._on_response)

        print(f"Navigating to {target_url} ...")
        try:
            await page.goto(target_url, wait_until="domcontentloaded", timeout=config.NAVIGATION_TIMEOUT)
        except Exception as e:
            print(f"Navigation warning: {e}")

        # Wait for SPA content — poll for API data instead of fixed wait
        print("Waiting for content to render...")
        await self._wait_for_api_data(page)

        # Process any comments already captured
        self._process_api_comments()
        print(f"  Initial API capture: {len(self.posts)} posts")

        # Scroll to load more posts
        await self._scroll_for_more(page)

        # Remove listener to avoid interference with next stock
        page.remove_listener("response", self._on_response)

        # If API intercept didn't work, we'd have 0 posts
        if not self.posts:
            print("API intercept yielded no results.")

        return self.posts

    async def _on_response(self, response: Response):
        """Intercept API responses containing comment data."""
        url = response.url
        if config.API_COMMENTS_PATTERN not in url:
            return
        if response.status != 200:
            return
        # STOCK 타입만 처리 (LOUNGE 등 제외)
        if "subjectType=STOCK" not in url:
            return

        try:
            content_type = response.headers.get("content-type", "")
            if "json" not in content_type:
                return
            body = await response.json()
            # v4 API: result.results (v3: result.comments.body)
            comments = body.get("result", {}).get("results", [])
            if comments:
                self._api_comments.extend(comments)
                print(f"  [API] Captured {len(comments)} comments (buffer: {len(self._api_comments)})")
        except Exception as e:
            print(f"  [API] Error reading response: {e}")

    async def _wait_for_api_data(self, page: Page):
        """API 데이터 도착까지 폴링. 최대 SPA_MAX_WAIT_MS 대기."""
        elapsed = 0
        while elapsed < config.SPA_MAX_WAIT_MS:
            if self._api_comments:
                # 데이터 도착 — 짧은 추가 대기 후 진행 (추가 응답 수신 여유)
                await page.wait_for_timeout(config.SPA_POLL_INTERVAL_MS)
                return
            await page.wait_for_timeout(config.SPA_POLL_INTERVAL_MS)
            elapsed += config.SPA_POLL_INTERVAL_MS
        print(f"  SPA 최대 대기 도달 ({config.SPA_MAX_WAIT_MS}ms)")

    def _process_api_comments(self):
        """Convert buffered API comments into CommunityPost objects."""
        for comment in self._api_comments:
            # v4: commentId (v3: id)
            comment_id = str(comment.get("commentId", comment.get("id", "")))
            if not comment_id or comment_id in self.seen_ids:
                continue

            # Skip replies - only top-level posts
            if comment.get("parentId"):
                continue

            # v4: message is an object {"message": "...", "title": "..."}
            msg_data = comment.get("message", "")
            if isinstance(msg_data, dict):
                message = msg_data.get("message", "").strip()
            else:
                message = str(msg_data).strip()
            if not message:
                continue

            # Parse author
            author_data = comment.get("author", {})
            author = author_data.get("nickname", "")

            # Parse date
            updated_at = comment.get("updatedAt", "")
            post_date_parsed = parse_iso_datetime(updated_at) or ""

            # 기간 필터링 (YYYY-MM-DD 문자열 비교)
            if post_date_parsed:
                if self._end_date and post_date_parsed > self._end_date:
                    continue  # end_date 이후 → 건너뜀
                if self._start_date and post_date_parsed < self._start_date:
                    self._reached_start = True
                    continue  # start_date 이전 → 건너뜀

            # v4: counts in statistic object (v3: top-level fields)
            statistic = comment.get("statistic", {})
            like_count = int(statistic.get("likeCount", 0) or 0)
            reply_count = int(statistic.get("replyCount", 0) or 0)

            post = CommunityPost(
                opinion_text=message,
                post_id=comment_id,
                post_date=updated_at,
                post_date_parsed=post_date_parsed,
                like_count=like_count,
                comment_count=reply_count,
                author=author,
                stock_code=self._stock_code,
                stock_name=self._stock_name,
            )

            self.seen_ids.add(comment_id)
            self.posts.append(post)

            if len(self.posts) >= config.MAX_POSTS:
                break

        # Clear processed comments
        self._api_comments.clear()

    async def _scroll_for_more(self, page: Page):
        """Scroll page to trigger more API calls for pagination."""
        empty_scroll_count = 0

        while len(self.posts) < config.MAX_POSTS:
            # start_date 이전 게시물 발견 → 기간 크롤링 완료
            if self._reached_start:
                print("  Start date reached, stopping scroll.")
                break

            prev_count = len(self.posts)

            # Scroll down
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")

            # Random delay
            delay = random.uniform(config.SCROLL_PAUSE_MIN, config.SCROLL_PAUSE_MAX)
            await page.wait_for_timeout(int(delay * 1000))

            # Process newly captured API comments
            self._process_api_comments()

            new_count = len(self.posts) - prev_count
            if new_count == 0:
                empty_scroll_count += 1
                print(f"  No new posts from scroll (attempt {empty_scroll_count}/{config.MAX_EMPTY_SCROLLS})")
                if empty_scroll_count >= config.MAX_EMPTY_SCROLLS:
                    print("  Max empty scrolls reached, stopping.")
                    break
            else:
                empty_scroll_count = 0
                print(f"  +{new_count} posts from scroll (total: {len(self.posts)})")

        # Trim to MAX_POSTS
        self.posts = self.posts[:config.MAX_POSTS]
        print(f"\nTotal posts collected: {len(self.posts)}")
