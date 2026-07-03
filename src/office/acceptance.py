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


def _is_site_task(artifacts: list[str], started_ts: float = 0.0) -> bool:
    """Задача производит артефакт «site» (BOS §12: тип берётся из ДЕКЛАРАЦИИ задачи,
    а не из слов заголовка). Роль-декларация «site» при известном started_ts ещё
    требует реального касания site/ в этой задаче — иначе критические проблемы,
    оставленные ЧУЖОЙ задачей, валили приёмку несвязанной работы (кросс-контаминация:
    3 провала → блок невиновной задачи)."""
    if "site" not in (artifacts or []):
        return False
    if started_ts > 0:
        return _site_touched_since(started_ts)
    return critic.site_dir() is not None


def _is_bot_task(artifacts: list[str]) -> bool:
    return "bot" in (artifacts or [])


def check(task_title: str, role: str, result: str,
          done_criterion: str = "", started_ts: float = 0.0,
          artifacts: list[str] | None = None) -> dict:
    """
    Приёмка сдачи задачи. Возвращает:
      {"passed": bool, "problems": [...], "levels": {level: "ok"|"fail"|"skip"}}

    `artifacts` — ДЕКЛАРАЦИЯ артефактов задачи (plan.artifacts_of): по ней выбираются
    уровни L3 (site/bot), а не по словам заголовка (BOS §12). `started_ts` — момент
    старта: Build проверяет только файлы этой задачи, а site-декларация требует
    реального касания site/ — чужой битый артефакт не валит приёмку невиновной задачи.
    """
    artifacts = artifacts or []
    problems: list[str] = []
    warnings: list[str] = []
    levels: dict[str, str] = {"specification": "skip", "build": "skip",
                              "functional": "skip", "business": "skip", "acceptance": "ok"}

    # L5 (базовый): пустая сдача — не результат (обрыв/только tool-calls)
    if not (result or "").strip():
        problems.append("пустая сдача — агент не вернул результат")
        levels["acceptance"] = "fail"

    # L1 Specification: критерий готовности задачи сверяется с контрактом приёмки
    # (success_criteria). Расхождение — МЯГКОЕ предупреждение (не проваливает build/
    # functional), т.к. подтверждение владельца в v1 опционально (BOS §8 L1). Сигналит
    # работу вне согласованного контракта — задачи, добавленные после спецификации.
    from src.office import specification
    spec_status = specification.status()
    if spec_status and (done_criterion or "").strip():
        if specification.covers(done_criterion):
            levels["specification"] = "ok"
        else:
            levels["specification"] = "warn"
            warnings.append(
                "критерий готовности задачи не совпадает с контрактом приёмки "
                "(success_criteria спецификации) — работа вне согласованного объёма")

    # L2 Build: код обязан собираться (py + js/esm) — файлы, тронутые этой задачей
    if role in _CODING_ROLES and workspace.list_files():
        v = workspace.verify(changed_since=started_ts)
        levels["build"] = "ok" if v.get("ok") else "fail"
        problems += [f"код: {e}" for e in v.get("errors", [])[:3]]

    # L3 Functional: сайт/бот — критические проблемы артефакта (по декларации)
    if _is_bot_task(artifacts):
        bot_problems = critic.check_bot()
        levels["functional"] = "fail" if bot_problems else "ok"
        problems += [f"бот: {critic.text_of(p)}" for p in bot_problems[:3]]
    elif _is_site_task(artifacts, started_ts):
        site_critical = [p for p in critic.check_site() if critic.is_critical(p)]
        levels["functional"] = "fail" if site_critical else "ok"
        problems += [f"сайт: {critic.text_of(p)}" for p in site_critical[:3]]

    # L4 Business (BOS §8): двигает ли сдача к цели. ТОЛЬКО для задач-поставок
    # (site/bot) и ТОЛЬКО информационно — попадание в цель оценивается по метрике,
    # которая наполнится ПОСЛЕ сдачи, поэтому L4 не гейт («сделано» ≠ «цель закрыта»).
    if any(a in artifacts for a in ("site", "bot")):
        from src.office import gap
        unmet_gaps = gap.unmet()
        if unmet_gaps:
            levels["business"] = "open"
            warnings.append(
                "цель ещё не достигнута (" + "; ".join(
                    f"{g['title']}: {g['current']}/{g['desired']}" for g in unmet_gaps[:2])
                + ") — работа сдана, но разрыв к цели открыт")
        elif gap.compute():
            levels["business"] = "ok"

    # Уверенность приёмки — модификатор от статуса контракта (не гейт): подтверждённая
    # владельцем спецификация без предупреждений → high; черновик или расхождение → ниже.
    if warnings or spec_status == "draft":
        confidence = "normal"
    elif spec_status == "confirmed":
        confidence = "high"
    else:
        confidence = "normal"

    return {"passed": not problems, "problems": problems, "warnings": warnings,
            "levels": levels, "confidence": confidence}


def feedback_text(verdict: dict) -> str:
    """Человекочитаемая обратная связь для повторной попытки исполнителя."""
    if verdict.get("passed"):
        return ""
    lines = "\n".join(f"- {p}" for p in verdict.get("problems", [])[:5])
    return ("⚠ ПРИЁМКА НЕ ПРОЙДЕНА. Устрани проблемы (правь ТОЧЕЧНО существующие "
            f"файлы через read_file → write_file, не начинай с нуля):\n{lines}")
