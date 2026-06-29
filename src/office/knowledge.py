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


def note_result(department: str, role: str, summary: str) -> None:
    """Зафиксировать, что отдел сделал — короткий итог результата как факт."""
    summary = (summary or "").strip().replace("\n", " ")
    if not summary:
        return
    remember(f"{role} сделал: {summary[:200]}", department=department, tags="result")


# ─────────────────────────── сбор кандидатов ───────────────────────────

def _global_facts() -> list[dict]:
    """GLOBAL-слой из источников истины (brief + ответы пользователя)."""
    out: list[dict] = []
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


def _score(task_tokens: set[str], fact: dict) -> float:
    """База слоя + перекрытие ключевых слов задачи и факта (TF-подобно)."""
    f_tokens = _tokens(fact["text"])
    if not f_tokens:
        return fact.get("base", 0.0)
    overlap = len(task_tokens & f_tokens)
    rel = overlap / (len(f_tokens) ** 0.5 + 1.0) if overlap else 0.0
    return fact.get("base", 0.0) + rel


def retrieve(task: str, department: str = "", limit: int = _DEFAULT_LIMIT) -> list[str]:
    """Топ-N фактов (global + department), релевантных тексту задачи."""
    task_tokens = _tokens(task)
    candidates = _global_facts() + _department_facts(department)
    scored = [(_score(task_tokens, f), f["text"]) for f in candidates]
    scored = [(s, t) for s, t in scored if s > 0 and t]
    scored.sort(key=lambda x: x[0], reverse=True)
    seen, out = set(), []
    for _, text in scored:
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= limit:
            break
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
    dept = [{"text": f.get("text", ""), "layer": "department",
             "department": f.get("department", ""), "ts": f.get("ts", 0)}
            for f in _store().get("facts", [])]
    return glob + dept


def reset() -> None:
    ctx.delete_file(_FILE)
