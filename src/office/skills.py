"""
Skills — встроенная бизнес-логика (второй способ Execution Engine из docs/3.md).

Задача может быть выполнена тремя способами:
  1. Встроенный AI (LLM) — основной путь (см. core/llm.py).
  2. Skill — готовая бизнес-логика: знает КАК сделать (структура, приёмы, проверки).
     Роль больше НЕ держит «как» у себя в промпте — «как» живёт здесь, в скилле.
  3. External Worker — внешний сервис (Cursor/Lovable/n8n) — точка расширения.

Как воркер выбирает скилл (тот же приём, что в tool_router для интеграций):
  воркер описывает ПОТРЕБНОСТЬ словами  →  use_skill("сделать 3D-лендинг с анимациями")
    →  skills.match() ранжирует скиллы по словам потребности
    →  возвращается ПЛЕЙБУК скилла (экспертные инструкции + план файлов + чеклист)
    →  воркер выполняет его СВОИМИ инструментами (write_file/verify_code/…).

Так роль перестаёт быть зашитой инструкцией: захотели менять способ делать
3D-сайты — правим скилл, а не каждую роль; новый способ — новый скилл, роли не трогаем.
"""

from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional


@dataclass
class Skill:
    """Декларативное описание навыка (по образцу integrations/base.Integration)."""
    id: str
    title: str
    description: str
    # Слова-триггеры в тексте потребности (грубый матч намерения).
    keywords: list[str] = field(default_factory=list)
    # Экспертный плейбук «как делать»: структура файлов, приёмы, проверки.
    # Именно его получает воркер при use_skill и выполняет своими инструментами.
    playbook: str = ""
    # Каким ролям осмысленно (пусто = всем). Фильтрует выдачу под конкретного воркера.
    roles: list[str] = field(default_factory=list)
    # builtin — делается встроенной моделью по плейбуку; external — делегируется наружу.
    kind: str = "builtin"
    # Опциональный детерминированный исполнитель (если скилл сам что-то делает).
    handler: Optional[Callable[[dict], Awaitable[str]]] = None
    # Откуда скилл: "builtin" (в коде) или "installed" (файл, поставлен клиентом).
    source: str = "builtin"

    def score(self, task: str) -> int:
        """Насколько Skill подходит задаче (число совпавших ключевых слов)."""
        t = (task or "").lower()
        return sum(1 for k in self.keywords if k in t)

    def to_public(self) -> dict:
        return {"id": self.id, "title": self.title, "description": self.description,
                "keywords": self.keywords, "roles": self.roles, "kind": self.kind,
                "source": self.source}


# ── Реестр ───────────────────────────────────────────────────────────────────
# _BUILTIN — скиллы из кода (общие для всех тенантов, регистрируются при импорте).
# Установленные клиентом скиллы (файлы) вливаются в выдачу через _all_registered()
# и потому автоматически видны use_skill/find_skills без правок agent_factory.
_BUILTIN: dict[str, Skill] = {}


def register(skill: Skill) -> None:
    _BUILTIN[skill.id] = skill


def _all_registered() -> dict[str, Skill]:
    """Встроенные + установленные текущим тенантом (installed переопределяет по id)."""
    from src.office import skill_store
    merged: dict[str, Skill] = dict(_BUILTIN)
    for d in skill_store.load_installed():
        merged[d["id"]] = Skill(
            id=d["id"], title=d["title"], description=d["description"],
            keywords=d.get("keywords") or [], playbook=d.get("playbook", ""),
            roles=d.get("roles") or [], kind=d.get("kind", "builtin"),
            source="installed",
        )
    return merged


def get(skill_id: str) -> Optional[Skill]:
    return _all_registered().get(skill_id)


def all_skills(role: str = "") -> list[Skill]:
    """Скиллы, доступные роли (или все). Скилл без привязки доступен любой роли."""
    items = list(_all_registered().values())
    if not role:
        return items
    return [s for s in items if not s.roles or role in s.roles]


def match(task: str, role: str = "") -> Optional[Skill]:
    """Лучший Skill под потребность или None (тогда задачу делает LLM напрямую)."""
    pool = all_skills(role)
    ranked = sorted(pool, key=lambda s: s.score(task), reverse=True)
    if ranked and ranked[0].score(task) > 0:
        return ranked[0]
    return None


def suggestions(task: str, role: str = "", top: int = 3) -> list[Skill]:
    """Топ-N подходящих скиллов (для развилки, когда лидера нет)."""
    pool = [(s, s.score(task)) for s in all_skills(role)]
    pool = [p for p in pool if p[1] > 0]
    pool.sort(key=lambda kv: kv[1], reverse=True)
    return [s for s, _ in pool[:top]]


def catalog_for(role: str) -> str:
    """Короткий список доступных роли скиллов — для подсказки в промпте."""
    items = all_skills(role)
    return "; ".join(f"«{s.title}»" for s in items) if items else ""


def search(query: str, role: str = "", top: int = 6) -> list[Skill]:
    """
    Поиск по каталогу скиллов (внутренний аналог find-skills) — для ДИСКАВЕРИ,
    когда воркер/лидер хочет ПОСМОТРЕТЬ, какие способы вообще есть под запрос,
    а не сразу взять один плейбук (это делает match/use_skill).

    Пустой запрос → весь каталог роли (просто «покажи что умеешь»). Иначе —
    ранжирование по совпадению ключевых слов; если совпадений нет, возвращаем
    топ каталога роли (лучше показать что есть, чем пусто).
    """
    pool = all_skills(role)
    q = (query or "").strip().lower()
    if not q:
        return pool[:top]
    scored = sorted(pool, key=lambda s: s.score(q), reverse=True)
    if scored and scored[0].score(q) > 0:
        return [s for s in scored if s.score(q) > 0][:top]
    return pool[:top]


def prompt_block(role: str) -> str:
    """
    Динамический блок скиллов для системного промпта роли (собирается Prompt Builder'ом).

    Роль НЕ называет скиллы в своём тексте — их подмешивает этот блок из реестра,
    отфильтрованный под роль. Так каталог из 200 скиллов не раздувает промпт: воркер
    видит только релевантные его роли, а конкретный плейбук достаёт через use_skill.
    Нет скиллов для роли → пустая строка (блок не появляется).
    """
    items = all_skills(role)
    if not items:
        return ""
    lines = "\n".join(f"• {s.title} — {s.description}" for s in items)
    return ("\n\nДОСТУПНЫЕ СКИЛЛЫ (готовые способы «как делать»). Когда сомневаешься, "
            "как именно выполнить — НЕ выдумывай: вызови use_skill с потребностью словами, "
            "получи экспертный плейбук и выполни его своими инструментами. Не уверен, "
            "что есть под задачу — сначала find_skills (поиск по каталогу).\n" + lines)


def catalog_payload() -> list[dict]:
    return [s.to_public() for s in _all_registered().values()]


# ── Установка/удаление скиллов-файлов (аналог npx skills add/remove) ─────────
# Тонкие обёртки над skill_store — единая точка входа для API. Установка — только
# явное действие пользователя (см. server.py), НЕ инструмент агента.
def install(source: str, content: str = "", url: str = "", ref: str = "") -> dict:
    from src.office import skill_store
    if source == "markdown":
        return skill_store.install_markdown(content)
    if source == "url":
        return skill_store.install_url(url)
    if source == "github":
        return skill_store.install_github(ref)
    return {"ok": False, "message": "source должен быть markdown | url | github"}


def remove(skill_id: str) -> dict:
    from src.office import skill_store
    if skill_id in _BUILTIN:
        return {"ok": False, "message": "Встроенный скилл нельзя удалить — можно переопределить, установив свой с тем же id."}
    ok = skill_store.remove(skill_id)
    return {"ok": ok, "message": "" if ok else "Скилл не найден среди установленных."}


# ── Скилл: 3D-лендинг на Framer Motion ───────────────────────────────────────
_FRAMER_3D_PLAYBOOK = """\
СКИЛЛ: премиальный 3D-лендинг с ЖИВЫМИ интерактивными эффектами.

⚠️ ЭТОТ СКИЛЛ ПЕРЕОПРЕДЕЛЯЕТ СТЕК ИЗ ТЗ для этой задачи: даже если в ТЗ написано
«Vanilla JS без фреймворков» — для 3D-задачи используй способ этого скилла.

⚠️ ЕСЛИ site/index.html УЖЕ СУЩЕСТВУЕТ: НЕ переписывай сайт с нуля! Сначала read_file,
сохрани контент (офферы, тексты, форму, квиз) и ДОБАВЬ 3D-слой поверх: hero-сцену,
tilt-карточки, параллакс. Итог = прежний контент + живое 3D, а не новый сайт.

КРИТЕРИЙ КАЧЕСТВА (без этого 3D не засчитывается): минимум ДВА эффекта, реагирующие
на действия пользователя, а не статичная CSS-картинка:
1. tilt/поворот элементов ЗА КУРСОРОМ (mousemove → rotateX/rotateY с инерцией);
2. параллакс слоёв ПРИ СКРОЛЛЕ (разная скорость/глубина);
3. каскадное появление секций при прокрутке (stagger).
Статичная «сцена» из transform: rotateX(...) без движения — НЕ 3D-лендинг, это плашка.

Цель — «вау»-лендинг с настоящими 3D-эффектами и физикой движения, БЕЗ шага сборки:
платформа хостит папку site/ как статику, поэтому React и framer-motion подключаются
прямо в браузере через importmap с esm.sh. npm/build НЕ нужны.
(Если решишь остаться на Vanilla JS — допустимо, но ОБЯЗАТЕЛЬНЫ те же 2+ живых
эффекта: mousemove-tilt через requestAnimationFrame и scroll-параллакс через
IntersectionObserver/scroll — без них задача не выполнена.)

СТРУКТУРА (всё в site/):
• site/index.html — единственная страница. Внутри:
  - <script type="importmap"> с react, react-dom/client, framer-motion (motion) c esm.sh;
  - <div id="root"></div>;
  - <script type="module"> с приложением (или подключи site/app.js).

ОБЯЗАТЕЛЬНЫЙ importmap (вставь как есть, версии фиксируй):
  <script type="importmap">
  {"imports": {
    "react": "https://esm.sh/react@18.3.1",
    "react-dom/client": "https://esm.sh/react-dom@18.3.1/client",
    "framer-motion": "https://esm.sh/framer-motion@11?external=react"
  }}
  </script>

JSX НЕ используем (нет сборщика) — пишем через React.createElement.
Приём: `const m = motion; const h = React.createElement;` далее `h(m.div, {...}, ...)`.
Импорт: `import { motion, useScroll, useTransform, useMotionValue, useSpring } from "framer-motion"`.

3D-ПРИЁМЫ FRAMER MOTION (это суть скилла):
• perspective на контейнере (style: { perspective: 1000 }) — включает 3D-сцену.
• motion-компоненты с rotateX/rotateY/translateZ в animate/whileHover/whileInView.
• Параллакс по скроллу: useScroll() + useTransform(scrollYProgress,[0,1],[...]) —
  слои двигаются с разной скоростью и глубиной.
• Tilt-карточки: onMouseMove считает rotateX/rotateY от позиции курсора через
  useMotionValue + useSpring (живая инерция, а не дёрганье).
• Появление секций: whileInView={{opacity:1,y:0,rotateX:0}} c viewport={{once:true}}.
• Stagger: variants контейнера со staggerChildren для каскадного входа.
• spring-переходы (type:'spring', stiffness/damping), НЕ линейные.

СОДЕРЖАНИЕ (минимум 5 секций): hero с 3D-объектом/слоями, услуги/о нас,
преимущества, кейсы/отзывы, контакт-форма. Контент — по брифу клиента, без заглушек.

ПАЛИТРА: это решение маркетинга, не твоё. Сначала read_file docs/site_content.md
за строкой «Стиль: …» — она задаёт настроение и цвета 3D-сцены. Нет строки —
ask_colleague("marketer", "нужна строка «Стиль: …» под нашу нишу/аудиторию"),
не изобретай палитру сам. Только без marketer в компании — выведи из брифа сам
как временное; иначе не бери дефолтный тёмно-синий+cyan/violet — так выглядит
любой 3D-лендинг без привязки к нише.

ФОРМА ЗАЯВКИ: POST на /api/site-lead, JSON {name, contact, message} → «Лиды».
Бэкенд НЕ строй — эндпоинт уже хостится платформой.

КАРТИНКИ: без внешних файлов —  SVG.

ПРОВЕРКИ ПЕРЕД СДАЧЕЙ (чеклист скилла):
1. index.html открывается, в консоли нет ошибок импорта (версии в importmap валидны).
2. Виден хотя бы один реальный 3D-эффект при скролле и при наведении.
3. Форма шлёт POST /api/site-lead.
4. respect prefers-reduced-motion: при включённом — отключай тяжёлые анимации.

ВЫПОЛНЕНИЕ: пиши файлы через write_file. Готово — офис опубликует site/ сам.\
"""


async def _framer_3d(params: dict) -> str:
    # Скилл встроенный: его «работа» — выдать воркеру экспертный плейбук,
    # дальше воркер исполняет его своими инструментами (write_file и т.д.).
    return _FRAMER_3D_PLAYBOOK


register(Skill(
    id="framer_motion_3d_site",
    title="3D-лендинг на Framer Motion",
    description="Премиальный одностраничник с настоящими 3D-эффектами и физикой "
                "движения на React + framer-motion, без шага сборки (esm.sh).",
    keywords=["3d", "3д", "framer", "фреймер", "motion", "анимаци", "анимир",
              "паралл", "parallax", "вау", "премиальн", "интерактивн", "tilt"],
    playbook=_FRAMER_3D_PLAYBOOK,
    roles=["designer", "developer"],
    handler=_framer_3d,
))


# ── Скилл: премиальный статический сайт (без 3D) ────────────────────────────
_STATIC_SITE_PLAYBOOK = """\
СКИЛЛ: премиальный статический сайт/лендинг (без сборки, без 3D) — уровень студии.

ФАЙЛЫ (в site/): index.html + site/styles.css + site/script.js (стили и скрипт
ОТДЕЛЬНЫМИ файлами, не инлайном). Доп. страницы — по необходимости, общий css/js во все.
🚫 Никаких Tilda/Webflow/Wix/конструкторов — только собственный код.

ПРАВКА vs НОВЫЙ САЙТ (критично):
• Если site/index.html УЖЕ существует — это ПРАВКА: сначала read_file, меняй ТОЧЕЧНО,
  НЕ переписывай с нуля, НЕ выкидывай готовые секции, НЕ сокращай сайт.
• В конце ответа ОДНОЙ строкой: «Изменения: …» — что именно поправил.

ВИЗУАЛЬНАЯ ПЛАНКА (иначе получается дёшево — так делать НЕЛЬЗЯ):
• Палитра НЕ по умолчанию и НЕ твоя зона решения — это бренд-выбор маркетинга.
  Сначала read_file docs/site_content.md за строкой «Стиль: …». Нет строки —
  ask_colleague("marketer", "нужна строка «Стиль: …»: 2-3 прилагательных
  настроения под нашу нишу/аудиторию"), не придумывай палитру сам. Только если
  в компании нет marketer (отдел маркетинга не открыт) — выведи направление из
  брифа сам как временное и пометь это в ответе; иначе не бери дефолтный
  тёмно-синий+cyan/violet «SaaS-гласморфизм» (шаблонный вид для любой ниши).
• Дизайн-токены в :root — палитра (фон, поверхность, акцент, текст 2 уровня),
  радиусы, тени, отступы по шкале 4/8px. Единая система, не случайные значения.
• Типографика: заметная шкала (hero 44–64px, H2 28–36px, body 16–18px,
  line-height 1.5–1.7), 2 гарнитуры максимум (system-ui/Inter ок), контраст ≥ 4.5:1.
• Тёмная ИЛИ светлая тема — но целостная; фон не чисто белый/чёрный, а тон из палитры.
• Глубина: мягкие тени, тонкие рамки (1px), скругления; gradient-mesh/blur-пятна в hero
  через CSS (radial-gradient), без внешних картинок. SVG-иконки, НЕ эмодзи.
• Ритм секций: щедрые вертикальные отступы (72–120px), контент в max-width ~1100px по центру.
• Микро-взаимодействия: hover на кнопках/карточках (transform: translateY/scale + смена тени,
  transition 150–250ms ease), focus-состояния видимы. Уважай prefers-reduced-motion.
• Появление секций при скролле — IntersectionObserver (fade+translateY), 1–2 акцента, не всё подряд.
• Полная адаптивность: mobile-first, никакого горизонтального скролла, тач-цели ≥ 44px.

СОДЕРЖАНИЕ: минимум 5 секций (hero с чётким оффером и 1 главным CTA, преимущества/ценность,
как работает/услуги, доверие — кейсы/отзывы/цифры, контакт+форма). Тексты — из брифа и
файлов коллег (list_files → read_file: docs/offer.md, docs/site_content.md). Без лорем-ипсума.

ФОРМА ЗАЯВКИ (КРИТИЧНО — без этого сайт бесполезен):
JS РЕАЛЬНО шлёт fetch('/api/site-lead', POST, JSON {name, contact, message}), с валидацией
и экраном «спасибо». 🚫 НИКАКИХ заглушек: «подключаем CRM», «готово к отправке», форма,
которая ничего не отправляет — ЗАПРЕЩЕНЫ. 🚫 Бэкенд не строй — эндпоинт уже хостится.

ОДНА СТРУКТУРА, БЕЗ ДУБЛЕЙ ФАЙЛОВ (частая беда — свалка из 20 почти одинаковых html):
Фиксированный набор: index.html + НЕБОЛЬШОЕ число именованных страниц. Правишь существующее —
сначала list_files+read_file, меняй ТОТ ЖЕ файл. 🚫 НЕ создавай варианты-клоны
(kuhnya.html, kuhnya-kmv.html, kuhnya-vannaya.html — это ОДНА страница) и заглушки
(page-2.html, landing-*.html). Все страницы связаны навигацией; index ссылается на реальные.

ПРОВЕРКИ ПЕРЕД СДАЧЕЙ:
1. Каждый файл записан через write_file с непустым путём; css/js подключены.
2. Есть дизайн-токены, единая типо-шкала, hover/focus, адаптив без горизонт. скролла.
3. Форма РЕАЛЬНО шлёт POST /api/site-lead (fetch, НЕ заглушка) и показывает подтверждение.
4. Нет файлов-дублей и пустых заглушек; страницы связаны навигацией.

ВЫПОЛНЕНИЕ: пиши файлы через write_file. Публиковать не нужно — офис опубликует site/ сам.\
"""

register(Skill(
    id="static_landing_site",
    title="Премиальный сайт (без 3D)",
    description="Сайт/лендинг студийного уровня в site/ — HTML/CSS/JS без шага сборки, "
                "с дизайн-токенами, микро-анимациями и формой заявки на платформенный эндпоинт.",
    keywords=["лендинг", "landing", "сайт", "одностраничник", "многостраничн",
              "страниц", "визитк", "красив", "премиальн", "стильн"],
    playbook=_STATIC_SITE_PLAYBOOK,
    roles=["designer", "developer"],
))


# ── Скилл: Telegram-бот на aiogram ────────────────────────────────────────────
_TELEGRAM_BOT_PLAYBOOK = """\
СКИЛЛ: Telegram-бот на aiogram 3.x — полный рабочий код, без сборки.

ПЕРВЫМ ДЕЛОМ: list_files → read_file для ТЗ/текстов/услуг, уже сохранённых
коллегами в workspace (docs/bot_content.md и т.п.). ask_colleague — максимум
1 раз за задачу, только если файлов реально нет.

СТРУКТУРА:
• bot.py — основной файл: polling, обработчики, FSM-состояния.
• config.py — TOKEN, тексты кнопок, цены, услуги (легко менять).
• requirements.txt — aiogram>=3.0, aiosqlite если нужна БД.

ПРИЁМЫ:
• InlineKeyboardMarkup для кнопок выбора услуг/ответов.
• FSM (aiogram.fsm.state, StatesGroup) для многошаговых диалогов.
• Бот ЗАПИСЫВАЕТ лиды в платформу через POST /api/site-lead (эндпоинт уже есть).

ПРОВЕРКИ ПЕРЕД СДАЧЕЙ (чеклист):
1. write_file — пиши ПОЛНЫЙ код (не скелеты, не заглушки, не TODO).
2. verify_code для .py файлов — исправляй ошибки до нуля.
3. execute_code — запусти и убедись, что работает.
4. ask_user перед пушем в GitHub.

ВЫПОЛНЕНИЕ: код пишешь сам через write_file; ЗАПУСК бота (реальный polling
в проде) — задача интегратора, передай через delegate_task после готовности кода.\
"""

register(Skill(
    id="telegram_bot_aiogram",
    title="Telegram-бот (aiogram)",
    description="Полный рабочий код Telegram-бота на aiogram 3.x: меню, FSM, "
                "запись лидов в платформу.",
    keywords=["telegram", "телеграм", "бот", "aiogram", "чат-бот"],
    playbook=_TELEGRAM_BOT_PLAYBOOK,
    roles=["developer"],
))


# ── Скилл: маршрутизация Telegram-бота интегратором ───────────────────────────
_BOOKING_BOT_ROUTING_PLAYBOOK = """\
СКИЛЛ: маршрутизация и запуск Telegram-бота (решает интегратор).

ПОРЯДОК:
1. list_integrations — что доступно и что уже подключено.
2. Нет учётки — запроси через ask_user с конкретной инструкцией (она есть в
   описании интеграции). Как только появилась — проверь get_me через
   use_integration и доложи статус.

РЕШЕНИЕ ПО ТИПУ БОТА:
• Бот ЗАПИСИ КЛИЕНТОВ / СБОРА ЗАЯВОК (лиды): сначала ПРЕДЛОЖИ через ask_user
  готового бота записи платформы (меню услуг → имя/телефон → заявка в «Лиды»).
  Согласен — задай услуги через configure_bot и запусти
  use_integration('telegram','launch_bot'). Клиенту мало готового (нужен
  нестандартный функционал) — поставь задачу разработчику через delegate_task,
  он напишет код, ты потом его запустишь.
• Бот ДРУГОГО НАЗНАЧЕНИЯ (постинг, рассылки, уведомления): готового бота
  записи НЕ предлагай. Используй send_message/send_photo или передай
  кастомную логику разработчику.

СТОП-УСЛОВИЕ: launch_bot вернул «ЗАПУЩЕН»/enabled/polling — бот реально
работает, задача выполнена. Напиши краткий итог и ОСТАНАВЛИВАЙСЯ — не пиши
код, не создавай файлы, не перезапускай бот повторно.

НЕ ищи в интернете внутренние функции платформы (launch_bot, bot_engine,
configure_bot) — они уже есть, смотри list_integrations.\
"""

register(Skill(
    id="booking_bot_routing",
    title="Маршрутизация Telegram-бота",
    description="Решение: готовый бот записи платформы или кастомная логика "
                "разработчика — и реальный запуск через launch_bot.",
    keywords=["telegram", "бот записи", "booking", "запустить бот", "launch",
              "подключить бот", "запись клиентов"],
    playbook=_BOOKING_BOT_ROUTING_PLAYBOOK,
    roles=["integrator"],
))


# ── Скилл: маршрутизация задачи по боту между разработчиком и интегратором ────
_CTO_BOT_ROUTING_PLAYBOOK = """\
СКИЛЛ: кому поручить Telegram-бота (решает CTO).

• Бот ЗАПИСИ / сбора лидов → поручай ИНТЕГРАТОРУ: у платформы есть готовый
  движок записи, интегратор предложит его клиенту и запустит (launch_bot).
  Разработчику код не поручай, пока клиент не отверг готового бота как
  слишком простого.
• Бот с НЕСТАНДАРТНОЙ логикой (постинг, парсинг, кастом) → сначала
  разработчику (код), потом интегратору (запуск).
• Нужен премиальный дизайн сайта, которого нет в отделе → найми designer
  через hire.\
"""

register(Skill(
    id="cto_bot_routing",
    title="Маршрутизация бота между сотрудниками",
    description="Кому поручить Telegram-бота: интегратору (готовый движок) "
                "или разработчику (кастомная логика).",
    keywords=["telegram", "бот", "маршрутиз", "кому поручить", "кто должен",
              "разработчик или интегратор"],
    playbook=_CTO_BOT_ROUTING_PLAYBOOK,
    roles=["cto"],
))


# ── Стартовые Skill'ы (обёртки поверх существующей логики) ───────────────────
async def _publish_landing(params: dict) -> str:
    """Публикация лендинга — бэкенд website-интеграции хостит сам."""
    from src.integrations import registry as integrations_registry
    integ = integrations_registry.get("website")
    if not integ:
        return "Интеграция website недоступна."
    return ("Лендинг публикуется через website.publish_landing — "
            "файлы из site/ хостятся платформой автоматически.")


async def _launch_booking_bot(params: dict) -> str:
    """Запуск шаблонного Telegram-бота записи (готовый движок платформы)."""
    return ("Бот записи запускается через telegram.launch_bot — "
            "поведение задаётся конфигом тенанта (bot_config).")


register(Skill(
    id="publish_landing", title="Опубликовать лендинг",
    description="Хостит статический сайт из site/ и собирает лиды.",
    keywords=["лендинг", "landing", "сайт", "опубликовать", "publish"],
    handler=_publish_landing,
))
register(Skill(
    id="launch_booking_bot", title="Запустить бота записи",
    description="Готовый Telegram-бот записи клиентов: меню → имя/телефон → лид.",
    keywords=["бот записи", "booking", "запись", "telegram бот", "запустить бот"],
    handler=_launch_booking_bot,
))


# Библиотека экспертных скиллов (10 плейбунков из экосистемы skills.sh) —
# импорт В КОНЦЕ, чтобы Skill/register были уже определены. Импорт этого модуля
# (`from src.office import skills`) автоматически регистрирует всю библиотеку.
from src.office import skill_library  # noqa: E402,F401
