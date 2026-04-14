# 종토방 실시간 모니터링

네이버 종목토론방과 토스 커뮤니티에 올라오는 ETF 관련 게시글을 실시간으로 수집하여 웹 대시보드로 보여주는 도구입니다.

## 기능

- 네이버 금융 종목토론방 폴링 (기본 30초 주기)
- 토스 증권 커뮤니티 폴링 (기본 180초 주기)
- SQLite에 수집된 게시글 저장 (`data/posts.db`)
- FastAPI + SSE(Server-Sent Events) 기반 실시간 스트리밍 대시보드
- `ETF_list.csv`에 등록된 종목을 대상으로 일괄 수집

## 요구사항

- Python 3.10 이상
- Windows (배치 스크립트 기준, 다른 OS에서는 명령어 직접 실행)

## 설치

```
setup.bat
```

아래 작업을 수행합니다.

- `requirements.txt` 의존성 설치 (fastapi, uvicorn, aiohttp, beautifulsoup4, playwright)
- Playwright용 Chromium 브라우저 설치

## 실행

```
run.bat
```

또는 직접:

```
python -m src.server
```

기본 접속 주소: <http://localhost:8765>

## 대상 종목 설정

`ETF_list.csv` 파일에 모니터링할 종목 코드와 이름을 추가합니다.

```csv
code,name
0180V0,ACE 미국우주테크액티브
0183J0,TIGER 미국우주테크
```

## 주요 설정

`src/config.py` 에서 폴링 주기, 포트 등을 변경할 수 있습니다.

| 항목 | 기본값 | 설명 |
| --- | --- | --- |
| `NAVER_POLL_INTERVAL` | 30초 | 네이버 폴링 주기 |
| `TOSS_POLL_INTERVAL` | 180초 | 토스 폴링 주기 |
| `NAVER_PAGES_PER_POLL` | 1 | 폴링 시 가져올 페이지 수 |
| `TOSS_MAX_POSTS_PER_POLL` | 40 | 폴링 1회당 최대 게시글 수 |
| `HOST` / `PORT` | `0.0.0.0` / `8765` | 서버 바인딩 주소 |

## API

| 경로 | 설명 |
| --- | --- |
| `GET /` | 대시보드 HTML |
| `GET /api/etfs` | 모니터링 중인 ETF 목록 |
| `GET /api/recent` | 최근 게시글 (`limit`, `etf_code`, `source` 파라미터) |
| `GET /api/stats` | 수집 통계 및 헬스 정보 |
| `GET /api/stream` | SSE 실시간 이벤트 스트림 |

## 프로젝트 구조

```
999_종토방/
├── ETF_list.csv           # 모니터링 대상 ETF 목록
├── requirements.txt
├── setup.bat / run.bat    # Windows 실행 스크립트
├── data/
│   └── posts.db           # SQLite 저장소
└── src/
    ├── config.py          # 설정값
    ├── server.py          # FastAPI 서버 + SSE
    ├── storage.py         # DB 저장/조회
    ├── events.py          # 이벤트 버스
    ├── pollers.py         # 폴링 루프
    ├── crawler/
    │   ├── naver/         # 네이버 종토방 스크래퍼
    │   └── toss/          # 토스 커뮤니티 스크래퍼
    └── static/
        └── index.html     # 대시보드 프론트엔드
```
