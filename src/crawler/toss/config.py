"""Configuration for Toss Securities community crawler."""

# Target URL
BASE_URL = "https://www.tossinvest.com"
STOCK_CODE = "A457480"

# API endpoint patterns (for network intercept)
API_COMMENTS_PATTERN = "wts-cert-api.tossinvest.com/api/v4/comments"

# Crawling limits
MAX_POSTS = 200               # 안전 상한 (기간 기반 크롤링 시에도 적용)

# Scroll settings
SCROLL_PAUSE_MIN = 1.5  # seconds
SCROLL_PAUSE_MAX = 3.0  # seconds
MAX_EMPTY_SCROLLS = 5   # stop after N scrolls with no new posts

# ETF 간 딜레이 (초) — rate limit 방지
ETF_DELAY_MIN = 3.0
ETF_DELAY_MAX = 7.0

# Browser settings
HEADLESS = True
VIEWPORT_WIDTH = 1280
VIEWPORT_HEIGHT = 900
PAGE_LOAD_TIMEOUT = 30000  # ms
NAVIGATION_TIMEOUT = 60000  # ms

# Concurrency / SPA polling
ETF_CONCURRENCY = 3         # 동시 브라우저 페이지 수
CONTEXT_ROTATE_EVERY = 50   # N개 ETF마다 브라우저 컨텍스트 재생성 (rate limit 방지)
SPA_POLL_INTERVAL_MS = 500  # API 데이터 폴링 간격
SPA_MAX_WAIT_MS = 6000      # SPA 최대 대기
