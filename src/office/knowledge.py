"""
Трёхслойная память офиса с подбором релевантного в контекст (per-tenant).

Идея (moat): агенты не должны «забывать» контекст между циклами и не должны
тонуть в простыне «всё в промпт». Поэтому память разделена на слои, а в задачу
агента кладётся НЕ всё подряд, а топ-N фактов, релевантных ИМЕННО этой задаче.

Слои:
  GLOBAL     — факты о бизнесе клиента: цель, ниша, ограничения и (главное!)
               ОТВЕТЫ ПОЛЬЗОВАТЕЛЯ. Стабильны и приоритетны (указания клиента
               главнее стратегии/ТЗ — см. инварианты в CLAUDE.md).
  DEPARTMENT — что отдел уже узнал/сделал: краткие итоги результатов и явно
               записанные знания. Копится в knowledge.json.
  RETRIEVAL  — не хранилище, а способ ПОДАЧИ: `context_block()` ранжирует все
               кандидаты по близости к тексту задачи и отдаёт лучшие.

GLOBAL-слой не дублируется в хранилище — он читается из источников истины
(`brief`, `memory`), чтобы не было рассинхрона. Своё хранилище только у
DEPARTMENT-слоя: data/tenants/<tid>/knowledge.json
  {"facts": [ {text, department, tags, ts}, ... ]}.
"""

import time

from src.saas import context as ctx
from src.office import brief, memory

_FILE = "knowledge.json"
_MAX_FACTS = 60          # потолок хранилища department-знаний
_DEFAULT_LIMIT = 6       # сколько фактов класть в контекст задачи

# Стоп-слова: не несут смысла для подбора релевантности (рус + англ).
_STOP = {
    "и", "в", "во", "на", "с", "со", "по", "для", "что", "как", "это", "от",
    "до", "из", "за", "о", "об", "у", "к", "же", "ли", "бы", "не", "ни", "а",
    "но", "или", "то", "так", "уже", "ещё", "его", "их", "она", "они", "мы",
    "вы", "ты", "я", "тебе", "твоя", "твой", "нужно", "надо", "есть", "быть",
    "the", "a", "an", "to", "of", "in", "on", "for", "and", "or", "is", "are",
    "be", "it", "this", "that", "with", "as", "by", "at", "from",
}


# ─────────────────────────── хранилище department ───────────────────────────

def _store() -> dict:
    return ctx.read_json(_FILE, {"facts": []})


def remember(text: str, department: str = "", tags: str = "") -> None:
    """Записать факт department-знания (с дедупликацией по тексту)."""
    text = (text or "").strip()
    if not text:
        return
    data = _store()
    facts = data.setdefault("facts", [])
    norm = text.lower()
    if any((f.get("text") or "").lower() == norm for f in facts):
        return
    facts.append({"text": text[:280], "department": department or "",
                  "tags": tags or "", "ts": time.time()})
    data["facts"] = facts[-_MAX_FACTS:]
    ctx.write_json(_FILE, data)


_MAX_RESULTS = 20        # отдельный небольшой журнал результатов (не «знания»)


def note_result(department: str, role: str, summary: str) -> None:
    """
    Зафиксировать, что отдел сделал — в ОТДЕЛЬНЫЙ журнал результатов, НЕ в знания.
    Раньше каждый результат писался как retrievable-факт и за прогон вытеснял из окна
    60 реальные знания; retrieval потом подсовывал «developer сделал X» вместо сути (A5).
    """
    summary = (summary or "").strip().replace("\n", " ")
    if not summary:
        return
    data = _store()
    results = data.setdefault("results", [])
    line = f"{role} сделал: {summary[:200]}"
    if any((r.get("text") or "") == line for r in results):
        return
    results.append({"text": line, "department": department or "", "ts": time.time()})
    data["results"] = results[-_MAX_RESULTS:]
    ctx.write_json(_FILE, data)


# ─────────────────────────── сбор кандидатов ───────────────────────────

def _global_facts() -> list[dict]:
    """GLOBAL-слой из источников истины (brief + ответы пользователя + философия/конституция)."""
    out: list[dict] = []

    # Философия и Конституция — наивысший приоритет, выше стратегии и ТЗ
    try:
        from src.office import philosophy as phil_mod, constitution as const_mod
        phil_block = phil_mod.context_block()
        if phil_block:
            out.append({"text": phil_block, "base": 0.95, "src": "global"})
        const_block = const_mod.rule_block()
        if const_block:
            out.append({"text": const_block, "base": 0.90, "src": "global"})
    except Exception:
        pass

    b = brief.get()
    if b.get("goal"):
        out.append({"text": f"Цель клиента: {b['goal']}", "base": 0.35, "src": "global"})
    if b.get("niche"):
        out.append({"text": f"Ниша: {b['niche']}", "base": 0.3, "src": "global"})
    for key in ("constraints", "avoid", "notes", "preferences"):
        val = b.get(key)
        if val:
            out.append({"text": f"Ограничение/пожелание клиента: {val}",
                        "base": 0.55, "src": "global"})
    # Ответы пользователя — самый приоритетный слой (указания клиента главнее всего).
    for e in memory.all_entries():
        ans = (e.get("answer") or "").strip()
        if not ans:
            continue
        q = (e.get("question") or "").strip()
        txt = f"Клиент ответил на «{q[:80]}»: {ans[:160]}" if q else f"Клиент сказал: {ans[:200]}"
        out.append({"text": txt, "base": 0.5, "src": "user"})
    return out


def _department_facts(department: str) -> list[dict]:
    """DEPARTMENT-слой: знания своего отдела важнее, чужого — фоном."""
    out: list[dict] = []
    for f in _store().get("facts", []):
        same = department and f.get("department") == department
        out.append({"text": f.get("text", ""),
                    "base": 0.18 if same else 0.06, "src": "dept"})
    return out


# ─────────────────────────── ранжирование ───────────────────────────

def _tokens(s: str) -> set[str]:
    words = "".join(c.lower() if c.isalnum() else " " for c in (s or "")).split()
    return {w for w in words if len(w) > 2 and w not in _STOP}


def _result_facts(department: str) -> list[dict]:
    """Недавние результаты отдела — кандидаты с НИЗКИМ базовым весом (фон, не знания)."""
    out: list[dict] = []
    for r in _store().get("results", [])[-8:]:
        same = department and r.get("department") == department
        out.append({"text": r.get("text", ""), "base": 0.05 if same else 0.02, "src": "result"})
    return out


# Сколько слотов из limit ЗАРЕЗЕРВИРОВАНО под важное глобальное (философия/конституция/
# указания клиента), чтобы оно не вытеснялось, но и НЕ забивало всю выдачу (A4).
_RESERVED_GLOBAL = 2


def retrieve(task: str, department: str = "", limit: int = _DEFAULT_LIMIT) -> list[str]:
    """
    Топ-N фактов под задачу. Раньше глобальные факты (base 0.9+) всегда доминировали и
    съедали все слоты — релевантность почти не работала. Теперь: ≤2 слота резервируем
    под самое важное глобальное (по base), а ОСТАЛЬНОЕ ранжируем по ЧИСТОЙ релевантности
    к задаче (перекрытие ключевых слов), а не по base.
    """
    task_tokens = _tokens(task)
    globals_ = _global_facts()

    # 1) Резерв под важное глобальное — по базовому приоритету (философия/конституция/
    #    ограничения/ответы клиента идут первыми и не вытесняются).
    reserved = sorted(globals_, key=lambda f: f.get("base", 0.0), reverse=True)[:_RESERVED_GLOBAL]
    out, seen = [], set()
    for f in reserved:
        key = f["text"].lower()
        if f["text"] and key not in seen:
            seen.add(key)
            out.append(f["text"])

    # 2) Остальное — по релевантности (перекрытие токенов), а не по base слоя.
    rest = [f for f in (globals_ + _department_facts(department) + _result_facts(department))
            if f["text"].lower() not in seen]
    def _relevance(f: dict) -> float:
        f_tokens = _tokens(f["text"])
        if not f_tokens:
            return 0.0
        overlap = len(task_tokens & f_tokens)
        return (overlap / (len(f_tokens) ** 0.5 + 1.0)) + 0.001 * f.get("base", 0.0)
    for f in sorted(rest, key=_relevance, reverse=True):
        if len(out) >= limit:
            break
        if _relevance(f) <= 0:
            continue
        key = f["text"].lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(f["text"])
    return out


def context_block(task: str, department: str = "", limit: int = _DEFAULT_LIMIT) -> str:
    """Готовый блок «что мы знаем по этой задаче» для промпта (или '')."""
    facts = retrieve(task, department=department, limit=limit)
    if not facts:
        return ""
    lines = "\n".join(f"- {t}" for t in facts)
    return ("\n=== ЧТО ОФИС УЖЕ ЗНАЕТ (учитывай, указания клиента — главнее всего) ===\n"
            f"{lines}\n")


# ─────────────────────────── сервис ───────────────────────────

def all_facts() -> list[dict]:
    """Все факты для UI/инспекции: department-хранилище + срез global."""
    glob = [{"text": f["text"], "layer": f["src"], "department": ""}
            for f in _global_facts()]
    store = _store()
    dept = [{"text": f.get("text", ""), "layer": "department",
             "department": f.get("department", ""), "ts": f.get("ts", 0)}
            for f in store.get("facts", [])]
    results = [{"text": r.get("text", ""), "layer": "result",
                "department": r.get("department", ""), "ts": r.get("ts", 0)}
               for r in store.get("results", [])]
    return glob + dept + results


def reset() -> None:
    ctx.delete_file(_FILE)
