"""FastAPI web server for the Job Search Agent.

Serves the interactive UI, preference clarification, and SSE search progress.
"""

from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path
from queue import Empty, Queue
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from contextlib import asynccontextmanager

from agent import preload_model, run_job_search
from clarify import clarify

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    def _load() -> None:
        try:
            print(f"Preloading model {__import__('config').MODEL_ID}…")
            preload_model()
            print("Model ready.")
        except Exception as exc:  # noqa: BLE001
            print(f"Model preload failed (will retry on first search): {exc}")

    threading.Thread(target=_load, daemon=True).start()
    yield


app = FastAPI(title="Job Search Agent", version="0.1.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


class ClarifyRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    answers: dict[str, Any] = Field(default_factory=dict)


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=2000)
    criteria: dict[str, str] = Field(default_factory=dict)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/clarify")
def api_clarify(body: ClarifyRequest) -> dict[str, Any]:
    """Check preferences; ask follow-up questions if anything important is missing."""
    query = body.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query is required.")
    return clarify(query, body.answers)


@app.post("/api/search")
async def search(body: SearchRequest) -> StreamingResponse:
    """Stream status/log/result events as SSE while the agent runs."""
    query = body.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query is required.")

    event_queue: Queue[dict[str, Any] | None] = Queue()

    def worker() -> None:
        try:
            for event in run_job_search(query, criteria=body.criteria or None):
                event_queue.put(event)
        except Exception as exc:  # noqa: BLE001
            event_queue.put(
                {"type": "status", "phase": "error", "message": f"Unexpected error: {exc}"}
            )
        finally:
            event_queue.put(None)

    threading.Thread(target=worker, daemon=True).start()

    async def event_stream():
        while True:
            item = await asyncio.to_thread(_queue_get, event_queue)
            if item is None:
                yield "event: end\ndata: {}\n\n"
                break
            payload = json.dumps(item, ensure_ascii=False)
            yield f"data: {payload}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _queue_get(q: Queue) -> dict[str, Any] | None:
    while True:
        try:
            return q.get(timeout=0.25)
        except Empty:
            continue


if __name__ == "__main__":
    import subprocess
    import time
    import webbrowser

    import uvicorn

    url = "http://127.0.0.1:8000"

    def _open_system_browser() -> None:
        # Wait for the server, then open the OS browser (not Cursor/VS Code).
        time.sleep(0.8)
        try:
            subprocess.Popen(["open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            webbrowser.open(url)

    threading.Thread(target=_open_system_browser, daemon=True).start()
    print(f"Opening {url} in your system browser…")
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=False)
