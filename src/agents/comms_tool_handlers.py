"""
Обработчики межагентной коммуникации (request_research/ask_user/ask_colleague/
raise_event/delegate_task/read_office_chat/get_connection) — третий проход
декомпозиции agent_factory.py (первый — tool_schemas.py, второй —
file_tool_handlers.py; docs/audit-dd-2026-07-06.md §19 п.6). Сделано ПОСЛЕ
того, как tests/test_agent_tool_handlers.py зафиксировал поведение каждого
из этих обработчиков (включая ask_colleague — единственный, что делает СВОЙ
отдельный llm.run_agent-вызов внутри себя).

`build()` — та же фабрика, что file_tool_handlers.build(): принимает
(agent_id, role, publish, publish_and_log), возвращает словарь обработчиков.
"""

import re
from typing import Awaitable, Callable

from src.core import llm
from src.agents import researcher as researcher_agent
from src.office import (
    connections, events as events_module, memory as memory_module,
    models as models_module, office_channel, questions as questions_module,
    registry as registry_module, state, threads as threads_module,
)

_CRED_KEYWORDS = {
    "api", "key", "ключ", "token", "токен", "secret", "пароль", "password",
    "логин", "login", "access", "доступ", "credentials", "учётные", "oauth",
    "telegram", "instagram", "vk", "вконтакте", "openai", "anthropic",
    "notion", "airtable", "google", "youtube", "tiktok", "facebook",
}

_PLATFORM_WORDS = {
    "telegram", "instagram", "vk", "вконтакте", "openai", "anthropic",
    "google", "youtube", "tiktok", "facebook", "notion", "airtable",
    "twitter", "linkedin", "whatsapp", "viber", "discord", "slack",
    "github", "gitlab", "stripe", "yandex", "яндекс", "авито", "avito",
    "wildberries", "wb", "ozon", "озон", "bitrix", "bitrix24",
}

# Общие факты о бизнесе клиента (не про конкретный проект) — такие вопросы, куда
# бы их ни эскалировал руководитель, должны попадать к CEO, а не оседать в чате
# случайного лидера отдела (иначе один и тот же номер телефона будет спрошен и
# CTO, и CMO — по разу на каждый отдел).
_GENERAL_FACT_KEYWORDS = {
    "телефон", "номер", "phone", "почта", "email", "e-mail", "соцсет", "соцсети",
    "social", "инстаграм", "instagram", "vk", "вконтакте", "адрес", "address",
    "реквизит", "юрлицо", "ооо", "ип", "инн", "сайт компании", "бренд", "логотип",
    "контакт", "contact", "whatsapp", "viber", "telegram-канал",
}


def _is_general_fact(question: str) -> bool:
    q = question.lower()
    words = set(re.split(r"[^a-zа-я0-9]+", q))
    return bool(words & _GENERAL_FACT_KEYWORDS)


# Отказ/отсутствие доступа — типичные ответы клиента, когда учётки просто нет
# ("не надо", "нет", "потом") — их НЕЛЬЗЯ сохранять как подключение (баг:
# такой ответ попадал в connections.save() со статусом «успешная интеграция»).
_DECLINE_PATTERNS = re.compile(
    r"^\s*(не\s*надо|не\s*нужно|нет|не\s+сейчас|потом|позже|пропусти(?:ть)?|"
    r"skip|no|not\s+now|later|нету|не\s+знаю|не\s+будет|отказ)\s*[.!]*\s*$",
    re.I,
)


def try_extract_connection(question: str, answer: str) -> dict | None:
    """
    Если вопрос звучит как запрос учётных данных — собираем структуру подключения.
    Возвращает dict для connections.save() или None если не похоже на учётные данные.
    """
    answer = answer.strip()
    if not answer:
        return None
    if _DECLINE_PATTERNS.match(answer):
        return None
    q_lower = question.lower()
    words = set(q_lower.replace(":", " ").replace("?", " ").replace(".", " ").split())

    # Нужен хотя бы один кред-ключевик
    if not (words & _CRED_KEYWORDS):
        return None

    # Определяем название платформы (первое совпадение из известных)
    platform = next((w.capitalize() for w in words if w in _PLATFORM_WORDS), None)
    if not platform:
        # Ищем слово после "для" / "к" / "of" / "for"
        m = re.search(r'(?:для|к|for|of)\s+([a-zа-я0-9_\-]+)', q_lower)
        platform = m.group(1).capitalize() if m else "Сервис"

    # Тип подключения
    if words & {"password", "пароль", "login", "логин"}:
        conn_type = "login"
        # Пробуем разобрать "login: X password: Y" или "логин: X пароль: Y"
        l = re.search(r'(?:login|логин)[:\s]+([^\s,]+)', answer, re.I)
        p = re.search(r'(?:password|пароль)[:\s]+([^\s,]+)', answer, re.I)
        if l and p:
            fields = {"login": l.group(1), "password": p.group(1)}
        else:
            fields = {"value": answer.strip()}
    else:
        conn_type = "api"
        fields = {"key": answer.strip()}

    # Дедуп по имени+значениям — уже делает connections.save() (сравнивает ВСЕ
    # поля, не только key/value) при создании; отдельная проверка здесь была бы
    # дублирующей и более узкой копией той же логики в двух местах.
    return {"name": platform, "type": conn_type, "fields": fields,
            "note": "Автосохранено агентом при ответе на вопрос"}


def build(agent_id: str, role: str,
          publish: Callable[[dict], Awaitable[None]],
          publish_and_log: Callable[[dict], Awaitable[None]]) -> dict[str, Callable]:

    async def _handle_request_research(args: dict) -> str:
        question = args.get("question", "")
        depth = args.get("depth", "quick")
        await publish({"type": "speech", "agent_id": agent_id,
                       "text": f"📡 Запрашиваю ресёрчера [{depth}]: {question[:60]}"})
        # видно в общем чате: кто у кого что запросил
        office_channel.post(agent_id, role, f"@ресёрчер, нужны данные: {question[:160]}")
        await publish({"type": "office_chat", "from": agent_id, "role": role,
                       "text": f"@ресёрчер, нужны данные: {question[:160]}"})
        return await researcher_agent.run_async(
            question=question, depth=depth, publish=publish, agent_id="researcher_1",
        )

    async def _handle_ask_user(args: dict) -> str:
        question_text = args.get("question", "")
        return await _deliver_to_user(question_text, target_agent_id=agent_id)

    async def _deliver_to_user(question_text: str, target_agent_id: str) -> str:
        """Общий путь «вопрос дошёл до пользователя»: используется и напрямую
        (_handle_ask_user — для CEO/лидеров), и как ХВОСТ эскалации ask_leader,
        когда сам руководитель решил, что дальше него вопрос идти некуда, кроме
        клиента. `target_agent_id` — ЧЕЙ это личный чат/вопрос с точки зрения
        пользователя (не обязательно тот, кто изначально спросил)."""
        import asyncio
        # Проверяем память — вдруг на этот вопрос уже отвечали
        cached = memory_module.lookup(question_text)
        if cached:
            await publish({"type": "speech", "agent_id": target_agent_id,
                           "text": f"💭 (из памяти): {question_text[:50]} → {cached[:60]}"})
            return cached
        qid, fut = questions_module.ask(question_text, publish, agent_id=target_agent_id)
        # Вопрос попадает в личный чат руководителя — пользователь ответит прямо там
        threads_module.post(target_agent_id, "agent", question_text, kind="question", question_id=qid)
        await publish({"type": "agent_message", "agent_id": target_agent_id, "from": "agent",
                       "kind": "question", "question_id": qid, "text": question_text})
        try:
            answer = await asyncio.wait_for(fut, timeout=300)  # 5 мин макс
        except asyncio.TimeoutError:
            questions_module.answer(qid, "")
            threads_module.mark_answered(qid)
            await publish({"type": "question_answered", "question_id": qid, "agent_id": target_agent_id})
            return "Пользователь не ответил — продолжай без этих данных."
        if answer:
            memory_module.remember(question_text, answer)
            # Автосохранение в подключения если вопрос про учётные данные
            conn = try_extract_connection(question_text, answer)
            if conn:
                saved = connections.save(conn)
                await publish({"type": "connection_added", "connection": saved,
                               "agent_id": target_agent_id,
                               "text": f"🔌 Доступ '{saved['name']}' сохранён в подключения"})
                await publish({"type": "speech", "agent_id": target_agent_id,
                               "text": f"✅ Доступ к {saved['name']} сохранён — буду использовать в следующий раз автоматически"})
                # Оповещаем всех агентов через общий канал
                office_channel.post(
                    "system", "system",
                    f"🔑 API-ключ для '{saved['name']}' получен и сохранён. "
                    f"Все агенты могут использовать get_connection('{saved['name']}') — "
                    f"не спрашивайте пользователя повторно."
                )
        return answer

    async def _handle_ask_leader(args: dict) -> str:
        """Рядовой сотрудник не спрашивает клиента напрямую — вопрос идёт СВОЕМУ
        руководителю (лидеру отдела; штабным ролям — сразу CEO, у них manager
        уже 'orchestrator_1', см. registry.AgentRecord.manager). Руководитель либо
        отвечает сам (по своему контексту/памяти отдела), либо, если решение
        реально за клиентом, эскалирует ДАЛЬШЕ сам — с дедупом (questions.py уже
        схлопывает похожие вопросы разных сотрудников, кто бы их ни задавал)."""
        question = (args.get("question") or "").strip()
        if not question:
            return "Сформулируй вопрос конкретно."
        rec = registry_module.get(agent_id)
        leader_id = (rec.manager if rec else "") or "orchestrator_1"
        if leader_id == agent_id:
            # Сам лидер/CEO вызвал ask_leader по ошибке — веди себя как ask_user.
            return await _deliver_to_user(question, target_agent_id=agent_id)
        leader_rec = registry_module.get(leader_id)
        leader_role = leader_rec.role if leader_rec else ("orchestrator" if leader_id == "orchestrator_1" else "")

        await publish({"type": "speech", "agent_id": agent_id,
                       "text": f"💬 спрашиваю {leader_role or 'руководителя'}: {question[:60]}"})
        office_channel.post(agent_id, role, f"@{leader_role}, {question[:200]}")
        await publish({"type": "office_chat", "from": agent_id, "role": role,
                       "text": f"@{leader_role}, {question[:200]}"})

        from src.office import prompt_builder, roles as roles_module
        leader_work = state.result_for(leader_id) if leader_rec else ""
        leader_base = roles_module.render(leader_role) if leader_role else ""
        sys = (leader_base + prompt_builder.brief_block()
               + (f"\n\n=== ТВОЯ ПОСЛЕДНЯЯ РАБОТА ===\n{leader_work[:1200]}" if leader_work else "")
               + "\n\nСотрудник задаёт вопрос за пределами своей рабочей области. Если ты можешь "
                 "ответить сам (из своего контекста/знаний по компании) — ответь СРАЗУ, коротко. "
                 "Если ответ реально знает только сам клиент (владелец бизнеса) — не выдумывай, а "
                 "ответь ОДНОЙ строкой строго в формате 'ESCALATE: <вопрос клиенту одним предложением>'.")
        try:
            raw = await llm.run_agent(
                system=sys, user=question,
                model=models_module.for_agent(leader_id),
                max_tokens=400, use_search=False, agent_id=leader_id,
            )
        except Exception as e:
            raw = f"ESCALATE: {question}"  # руководитель недоступен — не блокируем цепочку молча
        raw = (raw or "").strip()

        if raw.upper().startswith("ESCALATE:"):
            client_question = raw.split(":", 1)[1].strip() or question
            target = "orchestrator_1" if _is_general_fact(client_question) else leader_id
            # В треде СОТРУДНИКА — не тишина, а явная пометка "куда ушёл вопрос"
            # и кнопка (фронт рисует по redirect_agent_id) открыть чат с адресатом.
            threads_module.post(agent_id, "system",
                                 f"Вопрос передан {'CEO' if target == 'orchestrator_1' else leader_role} — "
                                 f"ответ придёт в чате с ним.",
                                 kind="redirect", redirect_agent_id=target)
            await publish({"type": "agent_message", "agent_id": agent_id, "from": "system",
                           "kind": "redirect", "redirect_agent_id": target,
                           "text": f"Вопрос передан {'CEO' if target == 'orchestrator_1' else leader_role}"})
            answer = await _deliver_to_user(client_question, target_agent_id=target)
            await publish({"type": "speech", "agent_id": agent_id,
                           "text": f"✅ Получен ответ через {'CEO' if target == 'orchestrator_1' else leader_role}: {answer[:70]}"})
            return answer

        await publish({"type": "speech", "agent_id": leader_id, "text": f"💬 → {agent_id}: {raw[:80]}"})
        office_channel.post(leader_id, leader_role, f"@{role}: {raw[:240]}")
        await publish({"type": "office_chat", "from": leader_id, "role": leader_role,
                       "text": f"@{role}: {raw[:240]}"})
        return raw or "Руководитель не дал содержательного ответа — реши по своему усмотрению."

    async def _handle_ask_colleague(args: dict) -> str:
        """Синхронная консультация: коллега нужной роли отвечает на вопрос ОДНИМ
        бесшумным LLM-вызовом (без инструментов → без рекурсии и циклов)."""
        from src.office import prompt_builder
        col_role = (args.get("role") or "").strip()
        question = (args.get("question") or "").strip()
        if not col_role or not question:
            return "Укажи роль коллеги и конкретный вопрос."
        if col_role == role:
            return "Это твоя же роль — реши сам, без консультации."
        # Находим коллегу этой роли (или отвечаем «от лица роли», если он ещё не нанят)
        colleague = next((a for a in registry_module.all_agents() if a.role == col_role), None)
        col_id = colleague.agent_id if colleague else f"{col_role}_1"
        col_work = state.result_for(col_id) if colleague else ""
        from src.office import roles as roles_module
        col_base = roles_module.render(col_role)
        await publish({"type": "speech", "agent_id": agent_id,
                       "text": f"💬 спрашиваю {col_role}: {question[:60]}"})
        # вопрос коллеге виден в общем чате
        office_channel.post(agent_id, role, f"@{col_role}, {question[:200]}")
        await publish({"type": "office_chat", "from": agent_id, "role": role,
                       "text": f"@{col_role}, {question[:200]}"})
        sys = (col_base + prompt_builder.brief_block()
               + ("\n\n=== ТВОЯ ПОСЛЕДНЯЯ РАБОТА (опирайся на неё) ===\n" + col_work[:1500]
                  if col_work else "")
               + "\n\nКоллега по команде задаёт тебе вопрос. Ответь КОРОТКО, конкретно и по делу "
                 "(без воды), чтобы он сразу мог использовать ответ в работе.")
        try:
            answer = await llm.run_agent(
                system=sys, user=question,
                model=models_module.for_agent(col_id),
                max_tokens=600, use_search=False, agent_id=col_id,
            )
        except Exception as e:
            return f"Коллега {col_role} не смог ответить: {str(e)[:80]}. Реши сам."
        answer = (answer or "").strip() or "Коллега не дал содержательного ответа — реши сам."
        await publish({"type": "speech", "agent_id": col_id,
                       "text": f"💬 → {agent_id}: {answer[:80]}"})
        # ответ коллеги виден в общем чате
        office_channel.post(col_id, col_role, f"@{role}: {answer[:240]}")
        await publish({"type": "office_chat", "from": col_id, "role": col_role,
                       "text": f"@{role}: {answer[:240]}"})
        return f"Ответ {col_role}: {answer}"

    async def _handle_raise_event(args: dict) -> str:
        kind = (args.get("kind") or "signal").strip()
        summary = (args.get("summary") or "").strip()
        detail = (args.get("detail") or "").strip()
        if not summary:
            return "Опиши суть сигнала одной фразой."
        ev = events_module.raise_event(kind, summary, detail, from_role=role, from_agent=agent_id)
        if not ev:
            return "Событие не создано (пустая суть)."
        label = events_module.KINDS.get(ev["kind"], ev["kind"])
        await publish_and_log({"type": "speech", "agent_id": agent_id,
                               "text": f"📨 Сигнал компании [{label}]: {summary[:70]}"})
        await publish({"type": "department_event", "agent_id": agent_id, "kind": ev["kind"],
                       "text": f"{label} от {role}: {summary[:120]}"})
        return ("Событие передано CEO — он интерпретирует его и при необходимости поручит "
                "нужному отделу. Продолжай свою задачу.")

    async def _handle_delegate_task(args: dict) -> str:
        from src.office import plan as plan_module
        from src.office import roles as roles_module
        col_role = (args.get("role") or "").strip()
        title = (args.get("title") or "").strip()
        if not col_role or not title:
            return "Укажи роль исполнителя и что нужно сделать."
        if col_role == role:
            return "Это твоя зона — сделай сам, не делегируй себе."
        if col_role not in roles_module.known_roles():
            valid = ", ".join(sorted(roles_module.known_roles()))
            return (f"Роли «{col_role}» не существует в офисе — задача НЕ поставлена. "
                    f"Реальные роли: {valid}.")
        t = plan_module.add_task(title, col_role, args.get("done_criterion", ""),
                                 requested_by=agent_id)
        await publish({"type": "speech", "agent_id": agent_id,
                       "text": f"📌 Поставил задачу {col_role}: {title[:50]}"})
        office_channel.post(agent_id, role, f"📌 @{col_role}, задача: {title[:160]}")
        await publish({"type": "office_chat", "from": agent_id, "role": role,
                       "text": f"📌 @{col_role}, задача: {title[:160]}"})
        return (f"Задача поставлена {col_role} (id={t['id']}) и добавлена на доску — "
                f"его лидер назначит исполнителя. Можешь продолжать своё.")

    async def _handle_create_recurring_process(args: dict) -> str:
        from src.office import processes as processes_module, roles as roles_module
        title = (args.get("title") or "").strip()
        proc_role = (args.get("role") or role).strip()
        instruction = (args.get("instruction") or "").strip()
        if not title or not instruction:
            return "Укажи название процесса и что делать каждый раз (instruction)."
        if proc_role not in roles_module.known_roles():
            valid = ", ".join(sorted(roles_module.known_roles()))
            return f"Роли «{proc_role}» не существует — процесс НЕ создан. Реальные роли: {valid}."
        # Процесс наследует ТВОЙ проект (если ты в нём) — иначе его задачи могли
        # бы доставаться воркеру ДРУГОГО параллельного проекта, у которого нет
        # файлов, написанных тобой (см. processes.create докстринг).
        my_rec = registry_module.get(agent_id)
        proc = processes_module.create(title, proc_role, instruction,
                                       project_id=(my_rec.project_id if my_rec else ""))
        if proc.get("_deduped"):
            existing_role = proc.get("role", proc_role)
            role_note = (f" (на роли {existing_role})" if existing_role != proc_role else "")
            return (f"Похожий активный процесс «{proc['title']}»{role_note} (id={proc['id']}) уже "
                    f"существует в этом проекте — новый НЕ создан, чтобы не дублировать работу. "
                    f"Если нужно изменить его поведение, дождись, пока текущая задача процесса "
                    f"закроется, и поставь правку через delegate_task, а не заводи ещё один.")
        await publish({"type": "speech", "agent_id": agent_id,
                       "text": f"🔄 Завёл повторяющийся процесс: {title[:60]}"})
        return (f"Процесс «{title}» создан (id={proc['id']}) — с этого момента задача "
                f"«{instruction[:60]}» будет ставиться заново каждый цикл офиса, как только "
                f"предыдущая закрыта. Дальше можешь заняться остальным.")

    async def _handle_read_office_chat(args: dict) -> str:
        n = args.get("n", 20)
        msgs = office_channel.recent(n)
        if not msgs:
            return "Общий чат пуст."
        lines = [f"[{m['from']}]: {m['text']}" for m in msgs]
        return "\n".join(lines)

    async def _handle_get_connection(args: dict) -> str:
        import json
        name = args.get("name", "")
        conn = connections.get_by_name(name)
        if not conn:
            available = ", ".join(connections.names()) or "нет сохранённых"
            return (
                f"Подключение '{name}' не найдено. Доступные: {available}. "
                f"Используй ask_user (или ask_leader, если он у тебя есть) чтобы запросить у "
                f"пользователя API-ключ или логин/пароль — они автоматически сохранятся в подключения."
            )
        return json.dumps({"name": conn["name"], "type": conn["type"], "fields": conn["fields"]},
                          ensure_ascii=False)

    return {
        "request_research": _handle_request_research,
        "ask_user": _handle_ask_user,
        "ask_leader": _handle_ask_leader,
        "ask_colleague": _handle_ask_colleague,
        "raise_event": _handle_raise_event,
        "delegate_task": _handle_delegate_task,
        "create_recurring_process": _handle_create_recurring_process,
        "read_office_chat": _handle_read_office_chat,
        "get_connection": _handle_get_connection,
    }
