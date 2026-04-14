"""FastAPI dashboard server with SSE streaming."""
import asyncio
import csv
import json
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from src import config, storage
from src.events import bus, health
from src.pollers import NaverPoller, TossPoller


def load_etfs() -> list[dict]:
    """Load ETF list from CSV (code,name)."""
    etfs: list[dict] = []
    with open(config.ETF_LIST_PATH, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            code = (row.get("code") or "").strip()
            name = (row.get("name") or "").strip()
            if not code:
                continue
            etfs.append({"code": code, "name": name or code})
    return etfs


@asynccontextmanager
async def lifespan(app: FastAPI):
    storage.init_db()
    etfs = load_etfs()
    app.state.etfs = etfs

    naver = NaverPoller(etfs)
    toss = TossPoller(etfs)
    app.state.naver = naver
    app.state.toss = toss

    task_n = asyncio.create_task(naver.start(), name="naver-poller")
    task_t = asyncio.create_task(toss.start(), name="toss-poller")
    print(f"Dashboard ready → http://{config.HOST}:{config.PORT}")
    try:
        yield
    finally:
        task_n.cancel()
        task_t.cancel()
        await naver.stop()
        await toss.stop()
        for t in (task_n, task_t):
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass


app = FastAPI(title="종토방 실시간 모니터링", lifespan=lifespan)

_static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=_static_dir), name="static")


@app.get("/", response_class=HTMLResponse)
async def index():
    with open(os.path.join(_static_dir, "index.html"), "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())


@app.get("/api/etfs")
async def api_etfs():
    return app.state.etfs


@app.get("/api/recent")
async def api_recent(limit: int = 100, etf_code: str | None = None,
                     source: str | None = None):
    return storage.recent_posts(limit=limit, etf_code=etf_code, source=source)


@app.get("/api/stats")
async def api_stats():
    s = storage.stats()
    s["health"] = health
    s["subscribers"] = bus.subscriber_count
    return s


@app.get("/api/stream")
async def api_stream(request: Request):
    q = await bus.subscribe()

    async def event_gen():
        try:
            yield f"event: hello\ndata: {json.dumps({'ok': True})}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(
                        q.get(), timeout=config.SSE_KEEPALIVE_SECONDS,
                    )
                    yield f"event: {event['type']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            await bus.unsubscribe(q)

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


def main():
    import uvicorn
    uvicorn.run("src.server:app", host=config.HOST, port=config.PORT, reload=False)


if __name__ == "__main__":
    main()
