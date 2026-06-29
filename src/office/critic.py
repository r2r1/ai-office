"""
Критик качества — приёмка результата работника перед тем, как считать задачу сделанной.

Сейчас лидер только маршрутизирует, но не оценивает результат: дизайнер мог сдать
сайт с битыми картинками и одной страницей — никто не проверил. Критик закрывает это:
программные проверки + (опционально) короткая LLM-оценка по чеклисту. Возвращает
список проблем; если он непуст — задача возвращается исполнителю с конкретикой.
"""

import re

from src.office import workspace


def _find_site_dir() -> str | None:
    """Папка с index.html в рабочей директории (или None)."""
    files = workspace.list_files()
    for f in files:
        p = f["path"]
        if p == "index.html":
            return ""
        if p.endswith("/index.html"):
            return p[: -len("/index.html")]
    return None


def site_dir() -> str | None:
    """Публичный доступ: папка собранного сайта (для авто-публикации офисом)."""
    return _find_site_dir()


def check_site() -> list[str]:
    """
    Программные проверки опубликованного/собранного сайта. Возвращает список проблем
    (пустой = всё ок). Дёшево, без LLM — ловит самые частые провалы.
    """
    site_dir = _find_site_dir()
    if site_dir is None:
        return ["Не найден index.html — сайт ещё не собран. Создай site/index.html через write_file."]

    problems: list[str] = []
    idx_path = f"{site_dir}/index.html" if site_dir else "index.html"
    html = workspace.read_file(idx_path)
    if not html or html.startswith("Файл не найден"):
        return ["index.html пустой или не читается — перепиши его полностью."]

    low = html.lower()
    files = [f["path"] for f in workspace.list_files()]
    in_dir = [p for p in files if (not site_dir) or p.startswith(site_dir + "/")]

    # 1. Внешние картинки часто не грузятся (Unsplash и т.п.) — требуем локальные/SVG.
    ext_imgs = re.findall(r'<img[^>]+src=["\']https?://[^"\']+', html, re.IGNORECASE)
    if ext_imgs:
        problems.append(
            f"Внешние картинки ({len(ext_imgs)} шт., напр. Unsplash) не грузятся и ломают вид — "
            "замени на встроенные SVG или CSS-градиентные блоки.")

    # 2. Одностраничник без отдельных файлов стиля — просим полноценную структуру.
    has_css_file = any(p.endswith(".css") for p in in_dir)
    has_inline_style = "<style" in low
    if not has_css_file and not has_inline_style:
        problems.append("Нет стилей вообще — добавь css/style.css или хотя бы <style>.")

    # 3. Форма должна слать заявки в нашу систему лидов.
    if "<form" in low and "/api/site-lead" not in low:
        problems.append("Форма не отправляет заявки на /api/site-lead — лиды не попадут в «Лиды».")
    if "<form" not in low:
        problems.append("Нет формы заявки — сайт не собирает лиды.")

    # 4. Базовая полнота: title и заметный объём контента.
    if "<title" not in low:
        problems.append("Нет <title> — добавь заголовок страницы.")
    if len(html) < 1500:
        problems.append("Слишком мало контента для лендинга — добавь секции (оффер, услуги, преимущества, отзывы).")

    # 5. Многостраничность приветствуется, но не блокирует (мягкая подсказка не нужна в проблемах).
    return problems


async def review_site_llm(goal: str) -> list[str]:
    """
    «Зрячая» самопроверка: LLM-ревьюер читает реальный HTML готового сайта и судит,
    достигает ли он цели клиента (ясность оффера, заметность CTA, доверие, тексты).
    Возвращает список КОНКРЕТНЫХ правок (пусто = сайт хорош). В отличие от check_site
    это не чек-лист, а профессиональная оценка результата.
    """
    sdir = _find_site_dir()
    if sdir is None:
        return []
    idx = f"{sdir}/index.html" if sdir else "index.html"
    html = workspace.read_file(idx)
    if not html or html.startswith("Файл не найден"):
        return []

    from src.core import llm
    from src.office import models as models_module
    import json
    import re

    sys = (
        "Ты — придирчивый, но конструктивный ревьюер конверсионных лендингов. Тебе дают HTML "
        "готового сайта и цель клиента. Оцени, реально ли сайт достигает цели: ясность оффера, "
        "заметность главного CTA, доверие, структура, качество текстов. Найди КОНКРЕТНЫЕ "
        "значимые недочёты (не мелкие придирки). Если сайт уже хорош — верни пустой список.\n"
        'Ответь ТОЛЬКО JSON: {"fixes": ["конкретное действие", ...]} — максимум 4 пункта, по-русски.'
    )
    user = f"Цель клиента: {goal}\n\nHTML сайта (фрагмент):\n{html[:9000]}"
    try:
        raw = await llm.run_agent(
            system=sys, user=user, model=models_module.for_agent("orchestrator_1"),
            max_tokens=500, use_search=False, agent_id="orchestrator_1",
        )
    except Exception:
        return []
    m = re.search(r"\{.*\}", raw or "", re.DOTALL)
    if not m:
        return []
    try:
        fixes = json.loads(m.group(0)).get("fixes", [])
        return [str(f)[:200] for f in fixes if f][:4]
    except Exception:
        return []


def check_bot() -> list[str]:
    """
    Проверка Telegram-бота: bot.py / main.py существует и содержит рабочую структуру.
    Возвращает список проблем (пустой = всё ок).
    """
    files = {f["path"]: f for f in workspace.list_files()}
    bot_path = next((p for p in ("bot.py", "main.py", "src/bot.py") if p in files), None)
    if bot_path is None:
        return ["Не найден файл бота (bot.py / main.py) — создай его через write_file."]

    code = workspace.read_file(bot_path)
    if not code or code.startswith("Файл не найден"):
        return [f"{bot_path} пустой или не читается — перепиши его полностью."]

    problems: list[str] = []
    low = code.lower()

    if "aiogram" not in low and "telebot" not in low and "telegram" not in low:
        problems.append(f"{bot_path}: не импортируется библиотека бота (aiogram / telebot).")
    if "token" not in low and "bot_token" not in low:
        problems.append(f"{bot_path}: нет переменной TOKEN / BOT_TOKEN — бот не сможет запуститься.")
    if "async def" not in low and "def " not in low:
        problems.append(f"{bot_path}: нет обработчиков сообщений (async def handler).")
    if len(code) < 300:
        problems.append(f"{bot_path}: слишком мало кода ({len(code)} символов) — добавь обработчики команд.")

    return problems


def check_python_files() -> list[str]:
    """
    Компиляция всех .py файлов в рабочей папке. Возвращает список ошибок.
    Дёшево, без LLM — ловит синтаксические ошибки до запуска.
    """
    import py_compile, tempfile, os
    problems: list[str] = []
    for f in workspace.list_files():
        if not f["path"].endswith(".py"):
            continue
        code = workspace.read_file(f["path"])
        if not code or code.startswith("Файл не найден"):
            continue
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".py",
                                             delete=False, encoding="utf-8") as tmp:
                tmp.write(code)
                tmp_path = tmp.name
            py_compile.compile(tmp_path, doraise=True)
        except py_compile.PyCompileError as e:
            problems.append(f"{f['path']}: синтаксическая ошибка — {str(e)[:120]}")
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
    return problems


def critique_text(problems: list[str]) -> str:
    """Человекочитаемый фидбэк исполнителю по сайту."""
    if not problems:
        return ""
    lines = "\n".join(f"- {p}" for p in problems)
    return ("⚠ Нужны небольшие правки. Исправь прямо в существующих файлах папки site/ "
            "(НЕ начинай с нуля, НЕ вызывай publish_site — офис опубликует сам):\n" + lines)


def critique_text_bot(problems: list[str]) -> str:
    """Человекочитаемый фидбэк исполнителю по боту."""
    if not problems:
        return ""
    lines = "\n".join(f"- {p}" for p in problems)
    return ("⚠ Нужны правки в боте. Прочитай файл через read_file, "
            "исправь проблемы, перезапись через write_file:\n" + lines)
