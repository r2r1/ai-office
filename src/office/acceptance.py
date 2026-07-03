"""
Acceptance Layer — задача закрывается ТОЛЬКО приёмкой (BOS §8).

Раньше «done» означало «агент вернул непустую строку» — система не отличала
работу от рассказа о работе. Теперь между Execution и Done стоит приёмка:

  L1 Specification — контракт сформирован (specification.py; не блокирует v1)
  L2 Build         — код собирается: py_compile + node --check (workspace.verify)
  L3 Functional    — артефакт работает: критические проблемы сайта / бота (critic)
  L4 Business      — соответствие целям (v1: заметка, не блокирует — ждёт метрик)
  L5 Acceptance    — сдача не пустая; вердикт с перечнем проблем

Уровни ПРИМЕНИМЫЕ к задаче выбираются детерминированно по роли/содержанию —
не-сайтовая текстовая задача не гоняется через критика сайтов. Все проверки
здесь детерминированные (LLM-ревью сайта остаётся в _review_and_maybe_fix —
одна доработка до приёмки, чтобы не жечь токены на каждом гейте).

Вердикт пишется в саму задачу (поле acceptance) — виден в UI и History.
"""

from src.office import critic, workspace

# Роли, чья сдача обязана проходить Build-проверку кода
_CODING_ROLES = ("developer", "designer", "integrator")

_SITE_WORDS = ("сайт", "лендинг", "landing", "site", "страниц")
_BOT_WORDS = ("бот", "bot", "telegram", "телеграм")


def _site_touched_since(ts: float) -> bool:
    """Менялись ли файлы папки сайта после метки времени (агент реально трогал сайт)."""
    sdir = critic.site_dir()
    if sdir is None:
        return False
    prefix = f"{sdir}/" if sdir else ""
    for f in workspace.list_files():
        if (not prefix or f["path"].startswith(prefix)) and f.get("mtime", 0) >= ts:
            return True
    return False


def _is_site_task(task_title: str, role: str, started_ts: float = 0.0) -> bool:
    t = (task_title or "").lower()
    if any(w in t for w in _SITE_WORDS):
        return True
    # designer/developer без бот-слов почти всегда работают по site/ (тот же
    # инвертированный принцип, что в plan.touches_site). Но роль-эвристика при
    # известном started_ts требует, чтобы сайт РЕАЛЬНО трогали в этой задаче —
    # иначе критические проблемы, оставленные ЧУЖОЙ задачей, валили приёмку
    # несвязанной работы (кросс-контаминация: 3 провала → блок невиновной задачи).
    if role not in ("designer", "developer") or any(w in t for w in _BOT_WORDS):
        return False
    if started_ts > 0:
        return _site_touched_since(started_ts)
    return critic.site_dir() is not None


def _is_bot_task(task_title: str) -> bool:
    return any(w in (task_title or "").lower() for w in _BOT_WORDS)


def check(task_title: str, role: str, result: str,
          done_criterion: str = "", started_ts: float = 0.0) -> dict:
    """
    Приёмка сдачи задачи. Возвращает:
      {"passed": bool, "problems": [...], "levels": {level: "ok"|"fail"|"skip"}}

    `started_ts` — момент старта задачи: Build проверяет только файлы, изменённые
    ЭТОЙ задачей, а роль-эвристика сайта требует реального касания site/ —
    чужой битый артефакт не валит приёмку невиновной задачи. Задачи с сайтом
    в ЗАГОЛОВКЕ проверяются по сайту всегда (явная ответственность).
    """
    problems: list[str] = []
    levels: dict[str, str] = {"build": "skip", "functional": "skip", "acceptance": "ok"}

    # L5 (базовый): пустая сдача — не результат (обрыв/только tool-calls)
    if not (result or "").strip():
        problems.append("пустая сдача — агент не вернул результат")
        levels["acceptance"] = "fail"

    # L2 Build: код обязан собираться (py + js/esm) — файлы, тронутые этой задачей
    if role in _CODING_ROLES and workspace.list_files():
        v = workspace.verify(changed_since=started_ts)
        levels["build"] = "ok" if v.get("ok") else "fail"
        problems += [f"код: {e}" for e in v.get("errors", [])[:3]]

    # L3 Functional: сайт/бот — критические проблемы артефакта
    if _is_bot_task(task_title):
        bot_problems = critic.check_bot()
        levels["functional"] = "fail" if bot_problems else "ok"
        problems += [f"бот: {p}" for p in bot_problems[:3]]
    elif _is_site_task(task_title, role, started_ts):
        site_critical = [p for p in critic.check_site() if critic.is_critical(p)]
        levels["functional"] = "fail" if site_critical else "ok"
        problems += [f"сайт: {p}" for p in site_critical[:3]]

    return {"passed": not problems, "problems": problems, "levels": levels}


def feedback_text(verdict: dict) -> str:
    """Человекочитаемая обратная связь для повторной попытки исполнителя."""
    if verdict.get("passed"):
        return ""
    lines = "\n".join(f"- {p}" for p in verdict.get("problems", [])[:5])
    return ("⚠ ПРИЁМКА НЕ ПРОЙДЕНА. Устрани проблемы (правь ТОЧЕЧНО существующие "
            f"файлы через read_file → write_file, не начинай с нуля):\n{lines}")
