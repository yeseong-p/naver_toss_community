"""Dashboard configuration."""
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
DB_PATH = os.path.join(DATA_DIR, "posts.db")
ETF_LIST_PATH = os.path.join(PROJECT_ROOT, "ETF_list.csv")

# Polling intervals (seconds)
NAVER_POLL_INTERVAL = 30
TOSS_POLL_INTERVAL = 180

# Polling scope
NAVER_PAGES_PER_POLL = 1      # first page only (latest ~20 posts)
TOSS_MAX_POSTS_PER_POLL = 40  # cap per poll cycle

# SSE
SSE_KEEPALIVE_SECONDS = 15
SSE_QUEUE_MAXSIZE = 500

# Server
HOST = "0.0.0.0"
PORT = 8765
