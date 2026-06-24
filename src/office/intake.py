"""
Интейк (discovery) — диалог уточнения ПЕРЕД запуском офиса. По тенанту.

Глупый офис строит вслепую. Умный — сначала задаёт уточняющие вопросы, собирает
ответы и только потом формирует бриф и начинает работу. Это состояние диалога
уточнения: idea (первичный запрос) + questions (что спросили) + answers (что ответил клиент).

Файл: data/tenants/<tid>/intake.json.
"""

from src.saas import context as ctx

_FILE = "intake.json"


def get() -> dict:
    return ctx.read_json(_FILE, {})


def active() -> bool:
    """Идёт ли сейчас уточнение (вопросы заданы, ждём/собираем ответы)."""
    return get().get("stage") == "questions"


def start(idea: str, questions: list[str]) -> None:
    ctx.write_json(_FILE, {"stage": "questions", "idea": idea, "questions": questions, "answers": []})


def add_answer(text: str) -> dict:
    st = get()
    if not st:
        st = {"stage": "questions", "idea": "", "questions": [], "answers": []}
    st.setdefault("answers", []).append(text.strip())
    ctx.write_json(_FILE, st)
    return st


def clear() -> None:
    ctx.delete_file(_FILE)


def reset() -> None:
    clear()


def load() -> None:
    pass
