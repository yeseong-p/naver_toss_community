"""Naver stock discussion board scraper.

Crawls the Naver finance discussion board (종목토론방) for ETF posts.
- PC page: parses post list from table.type2
- Mobile page: extracts post content from __NEXT_DATA__ JSON
"""

import asyncio
import json
import re
import random
import ssl

import aiohttp
from bs4 import BeautifulSoup

from . import config
from .models import NaverPost
from .utils import parse_date

from datetime import datetime, timedelta


class NaverCrawler:
    """Crawls Naver stock discussion board posts for a given ETF (async)."""

    def __init__(self, start_date: str | None = None, end_date: str | None = None):
        self._session: aiohttp.ClientSession | None = None

        # start_date가 있으면 해당 날짜까지 크롤링, 없으면 CRAWL_DAYS_BACK 기본값
        if start_date:
            self._cutoff = datetime.strptime(start_date, "%Y-%m-%d")
        else:
            self._cutoff = datetime.now() - timedelta(days=config.CRAWL_DAYS_BACK)

        # end_date 이후 게시물 건너뜀 (end_date 당일 포함 → +1일)
        self._end_date: datetime | None = None
        if end_date:
            self._end_date = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)

        self._ssl_ctx = ssl.create_default_context()
        self._ssl_ctx.check_hostname = False
        self._ssl_ctx.verify_mode = ssl.CERT_NONE

    async def __aenter__(self):
        connector = aiohttp.TCPConnector(ssl=self._ssl_ctx)
        self._session = aiohttp.ClientSession(
            headers=config.HEADERS,
            connector=connector,
        )
        return self

    async def __aexit__(self, *exc):
        if self._session:
            await self._session.close()

    @staticmethod
    def _is_irrelevant_title(title: str) -> bool:
        """제목이 무의미한지 판단 (1글자 이하, 알파벳/숫자/한글 없음)."""
        stripped = title.strip()
        if len(stripped) <= 1:
            return True
        if not re.search(r'[a-zA-Z0-9가-힣]', stripped):
            return True
        return False

    async def _get_post_list(self, code: str, page: int) -> list[dict]:
        """종목코드의 게시판 목록 페이지에서 게시물 목록을 파싱."""
        url = f"{config.BASE_URL}/item/board.naver?code={code}&page={page}"
        async with self._session.get(url) as resp:
            text = await resp.text(encoding="utf-8")

        soup = BeautifulSoup(text, "html.parser")

        table = soup.select_one("table.type2")
        if not table:
            return []

        posts = []
        rows = table.select("tbody tr")
        for row in rows:
            cells = row.select("td")
            if len(cells) < 6:
                continue

            # 제목 링크 확인
            title_td = cells[1]
            title_tag = title_td.select_one("a")
            if not title_tag:
                continue

            title = title_tag.get("title", title_tag.get_text(strip=True))
            href = title_tag.get("href", "")
            if "board_read" not in href:
                continue

            # nid 추출
            nid_match = re.search(r"nid=(\d+)", href)
            if not nid_match:
                continue
            nid = nid_match.group(1)

            # 무의미한 제목 스킵
            if self._is_irrelevant_title(title):
                continue

            # 댓글 수: 제목 옆 span.tah.p9에서 [n] 형태로 추출
            comment_count = 0
            comment_span = title_td.select_one("span.tah")
            if comment_span:
                cm = re.search(r"\[(\d+)\]", comment_span.get_text())
                if cm:
                    comment_count = int(cm.group(1))

            # 날짜
            date_span = cells[0].select_one("span")
            date_str = date_span.get_text(strip=True) if date_span else ""
            post_date = parse_date(date_str)

            # end_date 이후 → 건너뜀 (최신순이므로 이후 게시물이 범위 안에 있을 수 있음)
            if self._end_date and post_date and post_date >= self._end_date:
                continue

            # start_date 이전 → 중단 (최신순 정렬이므로 이후는 더 오래됨)
            if post_date and post_date < self._cutoff:
                return posts

            # 추천/비추천
            try:
                likes = int(cells[4].get_text(strip=True))
            except (ValueError, IndexError):
                likes = 0
            try:
                dislikes = int(cells[5].get_text(strip=True))
            except (ValueError, IndexError):
                dislikes = 0

            posts.append({
                "title": title,
                "href": href,
                "nid": nid,
                "date_str": date_str,
                "post_date": post_date,
                "likes": likes,
                "dislikes": dislikes,
                "comment_count": comment_count,
            })

        return posts

    async def _get_post_content(self, code: str, nid: str) -> str:
        """모바일 페이지의 __NEXT_DATA__에서 게시물 본문을 추출."""
        url = f"{config.MOBILE_URL}/pc/domestic/stock/{code}/discussion/{nid}"
        try:
            async with self._session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                text = await resp.text(encoding="utf-8")
        except (aiohttp.ClientError, asyncio.TimeoutError):
            return ""

        # __NEXT_DATA__ JSON 추출
        match = re.search(
            r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
            text,
            re.DOTALL,
        )
        if not match:
            return ""

        try:
            data = json.loads(match.group(1))
            queries = data["props"]["pageProps"]["dehydratedState"]["queries"]
            for q in queries:
                key = q.get("queryKey", [{}])
                if (
                    isinstance(key, list)
                    and len(key) > 0
                    and isinstance(key[0], dict)
                    and key[0].get("url") == "/discussion/detail"
                ):
                    result = q["state"]["data"]["result"]
                    # contentHtml에서 텍스트 추출
                    content_html = result.get("contentHtml", "")
                    if content_html:
                        soup = BeautifulSoup(content_html, "html.parser")
                        return soup.get_text(separator="\n").strip()
        except (KeyError, json.JSONDecodeError, IndexError, TypeError):
            pass

        return ""

    async def crawl_etf(
        self, code: str, name: str, interest_etf: int,
        invest_country: str = "", category_large: str = "",
        category_medium: str = "", category_small: str = "",
    ) -> list[NaverPost]:
        """한 ETF의 종토방에서 최대 MAX_POSTS_PER_ETF개 게시물 수집 (배치 병렬 본문 요청)."""
        print(f"  [네이버] 크롤링 중: [{code}] {name}")
        collected_posts: list[NaverPost] = []
        pending_items: list[dict] = []
        page = 1

        # 목록 페이지에서 후보 수집
        while len(pending_items) < config.MAX_POSTS_PER_ETF:
            post_list = await self._get_post_list(code, page)
            if not post_list:
                break

            for post in post_list:
                if len(pending_items) >= config.MAX_POSTS_PER_ETF:
                    break
                pending_items.append(post)

            page += 1
            await asyncio.sleep(random.uniform(config.DELAY_MIN, config.DELAY_MAX))

        # 배치 병렬 본문 요청
        batch_size = config.CONTENT_BATCH_SIZE
        for i in range(0, len(pending_items), batch_size):
            batch = pending_items[i:i + batch_size]

            # 배치 내 동시 요청
            contents = await asyncio.gather(
                *[self._get_post_content(code, item["nid"]) for item in batch]
            )

            for item, content in zip(batch, contents):
                naver_post = NaverPost(
                    title=item["title"],
                    content=content,
                    date_str=item["date_str"],
                    post_date=item["post_date"],
                    nid=item["nid"],
                    likes=item["likes"],
                    dislikes=item["dislikes"],
                    comment_count=item["comment_count"],
                    stock_code=code,
                    stock_name=name,
                    interest_etf=interest_etf,
                    invest_country=invest_country,
                    category_large=category_large,
                    category_medium=category_medium,
                    category_small=category_small,
                )
                collected_posts.append(naver_post)

                print(f"    [{len(collected_posts)}/{len(pending_items)}] {item['title'][:40]}".encode('cp949', errors='replace').decode('cp949'))

            # 배치 간 딜레이
            if i + batch_size < len(pending_items):
                await asyncio.sleep(random.uniform(config.BATCH_DELAY_MIN, config.BATCH_DELAY_MAX))

        print(f"  → [네이버] {name}: {len(collected_posts)}개 수집 완료")
        return collected_posts


if __name__ == "__main__":
    # 독립 실행: 첫 번째 ETF만 크롤링하여 테스트
    import pandas as pd
    import os

    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(script_dir))
    etf_input_dir = os.path.join(project_root, "ETF_list_input")
    # ETF_list_input 디렉토리의 첫 번째 .xlsx 파일 사용
    xlsx_files = [f for f in os.listdir(etf_input_dir) if f.endswith(".xlsx")] if os.path.isdir(etf_input_dir) else []
    etf_path = os.path.join(etf_input_dir, xlsx_files[0]) if xlsx_files else ""

    if os.path.exists(etf_path):
        df = pd.read_excel(etf_path, dtype={"종목코드": str})
        df.columns = [c.strip() for c in df.columns]
        df["종목코드"] = df["종목코드"].str.strip().str.zfill(6)

        row = df.iloc[0]
        code = str(row["종목코드"])
        name = str(row["종목명"])
        interest_etf = int(row.get("관심ETF여부", row.get("당사ETF여부", row.iloc[2])))

        async def _test():
            async with NaverCrawler() as crawler:
                posts = await crawler.crawl_etf(code, name, interest_etf)
                print(f"\n총 {len(posts)}개 수집")
                for i, p in enumerate(posts[:3]):
                    print(f"  [{i+1}] {p.title[:50]} | {p.date_str} | 추천:{p.likes}")
                    print(f"       내용: {p.content[:80]}...")

        asyncio.run(_test())
    else:
        print(f"ETF_list.xlsx not found at {etf_path}")
