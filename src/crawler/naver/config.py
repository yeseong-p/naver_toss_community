"""Configuration for Naver stock discussion board crawler."""

# URLs
BASE_URL = "https://finance.naver.com"
MOBILE_URL = "https://m.stock.naver.com"

# HTTP Headers
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# Crawling limits
MAX_POSTS_PER_ETF = 200      # 안전 상한 (기간 기반 크롤링 시에도 적용)
CRAWL_DAYS_BACK = 30          # start_date 미지정 시 기본값

# Request delay (seconds)
DELAY_MIN = 0.2
DELAY_MAX = 0.632

# Async batch settings
CONTENT_BATCH_SIZE = 3      # 동시 본문 요청 수
BATCH_DELAY_MIN = 0.5       # 배치 간 딜레이
BATCH_DELAY_MAX = 1.0
