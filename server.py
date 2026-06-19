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
from fastapi.requests import Request
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from src.office import bus, registry, loop as office_loop, demo, chat, brief, state, progress, connections
from src.agents import onboarding

load_dotenv()

DEMO_MODE = os.getenv("DEMO_MODE", "0") == "1"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Загружаем сохранённый бриф и историю (если были) — офис продолжит с того же места
    if not DEMO_MODE:
        brief.load()
        state.load()
        progress.load()
        connections.load()
        registry.restore(state.saved_agents())
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


@app.get("/api/brief/status")
async def brief_status():
    """Фронт проверяет: нужен ли онбординг, или офис уже работает."""
    return {"ready": brief.is_ready(), "demo": DEMO_MODE, "brief": brief.get()}


@app.post("/api/brief/questions")
async def brief_questions(request: Request):
    """Шаг 1: клиент прислал ввод → офис задаёт уточняющие вопросы."""
    data = await request.json()
    client_input = (data.get("input") or "").strip()
    if not client_input:
        return JSONResponse({"error": "пустой ввод"}, status_code=400)
    try:
        questions = await onboarding.make_questions(client_input, publish=bus.publish)
        return {"questions": questions}
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=500)


@app.post("/api/brief/start")
async def brief_start(request: Request):
    """Шаг 2: клиент ответил на вопросы → формируем бриф и запускаем офис."""
    data = await request.json()
    client_input = (data.get("input") or "").strip()
    qa_pairs = data.get("answers", [])
    if not client_input:
        return JSONResponse({"error": "пустой ввод"}, status_code=400)
    try:
        brief_data = await onboarding.build_brief(client_input, qa_pairs, publish=bus.publish)
        brief.set_brief(brief_data)  # сигналит офису о старте
        return {"ok": True, "brief": brief_data}
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=500)


@app.get("/api/history")
async def get_history():
    """Лента событий из прошлых запусков — фронт показывает её при загрузке."""
    return {"events": state.history(), "results": {
        a.agent_id: state.result_for(a.agent_id) for a in registry.all_agents()
    }}


@app.get("/api/deliverables")
async def get_deliverables():
    """Готовые результаты работы агентов — пользователь может посмотреть и скопировать."""
    return {"deliverables": state.deliverables()}


@app.get("/api/progress")
async def get_progress():
    """Текущий этап развития офиса для индикатора прогресса."""
    return progress.get()


@app.get("/api/agent/{agent_id}")
async def get_agent_detail(agent_id: str):
    """Карточка агента: что делает сейчас и что уже сделал."""
    rec = registry.get(agent_id)
    if rec is None:
        return JSONResponse({"error": "агент не найден"}, status_code=404)
    return {
        "agent_id": rec.agent_id,
        "role": rec.role,
        "status": rec.status,
        "task": rec.task,
        "current": rec.last_message or rec.task,
        "done": state.deliverables_for(agent_id),
        "activity": state.events_for(agent_id),
    }


@app.get("/api/connections")
async def get_connections():
    return {"connections": connections.list_all()}


@app.post("/api/connections")
async def save_connection(request: Request):
    data = await request.json()
    if not (data.get("name") or "").strip():
        return JSONResponse({"error": "название обязательно"}, status_code=400)
    item = connections.save(data)
    return {"ok": True, "connection": item}


@app.delete("/api/connections/{cid}")
async def delete_connection(cid: str):
    ok = connections.delete(cid)
    return {"ok": ok}


@app.post("/api/brief/reset")
async def brief_reset():
    """Полный сброс: новый клиент / новая задача с чистого листа."""
    brief.reset()
    state.reset()
    registry.reset()
    chat.clear_all()
    progress.reset()
    return {"ok": True}


@app.get("/api/questions")
async def get_questions():
    """Список всех ожидающих ответа вопросов от агентов."""
    from src.office import questions as q_module
    return {"questions": q_module.list_pending()}


@app.post("/api/answer")
async def answer_question(request: Request):
    data = await request.json()
    qid = data.get("question_id", "")
    ans = data.get("answer", "").strip()
    from src.office import questions as q_module
    ok = q_module.answer(qid, ans)
    if ok:
        await bus.publish({"type": "question_answered", "question_id": qid})
    return {"ok": ok}


@app.post("/api/ask")
async def ask_agent(request: Request):
    """Пользователь задаёт вопрос конкретному агенту."""
    data = await request.json()
    agent_id = data.get("agent_id", "")
    message = data.get("message", "").strip()

    if not agent_id or not message:
        return JSONResponse({"error": "agent_id и message обязательны"}, status_code=400)

    if registry.get(agent_id) is None:
        return JSONResponse({"error": "агент не найден"}, status_code=404)

    try:
        reply = await chat.ask(agent_id, message, publish=bus.publish)
        return {"agent_id": agent_id, "reply": reply}
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=500)
