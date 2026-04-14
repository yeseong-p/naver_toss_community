# 종토방 실시간 모니터링 대시보드

네이버 금융 종목토론방 + 토스증권 커뮤니티를 **실시간 폴링**하여 5개 ETF의 신규 게시물/코멘트를 웹 대시보드로 모니터링합니다.

## 모니터링 대상 ETF

| 종목코드 | 이름 |
|---------|------|
| 0180V0  | ACE 미국우주테크액티브 |
| 0183J0  | TIGER 미국우주테크 |
| 0167Z0  | KODEX 미국우주항공 |
| 0131V0  | 1Q 미국우주항공테크 |
| 440910  | WON 미국우주항공방산 |

→ 대상을 변경하려면 `ETF_list.csv`를 편집하고 재시작하면 반영됩니다.

## 아키텍처

```
┌─ NaverPoller (30초 주기, aiohttp)       ─┐
│                                           ├─→ SQLite(posts.db) ─→ EventBus
├─ TossPoller  (3분 주기, Playwright)      ─┘                         │
│                                                                     ▼
└─ FastAPI ─ SSE /api/stream ─→ 브라우저 대시보드 (실시간 카드 피드)
```

- **데이터 원본**: `04_종토방_분석` 프로젝트의 크롤러(`NaverCrawler`, `TossCommunityScraper`)를 그대로 재사용.
- **중복 방지**: SQLite `UNIQUE(source, post_id, etf_code)` 제약 + 메모리 내 `seen_ids` 세트.
- **푸시**: Server-Sent Events (단방향, 재연결 자동).

## 설치

```bash
# Windows
setup.bat

# 또는 수동
pip install -r requirements.txt
playwright install chromium
```

## 실행

```bash
run.bat
# 또는
python -m src.server
```

대시보드: http://127.0.0.1:8765

## 설정

`src/config.py`:

| 항목 | 기본값 | 설명 |
|------|--------|------|
| `NAVER_POLL_INTERVAL` | 30초 | 네이버 폴링 주기 |
| `TOSS_POLL_INTERVAL` | 180초 | 토스 폴링 주기 (Playwright 부담 고려) |
| `NAVER_PAGES_PER_POLL` | 1 | 매 폴링마다 읽는 목록 페이지 수 |
| `TOSS_MAX_POSTS_PER_POLL` | 40 | 토스 폴링 1회당 최대 스캔 게시물 |
| `PORT` | 8765 | 서버 포트 |

## API

- `GET /` — 대시보드 UI
- `GET /api/etfs` — 모니터링 중인 ETF 목록
- `GET /api/recent?limit=100&etf_code=&source=` — 최근 게시물
- `GET /api/stats` — ETF별/소스별 집계, 폴러 헬스
- `GET /api/stream` — SSE 실시간 스트림 (event: `post`)

## 프로젝트 구조

```
999_종토방/
├── ETF_list.csv            # 모니터링 대상
├── requirements.txt
├── run.bat / setup.bat
├── README.md
├── data/
│   └── posts.db            # 자동 생성 (SQLite)
└── src/
    ├── config.py           # 설정값
    ├── storage.py          # SQLite CRUD
    ├── events.py           # 인프로세스 pub/sub
    ├── pollers.py          # NaverPoller / TossPoller
    ├── server.py           # FastAPI + SSE
    ├── static/
    │   └── index.html      # 대시보드 UI
    └── crawler/            # 원본 크롤러 복사본
        ├── naver/
        └── toss/
```

## 주의사항

- **레이트 리밋 회피**: 폴링 주기를 너무 짧게(10초 이하) 잡으면 IP 차단 위험이 있습니다.
- **토스 Playwright**: 상시 브라우저를 띄워 둡니다(메모리 ~300MB). 프로세스 종료 시 자동 정리.
- **토스 API 버전**: 현재 v4 기반. Toss가 API를 v5로 올리면 `src/crawler/toss/config.py`의 `API_COMMENTS_PATTERN` 수정 필요. 대시보드의 "토스" 헬스 상태가 계속 "대기 중"이면 이 문제.
- **네이버 HTML 의존**: 사이트 구조가 바뀌면 `table.type2` 파서 수정 필요.
- **DB 초기화**: `data/posts.db`를 삭제하면 빈 상태에서 재시작됩니다.
