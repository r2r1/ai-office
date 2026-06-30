"""
Совет директоров — виртуальный механизм разрешения конфликтов.

Собирается автоматически при:
- CEO повторяет «wait» 3+ раз подряд (антицикл с эскалацией)
- Event типа «blocker» с приоритетом HIGH остаётся необработанным 2+ цикла
- Два отдела подают конфликтующие события об одной проблеме

Сценарий: CEO опрашивает лидера каждого открытого отдела (mini-LLM вызов),
собирает позиции, принимает итоговое решение и логирует в decisions.py.
"""

import time
from src.saas import context as ctx


def _load() -> dict:
    return ctx.read_json("board", None) or {"sessions": [], "wait_streak": 0, "last_session_ts": 0}


def _save(d: dict) -> None:
    ctx.write_json("board", d)


# ── Детекторы необходимости совета ──────────────────────────────────────────

def record_wait() -> None:
    """Вызывается каждый раз, когда CEO решает 'wait'."""
    d = _load()
    d["wait_streak"] = d.get("wait_streak", 0) + 1
    _save(d)


def reset_wait_streak() -> None:
    d = _load()
    d["wait_streak"] = 0
    _save(d)


def needs_session_by_wait() -> bool:
    d = _load()
    streak = d.get("wait_streak", 0)
    last = d.get("last_session_ts", 0)
    # 2+ подряд wait и совет не собирался последние 15 мин (был 3/30 — слишком редко)
    return streak >= 2 and (time.time() - last > 900)


def needs_session_by_blockers() -> bool:
    """Есть нерешённые блокеры старше 2 циклов (>60 сек)."""
    from src.office import events as events_mod
    now = time.time()
    stale_blockers = [
        e for e in events_mod.pending()
        if e.get("kind") == "blocker" and (now - e.get("ts", now)) > 60
    ]
    return len(stale_blockers) >= 1


def needs_session() -> bool:
    return needs_session_by_wait() or needs_session_by_blockers()


# ── Проведение сессии совета ─────────────────────────────────────────────────

async def run_session(conflict_summary: str, publish) -> dict:
    """
    Проводит сессию совета директоров.
    1. Опрашивает лидера каждого открытого отдела (mini-LLM без инструментов).
    2. CEO собирает позиции и принимает финальное решение.
    3. Логирует в decisions.py.
    Возвращает финальное решение CEO.
    """
    from src.office import org as org_mod
    from src.agents import orchestrator
    from src.office import decisions as decisions_mod
    from src.core import llm

    await publish({"type": "system", "text": f"🏛️ Совет директоров — {conflict_summary[:80]}"})

    open_depts = org_mod.open_departments()
    positions: dict[str, str] = {}

    for dept_id in open_depts:
        lead_title = org_mod.lead_title(dept_id)
        lead_role = org_mod.lead_role(dept_id)
        dept_name = org_mod.catalog().get(dept_id, {}).get("name", dept_id)
        hint = org_mod.catalog().get(dept_id, {}).get("hint", "")
        system = (
            f"Ты — {lead_title} ({dept_name}). {hint}. "
            "Дай короткую позицию (2-3 предложения) по вопросу: "
            "какое решение наилучшим образом поможет компании и твоему отделу."
        )
        try:
            pos = await llm.run_agent(
                system=system,
                user=f"Вопрос на совете: {conflict_summary}",
                max_tokens=300,
                use_search=False,
                agent_id=f"{lead_role}_board",
            )
            positions[dept_id] = pos
            await publish({
                "type": "speech",
                "agent_id": f"{lead_role}_1",
                "text": f"📋 [{lead_title}]: {pos[:200]}",
            })
        except Exception:
            positions[dept_id] = "(нет ответа)"

    # CEO принимает итоговое решение с позициями всех отделов
    decision = await orchestrator.board_decide(conflict_summary, positions, publish)

    # Логируем в историю
    did = decisions_mod.record(
        action="board_decision",
        target=conflict_summary[:100],
        thought=decision.get("conclusion", ""),
        alternatives=[{"dept": k, "position": v[:200]} for k, v in positions.items()],
        confidence=decision.get("confidence", 60),
        risks=decision.get("risks", []),
        expected_effect=decision.get("expected_effect", ""),
        data_used=["board_session", f"dept_positions:{len(positions)}"],
        made_by="board",
    )
    decision["decision_id"] = did

    # Сбрасываем streak и запоминаем время сессии
    d = _load()
    d["wait_streak"] = 0
    d["last_session_ts"] = time.time()
    sessions = d.get("sessions") or []
    sessions.append({"ts": time.time(), "conflict": conflict_summary[:100], "decision_id": did})
    d["sessions"] = sessions[-20:]
    _save(d)

    await publish({"type": "system",
                   "text": f"🏛️ Решение совета: {decision.get('conclusion', '')[:150]}"})
    return decision


def recent_sessions(n: int = 5) -> list:
    return list(reversed((_load().get("sessions") or [])[-n:]))

