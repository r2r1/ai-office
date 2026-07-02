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
    """
    Папка с index.html в рабочей директории (или None). Канонический сайт всегда
    живёт в site/ — проверяем её ПЕРВОЙ явным приоритетом. Иначе случайно созданный
    index.html в корне (агент забыл префикс site/ при write_file) хайджекает
    авто-публикацию и приёмку: они начинают читать/публиковать не ту версию сайта,
    а реальный собранный сайт в site/ остаётся невидимым клиенту.
    """
    paths = {f["path"] for f in workspace.list_files()}
    if "site/index.html" in paths:
        return "site"
    for p in sorted(paths):
        if p == "index.html":
            return ""
        if p.endswith("/index.html"):
            return p[: -len("/index.html")]
    return None


def site_dir() -> str | None:
    """Публичный доступ: папка собранного сайта (для авто-публикации офисом)."""
    return _find_site_dir()


def _site_files(site_dir: str) -> list[str]:
    """Все файлы внутри папки сайта."""
    files = [f["path"] for f in workspace.list_files()]
    return [p for p in files if (not site_dir) or p.startswith(site_dir + "/")]


def _read(path: str) -> str:
    c = workspace.read_file(path)
    return "" if (not c or c.startswith("Файл не найден")) else c


def _basename(path: str) -> str:
    return path.rsplit("/", 1)[-1]


def check_site() -> list[str]:
    """
    Программный тестировщик собранного сайта — как ручная проверка инженера, но
    детерминированно и без LLM. Проверяет НЕ только index, а ВСЕ страницы: структуру
    HTML, целостность ссылок, рабочесть форм на каждой странице, синтаксис JS (реальный
    node --check), дубли/заглушки, базовую доступность. Возвращает список проблем.
    """
    site_dir = _find_site_dir()
    if site_dir is None:
        return ["Не найден index.html — сайт ещё не собран. Создай site/index.html через write_file."]

    idx_path = f"{site_dir}/index.html" if site_dir else "index.html"
    html = _read(idx_path)
    if not html:
        return ["index.html пустой или не читается — перепиши его полностью."]

    problems: list[str] = []
    in_dir = _site_files(site_dir)
    html_pages = [p for p in in_dir if p.endswith(".html")]
    js_files = [p for p in in_dir if p.endswith(".js")]
    existing_names = {_basename(p) for p in in_dir}
    low = html.lower()

    # Общий JS всех страниц (fetch формы часто в отдельном script.js).
    js_blob = "\n".join(_read(p).lower() for p in js_files)

    # 1. Внешние картинки часто не грузятся (Unsplash и т.п.) — требуем локальные/SVG.
    ext_imgs = re.findall(r'<img[^>]+src=["\']https?://[^"\']+', html, re.IGNORECASE)
    if ext_imgs:
        problems.append(
            f"Внешние картинки ({len(ext_imgs)} шт., напр. Unsplash) не грузятся и ломают вид — "
            "замени на встроенные SVG или CSS-градиентные блоки.")

    # 2. Стили должны быть.
    if not any(p.endswith(".css") for p in in_dir) and "<style" not in low:
        problems.append("Нет стилей вообще — добавь css/style.css или хотя бы <style>.")

    # 3. index: title и объём.
    if "<title" not in low:
        problems.append("Нет <title> у главной — добавь заголовок страницы.")
    if len(html) < 1200:
        problems.append("Слишком мало контента на главной — добавь секции (оффер, услуги, преимущества, отзывы).")

    # 4. ФОРМЫ на КАЖДОЙ странице реально шлют на /api/site-lead (не только index).
    stub_markers = ("подключаем crm", "подключаем эндпоинт", "готово к отправке",
                    "эндпоинт скоро", "заглушк", "todo", "coming soon")
    pages_with_form = [p for p in html_pages if "<form" in _read(p).lower()]
    if not pages_with_form:
        problems.append("Нет формы заявки ни на одной странице — сайт не собирает лиды.")
    for p in pages_with_form:
        page_low = _read(p).lower()
        sends = "/api/site-lead" in page_low or "/api/site-lead" in js_blob
        if not sends:
            problems.append(f"{_basename(p)}: форма не отправляет заявки на /api/site-lead — лиды теряются.")
        elif any(s in (page_low + js_blob) for s in stub_markers) and "/api/site-lead" not in page_low:
            problems.append(f"{_basename(p)}: форма-заглушка (фраза «подключаем/готово»), реальной отправки нет.")

    # 5. ЦЕЛОСТНОСТЬ ССЫЛОК: каждая внутренняя ссылка ведёт на существующий файл.
    broken = set()
    for p in html_pages:
        for href in re.findall(r'href=["\']([^"\'#?]+\.html)[^"\']*["\']', _read(p), re.IGNORECASE):
            target = _basename(href.strip("/"))
            if target and target not in existing_names:
                broken.add(f"{_basename(p)} → {target}")
    if broken:
        problems.append(f"Битые внутренние ссылки на несуществующие страницы: {'; '.join(sorted(broken)[:5])}.")

    # 6. СТРУКТУРА HTML каждой страницы: базовый каркас + мобильный viewport + lang.
    for p in html_pages:
        c = _read(p).lower()
        if not c:
            continue
        if "<html" not in c or "<body" not in c:
            problems.append(f"{_basename(p)}: сломан каркас HTML (нет <html>/<body>).")
        if "viewport" not in c:
            problems.append(f"{_basename(p)}: нет мета viewport — сайт сломан на телефоне.")
        if "<html" in c and "lang=" not in c:
            problems.append(f"{_basename(p)}: у <html> нет lang — важно для доступности/SEO.")

    # 7. ЗАГЛУШКИ/ДУБЛИ: пустые страницы и свалка почти одинаковых файлов.
    for p in html_pages:
        c = _read(p)
        # ВАЖНО: не матчим слово "placeholder" — это HTML-атрибут инпутов, а не заглушка.
        # Признак заглушки: крошечный файл или lorem/явная пометка «заглушка».
        text_only = re.sub(r"<[^>]+>", "", c)
        if len(c) < 500 or "lorem ipsum" in c.lower() or "текст-заглушка" in c.lower() \
                or len(text_only.strip()) < 200:
            problems.append(f"{_basename(p)}: страница-заглушка/пустая — доделай или удали.")
    dup = _near_duplicate_pages(html_pages)
    if dup:
        problems.append(f"Много почти одинаковых страниц ({dup}) — это свалка дублей, "
                        "оставь по одной на смысл, остальные удали.")

    # 8. JS-СИНТАКСИС: реальный прогон node --check (как ручная проверка), если node есть.
    for p in js_files:
        err = _js_syntax_error(_read(p))
        if err:
            problems.append(f"{_basename(p)}: JS-ошибка синтаксиса — {err[:100]}")

    # 9. ДОСТУПНОСТЬ (базово): картинки без alt.
    imgs_no_alt = 0
    for p in html_pages:
        imgs_no_alt += len([m for m in re.findall(r'<img\b[^>]*>', _read(p), re.IGNORECASE)
                            if 'alt=' not in m.lower()])
    if imgs_no_alt:
        problems.append(f"Картинки без alt ({imgs_no_alt} шт.) — добавь alt для доступности/SEO.")

    # 10. ФЕЙКОВОЕ 3D: страница заявляет «3D», но это статичная CSS-плашка без движения.
    text_only_full = re.sub(r"<[^>]+>", " ", re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html,
                             flags=re.IGNORECASE | re.DOTALL))
    fake_3d = _fake_3d_problem(text_only_full, low, js_blob)
    if fake_3d:
        problems.append(fake_3d)

    return problems


_CLAIMS_3D_RE = re.compile(r"(?<![a-zа-я0-9])3d(?:[-\s]|$)", re.IGNORECASE)


def _fake_3d_problem(text_only: str, low_html: str, js_blob: str) -> str | None:
    """
    Скилл framer_motion_3d_site требует минимум 2 живых эффекта (mousemove-tilt,
    scroll-параллакс) — статичный `transform: rotateX(...)` без обработчиков
    считается «плашкой», а не 3D (см. playbook в skills.py). Реальный кейс: агент
    писал "3D-концепт"/"3D-сайт"/"3D-эффекты"/"3D-подача" в тексте страницы, но
    кроме слова "3D" в копирайте ничего не было — критик это пропускал.
    Матчим по регэксу (любое "3D" как отдельное слово в ВИДИМОМ тексте, не в CSS/
    JS/атрибутах — иначе ловим случайные "3d5a80" из hex-цветов), а не по списку
    фиксированных фраз: список фраз не поймал "3D-сайт"/"3D-подача" (реальный
    кейс — публикация ai-office-log-20260702_134612).
    """
    if not _CLAIMS_3D_RE.search(text_only):
        return None

    blob = low_html + "\n" + js_blob
    has_framer = "framer-motion" in blob or "importmap" in blob
    has_live_js = bool(re.search(r"addeventlistener\(['\"](mousemove|scroll)", blob)) \
        or "intersectionobserver" in blob \
        or "requestanimationframe" in blob
    if has_framer or has_live_js:
        return None
    return ("Заявлен «3D», но это статичная CSS-плашка без движения (нет framer-motion/importmap "
            "и нет JS-обработчиков mousemove/scroll) — по правилам скилла это не считается 3D. "
            "Либо добавь настоящие живые эффекты (tilt за курсором + scroll-параллакс), "
            "либо убери упоминания «3D» из текста.")


def _near_duplicate_pages(pages: list[str]) -> int:
    """Число страниц, у которых есть почти-дубль (перекрытие текста ≥ 0.85). Ловит
    свалку из клонов вроде kuhnya.html / kuhnya-kmv.html / kuhnya-vannaya.html."""
    def toks(path: str) -> set[str]:
        text = re.sub(r"<[^>]+>", " ", _read(path)).lower()
        return {w for w in re.split(r"[^\wа-яё]+", text) if len(w) > 3}
    tokmap = {p: toks(p) for p in pages}
    dupes = set()
    items = list(tokmap.items())
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            a, b = items[i][1], items[j][1]
            if not a or not b:
                continue
            jacc = len(a & b) / len(a | b)
            if jacc >= 0.85:
                dupes.add(items[i][0])
                dupes.add(items[j][0])
    return len(dupes)


def _js_syntax_error(code: str) -> str:
    """Проверяет JS через `node --check` (реальный парсер). '' если ок или node недоступен."""
    if not code.strip():
        return ""
    import shutil
    if not shutil.which("node"):
        return ""  # node нет на сервере — тихо пропускаем (не ложная тревога)
    import subprocess, tempfile, os
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".js", delete=False, encoding="utf-8") as f:
            f.write(code)
            tmp = f.name
        r = subprocess.run(["node", "--check", tmp], capture_output=True, text=True, timeout=15)
        if r.returncode != 0:
            out = (r.stderr or r.stdout or "").strip().splitlines()
            # Берём осмысленную строку об ошибке (SyntaxError/Error), а не баннер «Node.js vXX».
            err_line = next((ln for ln in out if "error" in ln.lower() and "node.js" not in ln.lower()), "")
            return (err_line or "синтаксическая ошибка").strip()
        return ""
    except Exception:
        return ""
    finally:
        if tmp:
            try:
                os.unlink(tmp)
            except Exception:
                pass


async def review_site_llm(goal: str, niche: str = "", audience: str = "") -> list[str]:
    """
    «Зрячая» самопроверка: LLM-ревьюер читает реальный HTML готового сайта и судит,
    достигает ли он цели клиента (ясность оффера, заметность CTA, доверие, тексты).
    Возвращает список КОНКРЕТНЫХ правок (пусто = сайт хорош). В отличие от check_site
    это не чек-лист, а профессиональная оценка результата.

    niche/audience передаются ОТДЕЛЬНО от goal и явно подписаны — иначе ревьюер путает
    «цель этого прогона офиса» (goal, напр. «упаковка бизнеса») с тем, что сайт должен
    ПРОДАВАТЬ. Реальный кейс: критик потребовал "заменить позиционирование под услугу
    упаковки/брендинга" на сайте натяжных потолков, потому что видел только голый
    goal="Упаковка бизнеса" без niche — developer подчинился и переписал сайт так, что
    он продавал «упаковку бизнеса» владельцам квартир вместо потолков (тот самый баг,
    который _task_with_context в loop.py уже чинит для воркеров, но не для критика).
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
        "готового сайта, что бизнес клиента продаёт конечным покупателям (niche/audience) и "
        "отдельно — цель ЭТОГО прогона офиса (не путай их!). Оцени, реально ли сайт достигает "
        "цели: ясность оффера, заметность главного CTA, доверие, структура, качество текстов. "
        "Найди КОНКРЕТНЫЕ значимые недочёты (не мелкие придирки). Если сайт уже хорош — верни "
        "пустой список.\n"
        "⚠️ ЖЁСТКОЕ ПРАВИЛО: сайт ВСЕГДА должен продавать конечному покупателю именно niche "
        "(то, что реально продаёт бизнес), а НЕ формулировку из «цели прогона офиса». Если "
        "HTML уже путает их — например называет себя услугой «упаковки бизнеса»/«брендинга» "
        "вместо прямой продажи niche — это КРИТИЧЕСКАЯ ошибка позиционирования, и первым "
        "пунктом в fixes должно быть «вернуть оффер к прямой продаже {niche}», а не «усилить "
        "формулировки услуги упаковки». НЕ проси сделать сайт более похожим на цель прогона —"
        " цель прогона не покупатель, покупатель видит только niche/audience.\n"
        'Ответь ТОЛЬКО JSON: {"fixes": ["конкретное действие", ...]} — максимум 4 пункта, по-русски.'
    )
    biz_line = ""
    if niche:
        biz_line += f"Бизнес клиента — ЧТО он продаёт конечным покупателям (это ДОЛЖЕН продавать сайт): {niche}\n"
    if audience:
        biz_line += f"Аудитория — КОМУ он продаёт: {audience}\n"
    user = (f"{biz_line}Цель ЭТОГО прогона офиса (служебная, покупатель её не видит, НЕ то, "
            f"что должен продавать сайт): {goal}\n\nHTML сайта (фрагмент):\n{html[:9000]}")
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


async def review_site_visual() -> list[str]:
    """
    ЗРЯЧАЯ проверка: реально РЕНДЕРИТ сайт в headless-браузере (Playwright) и ловит то,
    что видно только на отрисованной странице — ошибки в консоли, горизонтальный скролл
    и блоки, вылезающие за экран (кривая вёрстка), пустой рендер. Это аналог ручного
    осмотра инженером «ровно ли стоит».

    Требует playwright (+ chromium): `pip install playwright && playwright install chromium`.
    Если не установлен или рендер не удался — возвращает [] (не блокирует офис).
    """
    try:
        from playwright.async_api import async_playwright
    except Exception:
        return []
    sdir = _find_site_dir()
    idx = workspace.resolve(f"{sdir}/index.html" if sdir else "index.html")
    if idx is None or not idx.is_file():
        return []

    problems: list[str] = []
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch()
            # Мобильная ширина — тут вёрстка ломается чаще всего.
            page = await browser.new_page(viewport={"width": 390, "height": 844})
            errors: list[str] = []
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            page.on("pageerror", lambda e: errors.append(str(e)))
            try:
                await page.goto(idx.as_uri(), wait_until="load", timeout=15000)
                await page.wait_for_timeout(400)  # дать выполниться скриптам/анимациям входа
            except Exception:
                await browser.close()
                return []
            if errors:
                problems.append(f"Ошибка JS в консоли при загрузке: {errors[0][:120]} — кнопки/форма могут не работать.")
            body_h = await page.evaluate("() => document.body ? document.body.scrollHeight : 0")
            if body_h < 200:
                problems.append("При рендере страница почти пустая (высота < 200px) — контент не отображается.")
            overflow = await page.evaluate(
                "() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 2")
            if overflow:
                problems.append("На мобильном есть горизонтальный скролл — блоки шире экрана, вёрстка ломается.")
            over_n = await page.evaluate("""() => {
                const w = document.documentElement.clientWidth; let n = 0;
                for (const el of document.querySelectorAll('body *')) {
                    const r = el.getBoundingClientRect();
                    if (r.width > 0 && r.height > 0 && (r.right > w + 2 || r.left < -2)) n++;
                }
                return n;
            }""")
            if over_n > 3:
                problems.append(f"{over_n} элементов вылезают за край экрана — проверь ширины/отступы (padding, width:100%).")
            await browser.close()
    except Exception:
        return []
    return problems


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


# Признаки КРИТИЧЕСКОЙ (ломающей работу) проблемы сайта — в отличие от косметики.
# Единый источник правды: используется и финальной верификацией, и приёмкой задачи.
_CRITICAL_MARKERS = ("не отправляет", "нет формы", "не найден index",
                     "пустой или не читается", "форма не", "не собирает заявки",
                     "не работает", "битая ссылка", "битые внутренние ссылки", "сломан",
                     "js-ошибка", "нет мета viewport", "заглушк", "теряются",
                     "ошибка js в консоли", "горизонтальный скролл", "почти пустая")


def is_critical(problem: str) -> bool:
    p = (problem or "").lower()
    return any(w in p for w in _CRITICAL_MARKERS)


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
