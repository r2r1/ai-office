"""
Критик качества — приёмка результата работника перед тем, как считать задачу сделанной.

Сейчас лидер только маршрутизирует, но не оценивает результат: дизайнер мог сдать
сайт с битыми картинками и одной страницей — никто не проверил. Критик закрывает это:
программные проверки + (опционально) короткая LLM-оценка по чеклисту. Возвращает
список проблем; если он непуст — задача возвращается исполнителю с конкретикой.
"""

import posixpath
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
    """Публичный доступ: папка ГОТОВОГО К ПУБЛИКАЦИИ сайта. Для статики — папка с
    index.html; для проектов со сборкой (package.json+build) — выходная папка
    АКТУАЛЬНОЙ успешной сборки (dist/), а не исходники: index.html Vite-проекта —
    это entry со <script src="/src/main.jsx">, публиковать/критиковать его как
    сайт бессмысленно. Сборки нет/устарела → None (publish_site_auto сначала
    вызовет site_builder.ensure_built). Ленивый импорт — от цикла."""
    from src.office import site_builder
    d = site_builder.detect()
    if d["kind"] == "build":
        return site_builder.published_root()
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


# ── Структурный контракт проблемы (BOS §12) ──────────────────────────────────
# Проблема — не строка, а запись {code, severity, text}. Тяжесть объявляется В
# МЕСТЕ обнаружения проверкой, а не угадывается потом подстрокой в русской фразе
# (переформулировал сообщение — потерял критичность). severity ∈ critical|cosmetic.
def _p(code: str, severity: str, text: str) -> dict:
    return {"code": code, "severity": severity, "text": text}


def text_of(problem) -> str:
    """Текст проблемы (устойчиво к старому строковому формату, если где-то остался)."""
    return problem.get("text", "") if isinstance(problem, dict) else str(problem)


def check_site() -> list[dict]:
    """
    Программный тестировщик собранного сайта — как ручная проверка инженера, но
    детерминированно и без LLM. Проверяет НЕ только index, а ВСЕ страницы: структуру
    HTML, целостность ссылок, рабочесть форм на каждой странице, синтаксис JS (реальный
    node --check), дубли/заглушки, базовую доступность. Возвращает список проблем.
    """
    # Проект со сборкой: критикуем ВЫХОД сборки (dist/), не исходники — index.html
    # Vite-проекта это entry со <script src="/src/main.jsx">, как сайт он «пустой».
    # Сборка не прошла/отключена → это и есть главная проблема сайта (с логом).
    from src.office import site_builder
    is_built_spa = site_builder.detect()["kind"] == "build"
    if is_built_spa:
        bp = site_builder.cached_problem()
        if bp is not None:
            # critical (failed/disabled) — блокирующая проблема; cosmetic (pending —
            # офис ещё не собирал эти исходники) — мягкая, без ложного «создай index».
            return [_p(bp["code"], bp["severity"], bp["text"])]
        site_dir = site_builder.published_root()
    else:
        site_dir = _find_site_dir()
    if site_dir is None:
        return [_p("no_index", "critical",
                   "Не найден index.html — сайт ещё не собран. Создай site/index.html через write_file.")]

    idx_path = f"{site_dir}/index.html" if site_dir else "index.html"
    html = _read(idx_path)
    if not html:
        return [_p("empty_index", "critical",
                   "index.html пустой или не читается — перепиши его полностью.")]

    problems: list[dict] = []
    in_dir = _site_files(site_dir)
    html_pages = [p for p in in_dir if p.endswith(".html")]
    js_files = [p for p in in_dir if p.endswith(".js")]
    existing_names = {_basename(p) for p in in_dir}
    low = html.lower()

    # Общий JS всех страниц (fetch формы часто в отдельном script.js). Читаем
    # БЕЗ лимита read_file (200KB): минифицированный бандл собранного SPA больше,
    # и «/api/site-lead» в его хвосте терялся бы за срезом → ложный «нет формы».
    def _read_full(p: str) -> str:
        raw = workspace.read_bytes(p)
        return raw.decode("utf-8", errors="replace") if raw else ""
    js_blob = "\n".join(_read_full(p).lower() for p in js_files)

    # 1. Внешние картинки часто не грузятся (Unsplash и т.п.) — требуем локальные/SVG.
    ext_imgs = re.findall(r'<img[^>]+src=["\']https?://[^"\']+', html, re.IGNORECASE)
    if ext_imgs:
        problems.append(_p("external_images", "cosmetic",
            f"Внешние картинки ({len(ext_imgs)} шт., напр. Unsplash) не грузятся и ломают вид — "
            "замени на встроенные SVG или CSS-градиентные блоки."))

    # 2. Стили должны быть.
    if not any(p.endswith(".css") for p in in_dir) and "<style" not in low:
        problems.append(_p("no_styles", "cosmetic",
            "Нет стилей вообще — добавь css/style.css или хотя бы <style>."))

    # 3. index: title и объём.
    if "<title" not in low:
        problems.append(_p("no_title", "cosmetic", "Нет <title> у главной — добавь заголовок страницы."))
    if len(html) < 1200:
        problems.append(_p("thin_content", "cosmetic",
            "Слишком мало контента на главной — добавь секции (оффер, услуги, преимущества, отзывы)."))

    # 4. ФОРМЫ на КАЖДОЙ странице реально шлют на /api/site-lead (не только index).
    stub_markers = ("подключаем crm", "подключаем эндпоинт", "готово к отправке",
                    "эндпоинт скоро", "заглушк", "todo", "coming soon")
    pages_with_form = [p for p in html_pages if "<form" in _read(p).lower()]
    if not pages_with_form:
        # SPA (собранный React/Vue): <form> рендерится из JS и в HTML отсутствует.
        # Признак живой лид-формы там — отправка на /api/site-lead в JS-бандле.
        if "/api/site-lead" not in js_blob:
            problems.append(_p("no_form", "critical",
                "Нет формы заявки ни на одной странице — сайт не собирает лиды."))
    for p in pages_with_form:
        page_low = _read(p).lower()
        sends = "/api/site-lead" in page_low or "/api/site-lead" in js_blob
        if not sends:
            problems.append(_p("form_no_send", "critical",
                f"{_basename(p)}: форма не отправляет заявки на /api/site-lead — лиды теряются."))
        elif any(s in (page_low + js_blob) for s in stub_markers) and "/api/site-lead" not in page_low:
            problems.append(_p("form_stub", "critical",
                f"{_basename(p)}: форма-заглушка (фраза «подключаем/готово»), реальной отправки нет."))

    # 5. ЦЕЛОСТНОСТЬ ССЫЛОК: каждая внутренняя ссылка ведёт на существующий файл.
    # Сначала пробуем путь ПОЛНОСТЬЮ (разрешённый относительно директории страницы) —
    # раньше сравнивали только basename, и href="./pages/x.html" считался рабочим,
    # если ЛЮБОЙ файл x.html есть где угодно в site/, даже не по этому пути. Basename
    # оставлен как менее строгий fallback — большинство наших сайтов плоские
    # (index.html + несколько страниц в корне site/, без вложенных папок).
    existing_paths = set(in_dir)
    broken = set()
    for p in html_pages:
        page_dir = p.rsplit("/", 1)[0] if "/" in p else ""
        for href in re.findall(r'href=["\']([^"\'#?]+\.html)[^"\']*["\']', _read(p), re.IGNORECASE):
            href = href.strip()
            resolved = posixpath.normpath(posixpath.join(page_dir, href)) if page_dir else posixpath.normpath(href)
            target = _basename(href.strip("/"))
            if resolved in existing_paths:
                continue
            if target and target not in existing_names:
                broken.add(f"{_basename(p)} → {target}")
    if broken:
        problems.append(_p("broken_links", "critical",
            f"Битые внутренние ссылки на несуществующие страницы: {'; '.join(sorted(broken)[:5])}."))

    # 6. СТРУКТУРА HTML каждой страницы: базовый каркас + мобильный viewport + lang.
    for p in html_pages:
        c = _read(p).lower()
        if not c:
            continue
        if "<html" not in c or "<body" not in c:
            problems.append(_p("broken_frame", "critical",
                f"{_basename(p)}: сломан каркас HTML (нет <html>/<body>)."))
        if "viewport" not in c:
            problems.append(_p("no_viewport", "critical",
                f"{_basename(p)}: нет мета viewport — сайт сломан на телефоне."))
        if "<html" in c and "lang=" not in c:
            problems.append(_p("no_lang", "cosmetic",
                f"{_basename(p)}: у <html> нет lang — важно для доступности/SEO."))

    # 7. ЗАГЛУШКИ/ДУБЛИ: пустые страницы и свалка почти одинаковых файлов.
    for p in html_pages:
        c = _read(p)
        # ВАЖНО: не матчим слово "placeholder" — это HTML-атрибут инпутов, а не заглушка.
        # Признак заглушки: крошечный файл или lorem/явная пометка «заглушка».
        text_only = re.sub(r"<[^>]+>", "", c)
        if len(c) < 500 or "lorem ipsum" in c.lower() or "текст-заглушка" in c.lower() \
                or len(text_only.strip()) < 200:
            # Шелл собранного SPA легитимно «пуст»: <div id="root"> + бандл,
            # весь контент рендерит JS — это не заглушка (проверит Playwright-рендер).
            if is_built_spa and js_files:
                continue
            problems.append(_p("stub_page", "critical",
                f"{_basename(p)}: страница-заглушка/пустая — доделай или удали."))
    dup = _near_duplicate_pages(html_pages)
    if dup:
        problems.append(_p("duplicate_pages", "cosmetic",
            f"Много почти одинаковых страниц ({dup}) — это свалка дублей, "
            "оставь по одной на смысл, остальные удали."))

    # 8. JS-СИНТАКСИС: реальный прогон node --check (как ручная проверка), если node есть.
    # Отдельные .js файлы И инлайновый <script type="module"> (3D-скилл часто пишет
    # React/framer-motion прямо в index.html, а не в отдельный app.js — раньше такой
    # код никто не проверял вообще).
    for p in js_files:
        # Выход сборки уже провалидирован самой сборкой; к тому же _read обрезает
        # файл до 200KB — node --check на ОБРЕЗАННОМ бандле дал бы гарантированную
        # ложную «синтаксическую ошибку».
        if site_builder.is_built_output(p):
            continue
        code = _read(p)
        is_module = bool(re.search(r"^\s*(import|export)\s", code, re.M))
        err = workspace._js_syntax_error(code, as_module=is_module)
        if err:
            problems.append(_p("js_error", "critical",
                f"{_basename(p)}: JS-ошибка синтаксиса — {err[:100]}"))
    for m in re.finditer(r'<script[^>]*type=["\']module["\'][^>]*>(.*?)</script>',
                          html, re.IGNORECASE | re.DOTALL):
        err = workspace._js_syntax_error(m.group(1), as_module=True)
        if err:
            problems.append(_p("js_error", "critical",
                f"index.html: JS-ошибка синтаксиса в инлайн <script type=module> — {err[:100]}"))

    # 8b. ESM-РЕАКТ БЕЗ ИМПОРТА REACT: скилл "3D-лендинг на Framer Motion" грузит
    # react-dom/client и framer-motion через esm.sh importmap, а сам 'react' часто
    # забывают импортировать явно и обращаются к глобальному React (`const {...} =
    # React` / `React.createElement`) — в ESM-модуле такого глобала НЕТ, скрипт падает
    # с ReferenceError на первой же строке, страница остаётся пустой. node --check
    # эту ошибку НЕ ловит (это валидный синтаксис, просто React не определён в
    # рантайме), а Playwright (review_site_visual) опционален и часто не установлен —
    # нужна дешёвая детерминированная проверка, которая работает всегда.
    def _read_full_raw(p: str) -> str:
        raw = workspace.read_bytes(p)
        return raw.decode("utf-8", errors="replace") if raw else ""
    raw_js = "\n".join(_read_full_raw(p) for p in js_files)
    inline_modules = "\n".join(m.group(1) for m in re.finditer(
        r'<script[^>]*type=["\']module["\'][^>]*>(.*?)</script>', html, re.IGNORECASE | re.DOTALL))
    combined_raw = raw_js + "\n" + inline_modules
    uses_esm_react = "esm.sh/react" in low or "esm.sh/framer-motion" in low
    if uses_esm_react:
        imports_react = bool(re.search(r'import\s+(?:\*\s*as\s+)?React\b.*from\s+[\'"]react[\'"]', combined_raw))
        uses_bare_react = bool(re.search(r'(?<![\w.$])React\s*[.;]', combined_raw))
        if uses_bare_react and not imports_react:
            problems.append(_p("react_not_imported", "critical",
                "Код обращается к глобальному React (React.createElement / const {...} = React), "
                "но 'react' нигде не импортирован через ESM (import React from 'react') — в браузере "
                "такого глобала нет, скрипт падает с ReferenceError на первой строке, страница пустая."))

    # 8c. TAILWIND-КЛАССЫ БЕЗ TAILWIND: без шага сборки utility-классы (md:w-1/2,
    # bg-gradient-to-br, grid-cols-3 и т.п.) — просто строки, ничего не значащие для
    # браузера, если сам Tailwind не подключён (CDN-скрипт или собранный .css с этими
    # классами). Реальный кейс: сайт с десятками таких классов рендерился полностью
    # неоформленным (без сетки/отступов/цветов), потому что рантайм Tailwind не грузился.
    tailwind_markers = (r'\b(?:sm|md|lg|xl):[a-z0-9_-]+', r'\bbg-gradient-to-(?:br|bl|tr|tl|r|l|t|b)\b',
                        r'\bgrid-cols-\d\b', r'\btext-(?:gray|indigo|red|blue|green|purple)-\d{3}\b')
    tailwind_used = any(re.search(pat, low) for pat in tailwind_markers) \
        or any(re.search(pat, combined_raw) for pat in tailwind_markers)
    tailwind_loaded = "tailwindcss" in low or any(p.endswith("tailwind.css") for p in in_dir)
    if tailwind_used and not tailwind_loaded:
        problems.append(_p("tailwind_without_tailwind", "critical",
            "В разметке/JS используются Tailwind utility-классы (md:, bg-gradient-to-, "
            "grid-cols- и т.п.), но сам Tailwind нигде не подключён (нет <script src="
            "\"https://cdn.tailwindcss.com\"> и нет tailwind.css) — без сборки эти классы "
            "ничего не значат, вёрстка отображается неоформленной."))

    # 8d. ALPINE-ПЛАГИНЫ: x-intersect/x-collapse — НЕ часть ядра Alpine, а отдельные
    # CDN-плагины (@alpinejs/intersect, @alpinejs/collapse), которые обязаны грузиться
    # ДО core alpinejs.js (с defer скрипты выполняются по порядку документа, а core
    # стартует Alpine.start() сразу после своего исполнения — опоздавший плагин Alpine
    # не увидит). Реальный кейс: скилл alpine_tailwind_landing сгенерировал сайт, где
    # core Alpine шёл раньше intersect-плагина, а collapse-плагин не был подключён
    # вовсе — FAQ-аккордеоны и анимации при скролле молча не работали, в консоли
    # только warning, никакая другая проверка (verify_code — синтаксис, а не рантайм
    # Alpine) этого не ловила.
    alpine_src_re = re.compile(r'<script[^>]*\bsrc=["\']([^"\']*alpinejs[^"\']*)["\']', re.IGNORECASE)
    plugin_src_re = re.compile(r'<script[^>]*\bsrc=["\']([^"\']*@alpinejs/(intersect|collapse)[^"\']*)["\']', re.IGNORECASE)
    alpine_scripts = alpine_src_re.findall(html)
    core_matches = [s for s in alpine_scripts if "@alpinejs/" not in s]
    if core_matches:
        core_pos = html.find(core_matches[0])
        used_directives = {"intersect": "x-intersect" in low, "collapse": "x-collapse" in low}
        plugin_pos = {name: None for name in used_directives}
        for m in plugin_src_re.finditer(html):
            plugin_pos[m.group(2).lower()] = m.start()
        for name, used in used_directives.items():
            if not used:
                continue
            pos = plugin_pos.get(name)
            if pos is None:
                problems.append(_p("alpine_plugin_missing", "critical",
                    f"Используется x-{name}, но плагин @alpinejs/{name} нигде не подключён по CDN — "
                    f"директива молча не будет работать (только warning в консоли браузера)."))
            elif pos > core_pos:
                problems.append(_p("alpine_plugin_order", "critical",
                    f"Плагин @alpinejs/{name} подключён ПОСЛЕ core alpinejs.js — с defer core стартует "
                    f"первым и не видит опоздавший плагин, x-{name} не будет работать. Переставь тег "
                    f"плагина выше тега core alpinejs.js в <head>."))

    # 9. ДОСТУПНОСТЬ (базово): картинки без alt.
    imgs_no_alt = 0
    for p in html_pages:
        imgs_no_alt += len([m for m in re.findall(r'<img\b[^>]*>', _read(p), re.IGNORECASE)
                            if 'alt=' not in m.lower()])
    if imgs_no_alt:
        problems.append(_p("no_alt", "cosmetic",
            f"Картинки без alt ({imgs_no_alt} шт.) — добавь alt для доступности/SEO."))

    # 10. ФЕЙКОВОЕ 3D: страница заявляет «3D», но это статичная CSS-плашка без движения.
    text_only_full = re.sub(r"<[^>]+>", " ", re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html,
                             flags=re.IGNORECASE | re.DOTALL))
    fake_3d = _fake_3d_problem(text_only_full, low, js_blob)
    if fake_3d:
        problems.append(_p("fake_3d", "cosmetic", fake_3d))

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


async def review_site_llm(goal: str, niche: str = "", audience: str = "") -> list[dict]:
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

    # Текст ревью — policies/critic_site_review.md (собирается prompt_builder,
    # логируется в prompts.jsonl). Слот Brief НЕ подмешиваем: niche/audience/goal
    # уже сериализованы вручную в user из аргументов функции (единый путь, тестирован).
    from src.office import prompt_builder
    biz_line = ""
    if niche:
        biz_line += f"Бизнес клиента — ЧТО он продаёт конечным покупателям (это ДОЛЖЕН продавать сайт): {niche}\n"
    if audience:
        biz_line += f"Аудитория — КОМУ он продаёт: {audience}\n"
    user = (f"{biz_line}Цель ЭТОГО прогона офиса (служебная, покупатель её не видит, НЕ то, "
            f"что должен продавать сайт): {goal}\n\nHTML сайта (фрагмент):\n{html[:9000]}")
    system, _pid = prompt_builder.company_system(
        "critic_site_review", "orchestrator_1", "critic", user, with_brief=False)
    try:
        raw = await llm.run_agent(
            system=system, user=user, model=models_module.for_agent("orchestrator_1"),
            max_tokens=500, use_search=False, agent_id="orchestrator_1",
        )
    except Exception:
        return []
    # Раньше здесь был жадный re.search(r"\{.*\}", raw, re.DOTALL) — захватывал от
    # ПЕРВОЙ { до ПОСЛЕДНЕЙ } во всём ответе. Если модель добавляла хоть один лишний
    # {...} до/после нужного JSON (рассуждение, пример), кусок склеивался в невалидный
    # JSON, json.loads падал, исключение тихо проглатывалось — ревью сайта молча не
    # выполнялось. Теперь пробуем КАЖДУЮ { по очереди через JSONDecoder.raw_decode
    # (останавливается на первом сбалансированном объекте, игнорируя хвост) и берём
    # первый объект, у которого реально есть ключ "fixes" — устойчиво и к лишнему
    # тексту вокруг, и к декоративному JSON перед нужным объектом.
    raw = raw or ""
    decoder = json.JSONDecoder()
    pos = 0
    while True:
        idx = raw.find("{", pos)
        if idx == -1:
            return []
        try:
            obj, end = decoder.raw_decode(raw[idx:])
        except Exception:
            pos = idx + 1
            continue
        if isinstance(obj, dict) and "fixes" in obj:
            fixes = obj.get("fixes", [])
            # LLM-замечания позиционирования — cosmetic: запускают одну доработку,
            # но не входят в критический гейт приёмки (тот считается по check_site).
            return [_p("llm_review", "cosmetic", str(f)[:200]) for f in fixes if f][:4]
        pos = idx + max(end, 1)


async def review_site_visual() -> list[dict]:
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

    problems: list[dict] = []
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
                problems.append(_p("console_error", "critical",
                    f"Ошибка JS в консоли при загрузке: {errors[0][:120]} — кнопки/форма могут не работать."))
            body_h = await page.evaluate("() => document.body ? document.body.scrollHeight : 0")
            if body_h < 200:
                problems.append(_p("empty_render", "critical",
                    "При рендере страница почти пустая (высота < 200px) — контент не отображается."))
            overflow = await page.evaluate(
                "() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 2")
            if overflow:
                problems.append(_p("h_scroll", "critical",
                    "На мобильном есть горизонтальный скролл — блоки шире экрана, вёрстка ломается."))
            over_n = await page.evaluate("""() => {
                const w = document.documentElement.clientWidth; let n = 0;
                for (const el of document.querySelectorAll('body *')) {
                    const r = el.getBoundingClientRect();
                    if (r.width > 0 && r.height > 0 && (r.right > w + 2 || r.left < -2)) n++;
                }
                return n;
            }""")
            if over_n > 3:
                problems.append(_p("overflow_elements", "cosmetic",
                    f"{over_n} элементов вылезают за край экрана — проверь ширины/отступы (padding, width:100%)."))
            await browser.close()
    except Exception:
        return []
    return problems


def check_bot() -> list[dict]:
    """
    Проверка Telegram-бота: bot.py / main.py существует и содержит рабочую структуру.
    Возвращает список проблем (пустой = всё ок). Любая проблема бота — critical
    (нерабочий бот не должен считаться сданным).
    """
    files = {f["path"]: f for f in workspace.list_files()}
    bot_path = next((p for p in ("bot.py", "main.py", "src/bot.py") if p in files), None)
    if bot_path is None:
        return [_p("no_bot_file", "critical",
                   "Не найден файл бота (bot.py / main.py) — создай его через write_file.")]

    code = workspace.read_file(bot_path)
    if not code or code.startswith("Файл не найден"):
        return [_p("empty_bot", "critical", f"{bot_path} пустой или не читается — перепиши его полностью.")]

    problems: list[dict] = []
    low = code.lower()

    if "aiogram" not in low and "telebot" not in low and "telegram" not in low:
        problems.append(_p("no_bot_lib", "critical",
            f"{bot_path}: не импортируется библиотека бота (aiogram / telebot)."))
    if "token" not in low and "bot_token" not in low:
        problems.append(_p("no_bot_token", "critical",
            f"{bot_path}: нет переменной TOKEN / BOT_TOKEN — бот не сможет запуститься."))
    if "async def" not in low and "def " not in low:
        problems.append(_p("no_bot_handlers", "critical",
            f"{bot_path}: нет обработчиков сообщений (async def handler)."))
    if len(code) < 300:
        problems.append(_p("thin_bot", "critical",
            f"{bot_path}: слишком мало кода ({len(code)} символов) — добавь обработчики команд."))

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


def is_critical(problem) -> bool:
    """Критическая (ломающая работу) проблема — по ОБЪЯВЛЕННОЙ тяжести (severity),
    а не по подстроке в русской фразе. Раньше критичность угадывалась списком
    _CRITICAL_MARKERS: переформулировал сообщение проверки — потерял критичность
    (хрупко). Теперь severity ставится в месте обнаружения проблемы (BOS §12)."""
    if isinstance(problem, dict):
        return problem.get("severity") == "critical"
    return False  # строковый формат больше не производится критиком


def critique_text(problems: list) -> str:
    """Человекочитаемый фидбэк исполнителю по сайту."""
    if not problems:
        return ""
    lines = "\n".join(f"- {text_of(p)}" for p in problems)
    return ("⚠ Нужны небольшие правки. Исправь прямо в существующих файлах папки site/ "
            "(НЕ начинай с нуля, НЕ вызывай publish_site — офис опубликует сам):\n" + lines)


def critique_text_bot(problems: list) -> str:
    """Человекочитаемый фидбэк исполнителю по боту."""
    if not problems:
        return ""
    lines = "\n".join(f"- {text_of(p)}" for p in problems)
    return ("⚠ Нужны правки в боте. Прочитай файл через read_file, "
            "исправь проблемы, перезапись через write_file:\n" + lines)
