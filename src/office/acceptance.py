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

import re

from src.office import critic, workspace

# Роли, чья сдача обязана проходить Build-проверку кода
_CODING_ROLES = ("developer", "designer", "integrator")

# L1.5: роли, которым программно ЗАПРЕЩЕНО сдать спорное решение без реального
# вызова ask_user этим же агентом (см. докстринг у L1.5 ниже) — таблица, не
# цепочка if role == "...", тот же приём, что уже есть у ROLE_HOME/_NEED_WORDS/
# PRICES в этом кодбейзе (production-readiness worklist п.11: раньше единственная
# запись была захардкожена внутри if, добавить вторую роль под другой скилл
# значило трогать логику проверки, а не только данные). Сегодня реальный кейс
# ровно один (brand_book.md/designer) — не выдумываем гипотетические записи
# для architect/marketer без соответствующего скилла, который бы это требовал.
_MUST_ASK_BEFORE_ACCEPT: dict[str, str] = {
    "designer": ("дизайн-направление не подтверждено владельцем — прежде чем "
                 "сдавать, задай через ask_user вопрос с вариантами стиля "
                 "(см. скилл «Бренд-бук»), не выбирай направление сам"),
}

# Сдача-«реплика процесса» — модель отдала рассуждение вместо отчёта о сделанном
# (прод-кейс: задачи закрывались текстами «Давайте посмотрим на структуру сайта…»,
# «Теперь проверим файл offer.md…», «мне нужно уточнить у клиента…» — и сайт
# публиковался с этим текстом как описанием правки). Защита в llm.run_agent
# (преамбула ≠ результат) — первая линия; это — вторая, на случай если wrap-up
# вызов тоже вернул болтовню.
_PREAMBLE_RE = re.compile(
    r"(давайте\s+(посмотр|провер|изуч|начн)|теперь\s+(посмотр|провер|давайте)|"
    r"сейчас\s+(посмотрю|проверю|изучу)|мне нужно уточнить|для начала посмотр)",
    re.IGNORECASE)

# Реальный кейс (лог прогона 2026-07-17): integrator сдал задачу текстом «нужно
# получить от клиента номер счётчика Яндекс.Метрики — без него не смогу...» —
# приёмка её пропустила (это не пустая сдача и не «реплика процесса», а честный
# отчёт о блокере), задача закрылась «выполнена», а вопрос владельцу так и не
# был задан (ask_user не вызван). Отличаем «сказал, что нужно спросить» от
# «реально спросил» — если сдача заявляет потребность в данных от клиента, но
# ask_user этим агентом не вызывался, это не готовая сдача, а недоделанная.
_NEEDS_CLIENT_INPUT_RE = re.compile(
    r"(нужно (получить|узнать|уточнить|запросить) (от|у) клиент|"
    r"без (него|этого|номера|id|ключа) не (смогу|получится|подключ)|"
    r"нужен от клиента|нужен id|нужен ключ|нужен номер счётчика|"
    r"уточнить у (клиента|владельца))",
    re.IGNORECASE)


def _is_process_chatter(result: str) -> bool:
    """Сдача выглядит как реплика процесса, а не отчёт: обрывается на «:» (подводка
    к так и не сделанному) или короткий текст с «давайте посмотрим/проверим»."""
    r = (result or "").strip()
    if not r:
        return False
    if r.endswith(":"):
        return True
    return len(r) < 400 and bool(_PREAMBLE_RE.search(r))


def _site_touched_since(ts: float) -> bool:
    """Менялись ли ИСХОДНИКИ сайта после метки времени (агент реально трогал сайт).
    Для проекта со сборкой смотрим папку исходников (site_builder.detect), а не
    critic.site_dir(): тот для несобранного build-проекта возвращает None, и
    провал сборки никогда не доходил бы до приёмки виновной задачи."""
    from src.office import site_builder
    d = site_builder.detect()
    if d["kind"] == "build":
        sdir = d["root"]
    else:
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
    from src.office import site_builder
    return critic.site_dir() is not None or site_builder.detect()["kind"] == "build"


def _is_bot_task(artifacts: list[str]) -> bool:
    return "bot" in (artifacts or [])


def check(task_title: str, role: str, result: str,
          done_criterion: str = "", started_ts: float = 0.0,
          artifacts: list[str] | None = None, project_id: str = "",
          agent_id: str = "") -> dict:
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
    elif _is_process_chatter(result):
        problems.append("сдача — реплика процесса («давайте посмотрим…»/обрыв на «:»), "
                        "а не отчёт: напиши, ЧТО сделано и в каких файлах")
        levels["acceptance"] = "fail"
    elif _NEEDS_CLIENT_INPUT_RE.search(result or ""):
        from src.office import questions
        if not questions.asked_since(agent_id, started_ts):
            problems.append(
                "сдача заявляет, что нужны данные от клиента, но вопрос ему не "
                "задан — вызови ask_user с конкретным вопросом (не просто "
                "напиши об этом в отчёте), задача не готова, пока владелец не ответил")
            levels["acceptance"] = "fail"

    # L1 Specification: критерий готовности задачи сверяется с контрактом приёмки
    # (success_criteria). Расхождение — МЯГКОЕ предупреждение (не проваливает build/
    # functional), т.к. подтверждение владельца в v1 опционально (BOS §8 L1). Сигналит
    # работу вне согласованного контракта — задачи, добавленные после спецификации.
    from src.office import specification
    spec_status = specification.status(project_id)
    if spec_status and (done_criterion or "").strip():
        if specification.covers(done_criterion, project_id):
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

    # L1.5 Design confirmation (аудит логов 2026-07-17): brand_book.md/направление
    # стиля — решение ВЛАДЕЛЬЦА (см. builtin_skills/brand_book.md), не designer'а
    # самого по себе. Skill текстом требует ask_user, но LLM вправе его
    # проигнорировать — реальный прогон показал именно это: designer ни разу за
    # весь прогон не спросил и сдал стиль как решённый факт. Программный гейт,
    # не текстовая просьба — задача НЕ проходит приёмку без реального вызова
    # ask_user этим же агентом в рамках текущей попытки.
    ask_requirement = _MUST_ASK_BEFORE_ACCEPT.get(role)
    if ask_requirement:
        from src.office import questions
        if not questions.asked_since(agent_id, started_ts):
            problems.append(ask_requirement)

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
