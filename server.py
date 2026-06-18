"""
FastAPI сервер — SSE-стрим событий + статика игры.
"""

import asyncio
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from src.office import bus, registry, loop as office_loop, demo

load_dotenv()

DEMO_MODE = os.getenv("DEMO_MODE", "0") == "1"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Стартуем офис в фоне: демо-сценарий или реальный автономный цикл
    runner = demo.run if DEMO_MODE else office_loop.run
    task = asyncio.create_task(runner())
    yield
    task.cancel()


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", response_class=HTMLResponse)
async def index():
    return Path("static/index.html").read_text(encoding="utf-8")


@app.get("/events")
async def events():
    """SSE endpoint — браузер подключается и получает все события офиса."""
    q = bus.subscribe()

    # Отправляем текущее состояние реестра при подключении
    async def stream():
        try:
            # Снапшот текущих агентов
            for agent in registry.all_agents():
                snapshot = {
                    "type": "hired",
                    "agent_id": agent.agent_id,
                    "role": agent.role,
                    "desk": agent.desk,
                    "task": agent.task,
                }
                yield f"data: {json.dumps(snapshot, ensure_ascii=False)}\n\n"

            # Живой поток
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=30)
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
        finally:
            bus.unsubscribe(q)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/agents")
async def get_agents():
    return [
        {
            "agent_id": a.agent_id,
            "role": a.role,
            "desk": a.desk,
            "status": a.status,
            "last_message": a.last_message,
            "task": a.task,
        }
        for a in registry.all_agents()
    ]
