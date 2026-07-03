"""
Planning Engine — планирование и маршрутизация как отдельная подсистема (BOS §12).

Расслоение loop.py (Phase 6): чистые, детерминированные функции «есть ли ход»,
«свободен ли работник», «готовность отдела» и детерминированный фолбэк-план вынесены
из бог-модуля цикла. Здесь НЕТ мутабельного состояния живости (watchdog/futures) и
НЕТ замыканий цикла — только чтение мира (plan/org/registry/state), поэтому модуль
покрывается unit-тестами без поднятия полного офис-цикла.

  fallback_plan(goal)               — детерминированный план, когда LLM недоступна
  has_actionable_move()             — есть ли вообще ход у офиса на этом цикле
  dept_actionable(dept_id, now)     — есть ли ход у отдела
  free_worker_of_role(dept, role,…) — свободный работник роли
  has_orphan_tasks()                — есть ли задачи без обслуживающего отдела
"""

import os
import time

from src.office import plan, org, registry, state

# Антидребезг живости работника (был в loop.py; сюда переехал вместе с потребителями).
AGENT_COOLDOWN_SECS = int(os.getenv("AGENT_COOLDOWN_SECS", "25"))


def fallback_plan(goal: str) -> list[dict]:
    """Детерминированный план под типовой результат, когда LLM-генерация плана недоступна.
    Гарантирует, что офис всегда plan-driven (а не уходит в LLM-хаос)."""
    g = (goal or "").lower()
    # ЯВНЫЙ запрос продукта (императив «сделай/нужен X»), а не упоминание X как продукта бизнеса.
    wants_bot = any(p in g for p in ("нужен бот", "нужен телеграм", "сделай бот", "сделать бот",
                                     "хочу бот", "бот для записи", "бот записи", "бот заявок",
                                     "телеграм-бот", "telegram-бот", "запусти бот"))
    wants_site = any(p in g for p in ("нужен сайт", "нужен лендинг", "сделай сайт", "сделай лендинг",
                                      "сделать сайт", "сделать лендинг", "хочу сайт", "хочу лендинг",
                                      "одностраничник", "landing page", "собери лендинг", "собери сайт"))
    if not wants_bot and not wants_site:
        # ПО УМОЛЧАНИЮ не строим вслепую: готовим план запуска + рекомендации и СПРАШИВАЕМ
        # клиента, что делать первым. (Раньше тут всегда был лендинг — главная причина «глупости».)
        return [
            {"id": "t1",
             "title": "На основе исследования и стратегии подготовить КОРОТКИЙ план запуска "
                      "и рекомендации (позиционирование, оффер, первые 2-3 шага). В конце ОБЯЗАТЕЛЬНО "
                      "через ask_user задать клиенту 1-2 вопроса: что строить первым (лендинг / бот / "
                      "MVP / контент-план) и какие ресурсы есть. НЕ строй продукт, пока клиент не выбрал.",
             "role": "marketer", "deps": [],
             "done_criterion": "готов план запуска + клиенту задан вопрос, что делать дальше"},
        ]
    if wants_bot:
        return [
            {"id": "t1", "title": "Подготовить тексты, услуги и приветствие для бота",
             "role": "marketer", "deps": [], "done_criterion": "готовы тексты и список услуг"},
            {"id": "t2", "title": "Настроить и запустить Telegram-бота сбора заявок",
             "role": "integrator", "deps": ["t1"], "done_criterion": "бот запущен через launch_bot"},
        ]
    # сайт/лендинг — основной кейс
    return [
        {"id": "t1", "title": "Подготовить оффер и продающие тексты для всех блоков лендинга",
         "role": "marketer", "deps": [], "done_criterion": "готов копирайт: оффер, выгоды, FAQ, CTA"},
        {"id": "t2", "title": "Собрать конверсионный многостраничный лендинг в site/ с формой заявки",
         "role": "designer", "deps": ["t1"],
         "done_criterion": "site/index.html + страницы опубликованы, форма шлёт на /api/site-lead"},
        {"id": "t3", "title": "Проверить формы/CTA и довести лендинг до рабочего состояния",
         "role": "developer", "deps": ["t2"], "done_criterion": "формы работают, сайт опубликован и собирает лиды"},
    ]


def dept_actionable(dept_id: str, now: float) -> bool:
    """Есть ли в отделе ход. Когда план сгенерирован — отдел активен ТОЛЬКО если у него
    есть готовая задача (иначе простаивает, цикл не крутится вхолостую)."""
    if plan.is_generated() and not plan.ready_for_department(dept_id):
        return False
    worker_roles = set(org.member_roles(dept_id))  # роли работников (без лидера)
    members = registry.members_of(dept_id)
    for a in members:
        if a.role not in worker_roles:
            continue  # лидер отдела — не работник
        on_cooldown = (now - state.last_run_for(a.agent_id)) < AGENT_COOLDOWN_SECS
        if a.status != "thinking" and not on_cooldown:
            return True
    existing = {a.role for a in members}
    return any(r not in existing for r in worker_roles)


def has_orphan_tasks() -> bool:
    """Есть ли pending-задачи, которые НЕ обслуживает ни один отдел (роль без отдела —
    например analyst/researcher). Такие нельзя выполнить через отделы → офис завис бы."""
    servable = set()
    for did in org.catalog():
        servable |= set(org.member_roles(did))
    for t in plan.all_tasks():
        if t.get("status") in ("pending", "in_progress") and t.get("role") not in servable \
                and not t.get("department"):
            return True
    return False


def has_actionable_move() -> bool:
    """Есть ли вообще ход у офиса на этом цикле (иначе шедулер может подождать)."""
    # Нет открытых отделов — CEO должен открыть первый: даём циклу ход.
    open_depts = org.open_departments()
    if not open_depts:
        return True
    # Есть задача плана в ещё НЕ открытом отделе → нужен ход CEO, чтобы открыть его
    # (иначе дедлок: открытые отделы доделали своё и спят, а новый отдел не открывается).
    if plan.is_generated():
        if any(d not in open_depts for d in plan.departments_needed()):
            return True
        # Есть неустранимые «висячие» задачи (роль без отдела) → нужен ход, чтобы их закрыть.
        if has_orphan_tasks():
            return True
    now = time.time()
    return any(dept_actionable(did, now) for did in open_depts)


def free_worker_of_role(dept_id: str, role: str, now: float):
    """Свободный (idle, не в cooldown) работник нужной роли в отделе — или None."""
    for a in registry.members_of(dept_id):
        if a.role != role or a.status == "thinking":
            continue
        if (now - state.last_run_for(a.agent_id)) < AGENT_COOLDOWN_SECS:
            continue
        return a
    return None
