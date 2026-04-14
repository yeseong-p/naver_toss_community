"""Async pollers for Naver and Toss discussion boards.

Both pollers keep a persistent client/browser, run on a timer,
diff against already-seen post IDs in SQLite, and publish new
posts to the event bus.
"""
import asyncio
import random
import re
import ssl
from datetime import datetime

import aiohttp
from bs4 import BeautifulSoup

from src import config, storage
from src.events import bus, health
from src.crawler.naver import config as naver_cfg
from src.crawler.naver.utils import parse_date as parse_naver_date


# ── Naver poller ──────────────────────────────────────────
class NaverPoller:
    """Lightweight Naver poller: fetches first page list, diffs, pulls content for new."""

    def __init__(self, etfs: list[dict]):
        self.etfs = etfs
        self._seen: dict[str, set[str]] = {e["code"]: set() for e in etfs}
        self._session: aiohttp.ClientSession | None = None

    async def start(self):
        for e in self.etfs:
            self._seen[e["code"]] = storage.existing_post_ids("네이버", e["code"])
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE
        connector = aiohttp.TCPConnector(ssl=ssl_ctx)
        self._session = aiohttp.ClientSession(
            headers=naver_cfg.HEADERS, connector=connector,
        )
        while True:
            try:
                await self._poll_cycle()
                health["naver"].update({
                    "last_ok": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "consecutive_errors": 0,
                })
            except Exception as e:
                health["naver"]["last_error"] = f"{type(e).__name__}: {e}"
                health["naver"]["consecutive_errors"] += 1
                print(f"[Naver] poll error: {e}")
            await asyncio.sleep(config.NAVER_POLL_INTERVAL)

    async def stop(self):
        if self._session:
            await self._session.close()

    async def _poll_cycle(self):
        for etf in self.etfs:
            await self._poll_one(etf)
            await asyncio.sleep(random.uniform(naver_cfg.DELAY_MIN, naver_cfg.DELAY_MAX))

    async def _poll_one(self, etf: dict):
        code = etf["code"]
        name = etf["name"]
        new_items: list[dict] = []
        for page in range(1, config.NAVER_PAGES_PER_POLL + 1):
            items = await self._get_list(code, page)
            for item in items:
                if item["nid"] in self._seen[code]:
                    continue
                new_items.append(item)

        if not new_items:
            return

        # Fetch content for new posts in small batches
        batch = naver_cfg.CONTENT_BATCH_SIZE
        for i in range(0, len(new_items), batch):
            chunk = new_items[i:i + batch]
            contents = await asyncio.gather(
                *[self._get_content(code, item["nid"]) for item in chunk],
                return_exceptions=True,
            )
            for item, content in zip(chunk, contents):
                if isinstance(content, Exception):
                    content = ""
                await self._save_and_publish(etf, item, content)
            if i + batch < len(new_items):
                await asyncio.sleep(random.uniform(
                    naver_cfg.BATCH_DELAY_MIN, naver_cfg.BATCH_DELAY_MAX,
                ))

    async def _get_list(self, code: str, page: int) -> list[dict]:
        url = f"{naver_cfg.BASE_URL}/item/board.naver?code={code}&page={page}"
        async with self._session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            text = await resp.text(encoding="utf-8")

        soup = BeautifulSoup(text, "html.parser")
        table = soup.select_one("table.type2")
        if not table:
            return []

        posts: list[dict] = []
        for row in table.select("tbody tr"):
            cells = row.select("td")
            if len(cells) < 6:
                continue
            title_td = cells[1]
            a = title_td.select_one("a")
            if not a:
                continue
            href = a.get("href", "")
            if "board_read" not in href:
                continue
            m = re.search(r"nid=(\d+)", href)
            if not m:
                continue
            nid = m.group(1)
            title = a.get("title", a.get_text(strip=True)).strip()
            if len(title) <= 1 or not re.search(r"[a-zA-Z0-9가-힣]", title):
                continue

            comment_count = 0
            span = title_td.select_one("span.tah")
            if span:
                cm = re.search(r"\[(\d+)\]", span.get_text())
                if cm:
                    comment_count = int(cm.group(1))
            date_span = cells[0].select_one("span")
            date_str = date_span.get_text(strip=True) if date_span else ""
            try:
                likes = int(cells[4].get_text(strip=True))
            except (ValueError, IndexError):
                likes = 0
            try:
                dislikes = int(cells[5].get_text(strip=True))
            except (ValueError, IndexError):
                dislikes = 0
            posts.append({
                "nid": nid,
                "title": title,
                "date_str": date_str,
                "likes": likes,
                "dislikes": dislikes,
                "comments": comment_count,
            })
        return posts

    async def _get_content(self, code: str, nid: str) -> str:
        url = f"{naver_cfg.MOBILE_URL}/pc/domestic/stock/{code}/discussion/{nid}"
        try:
            async with self._session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                text = await resp.text(encoding="utf-8")
        except (aiohttp.ClientError, asyncio.TimeoutError):
            return ""
        m = re.search(
            r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
            text, re.DOTALL,
        )
        if not m:
            return ""
        import json
        try:
            data = json.loads(m.group(1))
            queries = data["props"]["pageProps"]["dehydratedState"]["queries"]
            for q in queries:
                key = q.get("queryKey", [{}])
                if (isinstance(key, list) and key
                        and isinstance(key[0], dict)
                        and key[0].get("url") == "/discussion/detail"):
                    html = q["state"]["data"]["result"].get("contentHtml", "")
                    if html:
                        return BeautifulSoup(html, "html.parser").get_text(
                            separator="\n").strip()
        except (KeyError, json.JSONDecodeError, IndexError, TypeError):
            pass
        return ""

    async def _save_and_publish(self, etf: dict, item: dict, content: str):
        post_date = parse_naver_date(item["date_str"])
        record = {
            "source": "네이버",
            "post_id": item["nid"],
            "etf_code": etf["code"],
            "etf_name": etf["name"],
            "title": item["title"],
            "content": content,
            "post_date": post_date.strftime("%Y-%m-%d %H:%M") if post_date else item["date_str"],
            "author": "",
            "likes": item["likes"],
            "dislikes": item["dislikes"],
            "comments": item["comments"],
            "crawled_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        if storage.insert_post(record):
            self._seen[etf["code"]].add(item["nid"])
            await bus.publish({"type": "post", "post": record})


# ── Toss poller (Playwright) ──────────────────────────────
class TossPoller:
    def __init__(self, etfs: list[dict]):
        self.etfs = etfs
        self._seen: dict[str, set[str]] = {e["code"]: set() for e in etfs}
        self._pw = None
        self._browser = None
        self._context = None

    async def start(self):
        from playwright.async_api import async_playwright
        from src.crawler.toss import config as toss_cfg

        for e in self.etfs:
            self._seen[e["code"]] = storage.existing_post_ids("토스증권", e["code"])

        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=toss_cfg.HEADLESS)
        self._context = await self._browser.new_context(
            viewport={"width": toss_cfg.VIEWPORT_WIDTH, "height": toss_cfg.VIEWPORT_HEIGHT},
            locale="ko-KR",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
        )

        while True:
            try:
                await self._poll_cycle()
                health["toss"].update({
                    "last_ok": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "consecutive_errors": 0,
                })
            except Exception as e:
                health["toss"]["last_error"] = f"{type(e).__name__}: {e}"
                health["toss"]["consecutive_errors"] += 1
                print(f"[Toss] poll error: {e}")
            await asyncio.sleep(config.TOSS_POLL_INTERVAL)

    async def stop(self):
        try:
            if self._context:
                await self._context.close()
            if self._browser:
                await self._browser.close()
            if self._pw:
                await self._pw.stop()
        except Exception:
            pass

    async def _poll_cycle(self):
        from src.crawler.toss import config as toss_cfg
        for etf in self.etfs:
            await self._poll_one(etf)
            await asyncio.sleep(random.uniform(
                toss_cfg.ETF_DELAY_MIN, toss_cfg.ETF_DELAY_MAX,
            ))

    async def _poll_one(self, etf: dict):
        from src.crawler.toss.scraper import TossCommunityScraper
        code = etf["code"]
        name = etf["name"]
        toss_code = f"A{code}" if code.isdigit() else code

        page = await self._context.new_page()
        scraper = TossCommunityScraper()
        # Override MAX_POSTS for poll — only look at latest N
        from src.crawler.toss import config as toss_cfg
        original_max = toss_cfg.MAX_POSTS
        toss_cfg.MAX_POSTS = config.TOSS_MAX_POSTS_PER_POLL
        try:
            posts = await scraper.scrape_page(page, stock_code=toss_code, stock_name=name)
        finally:
            toss_cfg.MAX_POSTS = original_max
            await page.close()

        for p in posts:
            if p.post_id in self._seen[code]:
                continue
            record = {
                "source": "토스증권",
                "post_id": p.post_id,
                "etf_code": code,
                "etf_name": name,
                "title": "",
                "content": p.opinion_text,
                "post_date": p.post_date_parsed or p.post_date,
                "author": p.author,
                "likes": p.like_count,
                "dislikes": 0,
                "comments": p.comment_count,
                "crawled_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            if storage.insert_post(record):
                self._seen[code].add(p.post_id)
                await bus.publish({"type": "post", "post": record})
