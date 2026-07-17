"""
Общение с офисом: знания, память, вопросы/ответы, личные чаты, чат с CEO. Перенесено из server.py (docs/technical-due-diligence-
2026-07-17.md §3.2.1, PR-5) механически — тот же код, то же поведение.
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from fastapi.requests import Request
import asyncio
from src.office import brief
from src.office import bus
from src.office import chat
from src.office import demo
from src.office import investigation
from src.office import memory
from src.office import milestones
from src.office import bootstrap as office_bootstrap
from src.office import office_channel
from src.office import loop as office_loop
from src.agents import orchestrator
from src.office import org
from src.office import plan as plan_module
from src.office import questions as questions_module
from src.office import registry
from src.office import threads as threads_module

router = APIRouter()


@router.get("/api/knowledge")
async def get_knowledge():
    """Трёхслойная память офиса: что он знает о клиенте и отделах."""
    from src.office import knowledge as knowledge_module
    facts = knowledge_module.all_facts()
    layers = {"global": 0, "user": 0, "department": 0}
    for f in facts:
        k = f.get("layer", "department")
        layers[k] = layers.get(k, 0) + 1
    return {"facts": facts, "count": len(facts), "layers": layers}

@router.get("/api/memory")
async def get_memory():
    """Все сохранённые ответы пользователя."""
    return {"entries": memory.all_entries()}

@router.get("/api/questions")
async def get_questions():
    """Список всех ожидающих ответа вопросов от агентов."""
    from src.office import questions as q_module
    return {"questions": q_module.list_pending()}

@router.post("/api/answer")
async def answer_question(request: Request):
    data = await request.json()
    qid = data.get("question_id", "")
    ans = data.get("answer", "").strip()
    from src.office import questions as q_module
    ok = q_module.answer(qid, ans)
    if ok:
        await bus.publish({"type": "question_answered", "question_id": qid})
    return {"ok": ok}

@router.get("/api/threads")
async def get_threads():
    """Сводка по личным чатам с агентами (для боковой панели вкладки «Чаты»)."""
    return {"threads": threads_module.summaries()}

@router.get("/api/thread/{agent_id}")
async def get_thread(agent_id: str):
    """Полная переписка пользователя с конкретным агентом."""
    return {"agent_id": agent_id, "worker_id": agent_id,
            "messages": threads_module.recent(agent_id)}

@router.post("/api/ask")
async def ask_agent(request: Request):
    """Сообщение пользователя агенту в личном чате.

    Если у агента есть открытый вопрос — сообщение трактуется как ОТВЕТ на него
    (разблокирует ожидающую задачу). Иначе — это обычная беседа с агентом.
    """
    data = await request.json()
    # worker_id — предпочтительное имя (BOS §12 п.4); agent_id принимается как
    # deprecated-алиас на переходный период, чтобы старые клиенты не сломались.
    agent_id = data.get("worker_id") or data.get("agent_id", "")
    message = (data.get("message") or "").strip()

    if not agent_id or not message:
        return JSONResponse({"error": "worker_id и message обязательны"}, status_code=400)

    if registry.get(agent_id) is None:
        return JSONResponse({"error": "агент не найден"}, status_code=404)

    # Сообщение пользователя всегда попадает в ленту чата
    threads_module.post(agent_id, "user", message)

    # 1) Есть ожидающий вопрос от этого агента → это ответ на него
    qid = questions_module.pending_for(agent_id)
    if qid:
        questions_module.answer(qid, message)
        threads_module.mark_answered(qid)
        await bus.publish({"type": "question_answered", "question_id": qid, "agent_id": agent_id})
        await bus.publish({"type": "agent_message", "agent_id": agent_id, "from": "user",
                           "kind": "msg", "text": message})
        return {"agent_id": agent_id, "worker_id": agent_id, "answered": True}

    # 2) Иначе — обычный диалог с агентом. Сообщение пользователя агенту тоже считаем
    # директивой (например «запусти бота») — иначе автономный цикл его не увидит.
    role = registry.get(agent_id).role
    memory.remember(f"Указание пользователя ({role})", message)
    # Intent Layer (BOS §1): ЕДИНЫЙ вход намерений владельца — личный чат тоже
    # фиксируется в журнале, а не только общий канал (/api/chat).
    from src.office import intent as intent_module
    _it = intent_module.capture(message, source="owner")
    if _it:
        intent_module.set_interpretation(_it["id"], scope="personal_chat",
                                         directive=f"диалог с {agent_id} → память офиса")
    await bus.publish({"type": "agent_message", "agent_id": agent_id, "from": "user",
                       "kind": "msg", "text": message})
    # ⚠️ Реальный найденный баг (живой pre-release аудит): DEMO_MODE обещает
    # "демо без расхода токенов" (CLAUDE.md §2), но личный чат с агентом ДО этой
    # правки безусловно вызывал chat.ask() → настоящий LLM-запрос → реальный
    # расход, даже когда demo.run() (весь остальной офис-цикл) работает по
    # сценарию без единого обращения к сети. Посетитель демо мог случайно
    # потратить реальный баланс оператора, просто написав агенту.
    if DEMO_MODE:
        reply = ("Сейчас я в демо-режиме и работаю по сценарию, а не отвечаю на "
                 "произвольные вопросы — зарегистрируйтесь, чтобы говорить с реальным офисом.")
        threads_module.post(agent_id, "agent", reply)
        await bus.publish({"type": "agent_message", "agent_id": agent_id, "from": "agent",
                           "kind": "msg", "text": reply})
        return {"agent_id": agent_id, "worker_id": agent_id, "reply": reply}
    try:
        reply = await chat.ask(agent_id, message, publish=bus.publish)
        threads_module.post(agent_id, "agent", reply)
        await bus.publish({"type": "agent_message", "agent_id": agent_id, "from": "agent",
                           "kind": "msg", "text": reply})
        return {"agent_id": agent_id, "worker_id": agent_id, "reply": reply}
    except Exception as e:
        return JSONResponse({"error": str(e)[:200]}, status_code=500)

@router.get("/api/chat")
async def get_chat():
    """Последние сообщения общего канала офиса."""
    return {"messages": office_channel.recent(100)}

_STEER_ROLES = {"developer", "designer", "integrator", "marketer", "salesman"}

async def _post_ceo(text: str) -> None:
    """CEO пишет в общий чат (и в SSE)."""
    cmsg = office_channel.post("orchestrator_1", "orchestrator", text)
    await bus.publish({"type": "office_chat", "from": "orchestrator_1", "role": "orchestrator",
                       "text": text, "id": cmsg["id"]})

async def _intake_from_chat(text: str) -> None:
    """Первое расследование ПЕРЕД запуском офиса (docs/first-investigation-plan-
    2026-07-16.md, Фаза 4): живой агентский диалог вместо жёсткого 2-шагового
    скрипта (спросить фиксированные вопросы → собрать один ответ → бриф).
    Агент сам решает, искать ли web_search или спросить коротко, и завершает
    явным finish_investigation — см. office/investigation.py."""
    await bus.publish({"type": "thinking", "agent_id": "orchestrator_1",
                       "text": "Разбираюсь…"})
    try:
        reply, finished = await asyncio.wait_for(
            investigation.run_turn(text, publish=bus.publish),
            timeout=90.0,
        )
    except Exception:
        reply, finished = (
            "Не расслышал — повторите, пожалуйста, чем занимается компания?", False)
    await _post_ceo(reply)
    if finished:
        office_loop.wake_tenant()

async def _steer_from_chat(text: str) -> None:
    """Сообщение предпринимателя из чата. Если офис ещё не запущен (нет брифа) — ведём
    discovery (уточняющие вопросы → бриф → старт). Если офис работает — CEO-триаж: понять
    и органично вписать в работу. В фоне, чтобы POST отвечал мгновенно.
    """
    # Intent: единый вход намерений владельца (BOS §1) — каждое сообщение фиксируется
    # в журнале ДО интерпретации, с результатом триажа после.
    from src.office import intent as intent_module
    _intent = intent_module.capture(text, source="owner" if brief.is_ready() else "onboarding")

    # ⚠️ Тот же класс бага, что был закрыт в /api/ask (pre-release аудит,
    # docs/pre-release-audit-2026-07-15.md, находка High #2): DEMO_MODE обещает
    # "демо без расхода токенов" (CLAUDE.md §2), но и discovery-ветка (_intake_from_chat),
    # и CEO-триаж (interpret_directive) ниже безусловно дёргают реальный LLM.
    # Короткое замыкание ДО обеих веток — общий чат демо-режима теперь тоже бесплатен.
    if DEMO_MODE:
        reply = ("Сейчас я в демо-режиме и работаю по сценарию, а не отвечаю на "
                 "произвольные вопросы — зарегистрируйтесь, чтобы говорить с реальным офисом.")
        cmsg = office_channel.post("orchestrator_1", "orchestrator", reply)
        await bus.publish({"type": "office_chat", "from": "orchestrator_1", "role": "orchestrator",
                           "text": reply, "id": cmsg["id"]})
        return

    # ── DISCOVERY: офис ещё не запущен — сначала уточняем, потом строим бриф ──
    if not brief.is_ready():
        try:
            await _intake_from_chat(text)
            if _intent:
                intent_module.set_interpretation(_intent["id"], scope="discovery")
        except Exception:
            memory.remember("Указание пользователя офису", text)  # не теряем сообщение
        return

    try:
        b = brief.get()
        goal = b.get("goal", "") or brief.summary()
        niche = b.get("niche", "")
        audience = b.get("audience", "")
        strategy = office_bootstrap.strategy_text()
        ms = milestones.all_stages()
        try:
            open_d = org.open_departments()
            depts_text = ", ".join(open_d) if open_d else "(нет открытых отделов)"
        except Exception:
            depts_text = ""
        board = plan_module.board_summary() if plan_module.is_generated() else ""
        res = await orchestrator.interpret_directive(
            goal, strategy, ms, depts_text, board, text, publish=bus.publish,
            niche=niche, audience=audience)
    except Exception:
        memory.remember("Указание пользователя офису", text)  # фолбэк — прежнее поведение
        return

    scope = (res.get("scope") or "steer").strip()
    reply = (res.get("reply") or "").strip()
    directive = (res.get("directive") or "").strip()
    ops = res.get("milestone_ops") or []
    new_tasks = res.get("new_tasks") or []
    changes: list[str] = []
    if _intent:
        intent_module.set_interpretation(_intent["id"], scope=scope, directive=directive,
                                         tasks_added=len(new_tasks))

    rejected_reason = ""
    if scope == "steer":
        # приоритетная директива — её чтят CEO и лидеры в своих решениях
        memory.remember("Указание предпринимателя (приоритет)", directive or text)

        # Решение как ТРАНЗАКЦИЯ (BOS §14 п.3, Phase 5): директива → PlanDiff →
        # Sandbox-проверки (бюджет/конфликт артефактов/вето Конституции) → apply|reject.
        # Больше НЕ мутируем план/вехи напрямую — только через прошедший проверки diff.
        from src.office import decision_engine
        plan_diff = {
            "add_tasks": new_tasks if isinstance(new_tasks, list) else [],
            "milestone_ops": ops if isinstance(ops, list) else [],
        }
        outcome = decision_engine.decide(plan_diff, made_by="orchestrator_1",
                                         thought=directive or text[:120])
        changes = outcome["changes"]
        if outcome["applied"]:
            office_loop.wake_tenant()  # офис мог быть в мониторинге — пусть переоценит
        elif outcome["reason"] and not decision_engine.is_empty(plan_diff):
            rejected_reason = outcome["reason"]

    # ответ CEO в общий чат (предприниматель видит, что его услышали)
    if reply:
        cmsg = office_channel.post("orchestrator_1", "orchestrator", reply)
        await bus.publish({"type": "office_chat", "from": "orchestrator_1", "role": "orchestrator",
                           "text": reply, "id": cmsg["id"]})
    if changes:
        await bus.publish({"type": "system", "text": "📌 План обновлён: " + "; ".join(changes[:6])})
    if rejected_reason:
        # Автономность — торговля, не молчаливый саботаж (BOS §2): показываем цену отказа.
        await bus.publish({"type": "system",
                           "text": f"⚖️ Решение по вашему запросу отклонено проверками: {rejected_reason}. "
                                   f"Смотрите «Решения» — там причина. Уточните или снимите ограничение."})

@router.post("/api/chat")
async def post_chat(request: Request):
    """Предприниматель пишет в общий канал офиса. Сообщение сохраняется и сразу
    отдаётся, а CEO в фоне осмысливает его и вписывает в работу (ответ + правки этапов/доски)."""
    data = await request.json()
    text = (data.get("text") or "").strip()
    if not text:
        return JSONResponse({"error": "text обязателен"}, status_code=400)
    msg = office_channel.post("user", "user", text)
    await bus.publish({"type": "office_chat", "from": "user", "role": "user",
                       "text": text, "id": msg["id"]})
    # CEO-триаж в фоне (контекст тенанта копируется в задачу автоматически)
    asyncio.create_task(_steer_from_chat(text))
    return {"ok": True, "message": msg}
