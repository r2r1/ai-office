"""
Instant Learning — автоскан сайта клиента по URL, БЕЗ единого вопроса и БЕЗ LLM
(вау-эффект «офис уже изучил вас» за секунды онбординга — см. project memory
company-understanding-vision). Чистый httpx + regex по HTML, $0 стоимости.

Считается сигналом, не истиной: сайт может быть недоступен/защищён — тогда
возвращается частичный результат с тем, что удалось получить.
"""

import asyncio
import ipaddress
import re
import socket
import time
from urllib.parse import urlparse

import httpx

_TIMEOUT = httpx.Timeout(6.0, connect=4.0)
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; AIOfficeScan/1.0)"}

_SOCIAL_RE = {
    "instagram": re.compile(r"instagram\.com/[\w.\-]+", re.I),
    "vk": re.compile(r"vk\.com/[\w.\-]+", re.I),
    "telegram": re.compile(r"t\.me/[\w.\-]+", re.I),
    "whatsapp": re.compile(r"wa\.me/[\d]+", re.I),
    "youtube": re.compile(r"youtube\.com/[\w.\-@]+", re.I),
    "facebook": re.compile(r"facebook\.com/[\w.\-]+", re.I),
}
_CMS_MARKERS = {
    "WordPress": ("wp-content", "wp-includes", 'name="generator" content="WordPress'),
    "Tilda": ("tilda.ws", "t-records"),
    "Wix": ("wix.com", "wixstatic.com"),
    "Bitrix": ("bitrix", "/bitrix/"),
    "Webflow": ("webflow.io", "webflow.com"),
}
_EMAIL_RE = re.compile(r"[\w.\-]+@[\w\-]+\.[a-zA-Zа-яё]{2,}", re.I)
_PHONE_RE = re.compile(r"(?:\+7|8)[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}")
_CTA_RE = re.compile(
    r"(заказать|купить|оставить заявку|оставьте заявку|записаться|получить консультацию|"
    r"узнать цену|рассчитать|order now|get started|book (a|now)|contact us|buy now|sign up)",
    re.I,
)
_REVIEWS_RE = re.compile(r"(отзыв|testimonial|review)", re.I)
_QUIZ_RE = re.compile(r"(квиз|quiz)", re.I)
_FORM_RE = re.compile(r"<form\b", re.I)
_VIEWPORT_RE = re.compile(r'name=["\']viewport["\']', re.I)

# Digital Infrastructure (уровень 2): что из аналитики/CRM УЖЕ стоит на сайте
# клиента — маркеры в том же HTML, без доп. запросов.
_ANALYTICS_MARKERS = {
    "ga4": ("gtag(", "googletagmanager.com/gtag", "google-analytics.com"),
    "yandex_metrika": ("mc.yandex.ru", "ym(", "yandex_metrika"),
    "vk_pixel": ("vk.com/js/api/openapi", "VK.Retargeting"),
    "meta_pixel": ("connect.facebook.net", "fbq("),
}
_CRM_MARKERS = {
    "amocrm": ("amocrm.ru", "amocrm_id", "amo_forms"),
    "bitrix24": ("bitrix24", "b24-form"),
}


def _ru_plural(n: int) -> str:
    """«точку/точки/точек роста» (винительный падеж — «нашли N ...»)."""
    n = abs(n) % 100
    if 11 <= n <= 14:
        return "точек роста"
    last = n % 10
    if last == 1:
        return "точку роста"
    if 2 <= last <= 4:
        return "точки роста"
    return "точек роста"


def _normalize_url(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        return ""
    if not raw.startswith(("http://", "https://")):
        raw = "https://" + raw
    return raw


def _is_private_host(host: str) -> bool:
    """SSRF-защита: раньше scan() вызывался только авторизованными пользователями
    (за auth_middleware), теперь эндпоинт публичный (см. docs/architecture-
    improvements.md — Instant Learning до регистрации) — любой аноним может
    попросить сервер обратиться по указанному URL. Без этой проверки это прямой
    путь просканировать localhost/внутреннюю сеть/облачные metadata-эндпоинты
    (169.254.169.254) от имени сервера."""
    host = (host or "").strip().lower().rstrip(".")
    if not host or host == "localhost" or host.endswith(".local"):
        return True
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return True  # не резолвится — не сканируем вслепую
    for info in infos:
        ip = info[4][0]
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            return True
        if (addr.is_private or addr.is_loopback or addr.is_link_local
                or addr.is_reserved or addr.is_multicast or addr.is_unspecified):
            return True
    return False


async def scan(url: str) -> dict:
    """Возвращает {ok, url, findings: [str], detected: {...}}. Не бросает исключений
    наружу — недоступный сайт тоже даёт полезный сигнал (findings об этом)."""
    url = _normalize_url(url)
    if not url:
        return {"ok": False, "url": "", "findings": [], "detected": {}, "pain_points": [], "headline": ""}
    if _is_private_host(urlparse(url).hostname or ""):
        return {"ok": False, "url": url, "findings": ["Этот адрес нельзя просканировать"],
                "detected": {}, "pain_points": [], "headline": ""}

    detected: dict = {}
    findings: list[str] = []

    # follow_redirects=False + ручные хопы: httpx следует за Location без повторной
    # проверки хоста — сайт мог бы 302-редиректнуть на http://169.254.169.254/... и
    # обойти проверку выше. Проверяем КАЖДЫЙ хоп заново (эндпоинт публичный, см.
    # _is_private_host).
    from urllib.parse import urljoin
    async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_HEADERS, follow_redirects=False) as client:
        t0 = time.monotonic()
        try:
            hop_url = url
            resp = None
            for _ in range(5):
                resp = await client.get(hop_url)
                if resp.status_code not in (301, 302, 303, 307, 308) or "location" not in resp.headers:
                    break
                hop_url = urljoin(hop_url, resp.headers["location"])
                if _is_private_host(urlparse(hop_url).hostname or ""):
                    return {"ok": False, "url": url, "findings": ["Этот адрес нельзя просканировать"],
                            "detected": {}, "pain_points": [], "headline": ""}
            url = hop_url
            elapsed_ms = int((time.monotonic() - t0) * 1000)
        except Exception:
            return {
                "ok": False, "url": url,
                "findings": ["Сайт недоступен по этому адресу — уточним у клиента напрямую"],
                "detected": {}, "pain_points": [], "headline": "",
            }

        html = resp.text or ""
        detected["status_code"] = resp.status_code
        detected["response_ms"] = elapsed_ms
        findings.append(f"Сайт отвечает за {elapsed_ms} мс" + (" — многовато" if elapsed_ms > 1500 else ""))

        title_m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
        if title_m:
            title = re.sub(r"\s+", " ", title_m.group(1)).strip()[:120]
            detected["title"] = title
            findings.append(f"Заголовок страницы: «{title}»")

        desc_m = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)', html, re.I)
        if desc_m:
            detected["meta_description"] = desc_m.group(1).strip()[:200]
            findings.append("Есть meta description")
        else:
            findings.append("Нет meta description — минус к SEO")

        cms = next((name for name, markers in _CMS_MARKERS.items()
                    if any(m.lower() in html.lower() for m in markers)), None)
        if cms:
            detected["cms"] = cms
            findings.append(f"Платформа: {cms}")

        socials = {k: m.group(0) for k, r in _SOCIAL_RE.items() if (m := r.search(html))}
        if socials:
            detected["socials"] = socials
            findings.append("Соцсети: " + ", ".join(socials))
        else:
            findings.append("Ссылок на соцсети на главной не найдено")

        emails = sorted(set(_EMAIL_RE.findall(html)))[:3]
        phones = sorted(set(_PHONE_RE.findall(html)))[:3]
        if emails:
            detected["emails"] = emails
        if phones:
            detected["phones"] = phones
        if emails or phones:
            findings.append("Контакты найдены: " + ", ".join(emails + phones))
        else:
            findings.append("Контакты на главной не найдены")

        links_count = len(re.findall(r"<a\s", html, re.I))
        detected["links_on_page"] = links_count

        detected["has_cta"] = bool(_CTA_RE.search(html))
        detected["has_form"] = bool(_FORM_RE.search(html))
        detected["has_reviews"] = bool(_REVIEWS_RE.search(html))
        detected["has_quiz"] = bool(_QUIZ_RE.search(html))
        detected["has_viewport"] = bool(_VIEWPORT_RE.search(html))

        html_lower = html.lower()
        detected["analytics"] = {name: any(m.lower() in html_lower for m in markers)
                                 for name, markers in _ANALYTICS_MARKERS.items()}
        detected["crm_widgets"] = {name: any(m.lower() in html_lower for m in markers)
                                   for name, markers in _CRM_MARKERS.items()}

        favicon = bool(re.search(r'rel=["\'][^"\']*icon', html, re.I))
        detected["favicon"] = favicon
        if not favicon:
            findings.append("Нет favicon")

        detected["https"] = url.startswith("https://")
        if not detected["https"]:
            findings.append("Сайт без HTTPS")

        # robots.txt / sitemap.xml — дешёвые доп. запросы, best-effort
        base = re.match(r"(https?://[^/]+)", url).group(1)
        for path, key, label in (
            ("/robots.txt", "robots", "robots.txt"),
            ("/sitemap.xml", "sitemap", "sitemap.xml"),
        ):
            try:
                r2 = await client.get(base + path)
                ok = r2.status_code == 200
            except Exception:
                ok = False
            detected[key] = ok
            findings.append(f"{label}: {'найден' if ok else 'не найден'}")

    pain_points = _pain_points(detected)
    headline = f"Нашли {len(pain_points)} {_ru_plural(len(pain_points))} для вашего сайта" if pain_points \
        else "Явных проблем не нашли — сайт в целом в порядке"
    return {
        "ok": True, "url": url, "findings": findings, "detected": detected,
        "pain_points": pain_points, "headline": headline,
        "stage": await _stage_hypothesis(detected, findings, pain_points),
    }


# Гипотеза о стадии бизнеса — ИМЕННО гипотеза («похоже, вы...»), не вердикт:
# владелец подтверждает/поправляет на лендинге/в онбординге (см. product-разбор
# Company Understanding — стадия важна как повод для диалога, не готовый ответ).
#
# ⚠️ С LLM, а не чистой эвристикой (по явному запросу) — это НАРУШАЕТ инвариант
# "company_scan.py = $0, без LLM", на котором держится остальной модуль, и это
# осознанный компромисс, не недосмотр: эндпоинт ПУБЛИЧНЫЙ (см. server.py
# _PUBLIC_API, issue #19), значит КАЖДЫЙ анонимный визит на лендинг с непустым
# полем URL теперь стоит реальных денег с общего баланса платформы, а не
# конкретного тенанта (анонимные запросы всегда попадают в тенант "default" —
# см. saas/context.tenant_middleware). Ограничено тем же rate-limit 12/мин на
# IP, что и сам /api/onboarding/scan; дешёвая модель + маленький max_tokens
# держат стоимость одного вызова минимальной. Эвристика (`_stage_heuristic`)
# остаётся safety-фолбэком — при любой ошибке LLM (нет баланса, таймаут,
# провайдер недоступен) отдаём её вместо того, чтобы попытка "wow" сломала
# весь скан.
_STAGES = ("idea", "launch", "growth", "mature")
_STAGE_LABELS = {
    "idea": "на стадии идеи", "launch": "на стадии запуска",
    "growth": "в активном росте", "mature": "зрелой компанией",
}


# Жёсткий короткий таймаут ИМЕННО на этот вызов — независимо от llm.CALL_TIMEOUT
# (180с, рассчитан на настоящие рабочие задачи агентов). Живой замер в этой же
# сессии: обычный вызов run_agent для этой короткой классификации занял 156.9с
# (apinet/glm-4.5-flash под нагрузкой) — это НЕПРИЕМЛЕМО для лендинга перед
# регистрацией: посетитель не ждёт больше нескольких секунд ни при каких
# обстоятельствах. Лучше отдать эвристику мгновенно, чем красивую гипотезу
# через 2.5 минуты.
_STAGE_LLM_TIMEOUT = 8.0


async def _stage_hypothesis(detected: dict, findings: list[str], pain_points: list[str]) -> dict | None:
    heuristic = _stage_heuristic(detected)
    if heuristic is None:
        return None
    try:
        import asyncio as _asyncio
        import json as _json
        from src.core import llm as llm_module
        system = ("Ты аналитик, который по данным автоскана сайта определяет вероятную стадию бизнеса. "
                  "Отвечай ТОЛЬКО JSON без пояснений вокруг.")
        user = (
            f"Сигналы сайта: {findings}\n"
            f"Точки роста (проблемы): {pain_points}\n"
            f"Технические флаги: CRM={any((detected.get('crm_widgets') or {}).values())}, "
            f"аналитика={any((detected.get('analytics') or {}).values())}, "
            f"отзывы={bool(detected.get('has_reviews'))}, форма заявки={bool(detected.get('has_form'))}\n\n"
            'Определи стадию из списка ["idea","launch","growth","mature"] и верни ровно такой JSON:\n'
            '{"key": "growth", "label": "короткая фраза для владельца, например «в активном росте»", '
            '"reason": "одно короткое предложение почему, на русском"}'
        )
        raw = await _asyncio.wait_for(
            llm_module.run_agent(
                system=system, user=user, model="glm-4.5-flash", max_tokens=200,
                use_search=False, max_iterations=1, agent_id="landing_scan",
            ),
            timeout=_STAGE_LLM_TIMEOUT,
        )
        start, end = raw.find("{"), raw.rfind("}")
        parsed = _json.loads(raw[start:end + 1]) if start >= 0 and end > start else {}
        if parsed.get("key") in _STAGES and parsed.get("label") and parsed.get("reason"):
            return {"key": parsed["key"], "label": parsed["label"], "reason": parsed["reason"]}
    except Exception:
        pass
    return heuristic


def _stage_heuristic(detected: dict) -> dict | None:
    """Возвращает {key, label, reason} или None, если сигналов мало (например
    сайт недоступен — detected пуст). Safety-фолбэк для _stage_hypothesis (см. её
    докстринг) — если LLM недоступна/упала, гипотеза всё равно приходит, просто
    менее гибкая."""
    if not detected:
        return None
    has_crm = any((detected.get("crm_widgets") or {}).values())
    has_analytics = any((detected.get("analytics") or {}).values())
    has_reviews = bool(detected.get("has_reviews"))
    has_form = bool(detected.get("has_form"))
    has_cta = bool(detected.get("has_cta"))
    has_contacts = bool(detected.get("emails") or detected.get("phones"))

    if has_crm and has_analytics and has_reviews:
        return {"key": "mature", "label": _STAGE_LABELS["mature"],
                "reason": "на сайте есть CRM, аналитика и отзывы — обычно так выглядит уже отлаженный бизнес"}
    if has_crm or has_analytics:
        return {"key": "growth", "label": _STAGE_LABELS["growth"],
                "reason": ("CRM" if has_crm else "аналитика") + " на сайте — значит, вы уже считаете заявки и клиентов"}
    if has_form or has_cta or has_contacts:
        return {"key": "launch", "label": _STAGE_LABELS["launch"],
                "reason": "сайт уже принимает заявки, но без CRM и аналитики"}
    return {"key": "idea", "label": _STAGE_LABELS["idea"],
            "reason": "на сайте нет ни формы заявки, ни аналитики, ни контактов — скорее визитка под будущий продукт"}


# Технический факт → на что это влияет для ВЛАДЕЛЬЦА бизнеса, не для разработчика
# (прод-находка: «Нашёл WordPress» ничего не говорит владельцу — важно не «что
# стоит», а «что это стоит бизнесу»). Порядок — по убыванию важности для лидов.
def _pain_points(detected: dict) -> list[str]:
    points: list[str] = []
    if not detected.get("has_cta"):
        points.append("Нет чёткого призыва к действию — посетитель не понимает, что делать дальше")
    if not detected.get("has_form") and not detected.get("emails") and not detected.get("phones"):
        points.append("Не нашли способа оставить заявку или написать — часть посетителей просто уходит")
    if detected.get("response_ms", 0) > 1500:
        points.append("Сайт открывается медленно — часть посетителей закрывает вкладку, не дождавшись")
    if not detected.get("has_reviews"):
        points.append("На сайте нет отзывов — это снижает доверие к компании")
    if not detected.get("socials"):
        points.append("Не привязаны соцсети — сложнее возвращать посетителей и вести диалог")
    if not detected.get("meta_description"):
        points.append("Сайт слабо настроен для поиска — теряются бесплатные переходы из Google/Яндекс")
    if not detected.get("https"):
        points.append("Сайт без HTTPS — браузер может помечать его как небезопасный")
    if not detected.get("has_viewport"):
        points.append("Нет мобильной адаптации — доля мобильных посетителей уходит сразу")
    return points[:6]


def summary_line(scan_result: dict) -> str:
    """Одна строка для брифа/памяти — кратко, для контекста воркеров. Включает
    и технические факты (нужны разработчику/архитектору), и бизнес-боли
    (нужны маркетингу/стратегу) — оба слоя читают один и тот же бриф."""
    if not scan_result or not scan_result.get("ok"):
        return ""
    d = scan_result.get("detected", {})
    bits = []
    # title/meta_description — САМЫЕ бизнес-значимые факты скана (что компания
    # реально делает); без них воркеры знали CMS сайта, но не бизнес клиента.
    if d.get("title"):
        bits.append(f"заголовок сайта: «{d['title']}»")
    if d.get("meta_description"):
        bits.append(f"описание: {d['meta_description'][:160]}")
    if d.get("cms"):
        bits.append(d["cms"])
    if d.get("socials"):
        bits.append("соцсети: " + ", ".join(d["socials"]))
    if d.get("emails"):
        bits.append("email: " + d["emails"][0])
    if d.get("phones"):
        bits.append("тел: " + d["phones"][0])
    url = scan_result.get("url", "")
    line = f"Автоскан сайта {url}: " + ("; ".join(bits) if bits else "минимум признаков, изучим детальнее")
    pain_points = scan_result.get("pain_points") or []
    if pain_points:
        line += ". Точки роста: " + "; ".join(pain_points)
    return line


# ─────────────────────── Первое расследование: поиск БЕЗ готового URL ───────────────────────
#
# docs/first-investigation-plan-2026-07-16.md, Фаза 1: раньше единственный источник
# знаний о компании — HTML одной страницы, которую ДОЛЖЕН дать сам пользователь
# (scan(url) выше). Если URL не дали (типичный случай — "корпусная мебель", без
# сайта), business_stage не появлялся ВООБЩЕ, и дальше по цепочке LLM молча
# угадывал стадию бизнеса из воздуха (реальная находка, разбор с владельцем
# 2026-07-16). search_company() ищет компанию/рынок в вебе по нише+региону+(опц.)
# имени — не ждёт готовую ссылку.
#
# Источник данных здесь — сниппеты поисковой выдачи (title/body/href), НЕ полный
# HTML страницы, поэтому сигнал заведомо слабее, чем у scan(): результат ВСЕГДА
# несёт явное поле confidence (unconfirmed/inferred), никогда не молчаливое
# отсутствие стадии, как раньше. Значение "confirmed" здесь не выставляется —
# оно принадлежит либо прямому scan() полной страницы, либо явному подтверждению
# владельцем (см. LandingView.tsx correctStage) — search_company() по построению
# не может знать наверняка, только предполагать.
_SEARCH_BUDGET_SECONDS = 20.0  # суммарный суббюджет на все формулировки запроса

# Домены-агрегаторы, по которым результат поиска классифицируется как реальное
# присутствие компании в вебе (не просто "упоминание где-то в статье") — то же
# семейство источников, что и _SOCIAL_RE выше, но для ссылок ИЗ ВЫДАЧИ поиска,
# а не с самой HTML-страницы.
_AGGREGATOR_HOSTS: dict[str, tuple[str, str]] = {
    "vk.com": ("vk", "VK"),
    "instagram.com": ("instagram", "Instagram"),
    "t.me": ("telegram", "Telegram-канал"),
    "2gis.ru": ("2gis", "2ГИС"),
    "avito.ru": ("avito", "Авито"),
    "yandex.ru": ("yandex_maps", "Яндекс.Картах/Бизнесе"),
    "maps.google.com": ("google_maps", "Google Картах"),
    "flamp.ru": ("flamp", "отзывах на Flamp"),
    "zoon.ru": ("zoon", "отзывах на Zoon"),
}

_REVIEW_SIGNAL_RE = re.compile(r"отзыв|рейтинг|★|rating|review", re.I)


def _classify_result_host(href: str) -> tuple[str, str] | None:
    host = (urlparse(href).hostname or "").lower()
    host = host[4:] if host.startswith("www.") else host
    for known, val in _AGGREGATOR_HOSTS.items():
        if host == known or host.endswith("." + known):
            return val
    return None


def _investigation_queries(niche: str, region: str, name: str) -> list[str]:
    """Формулировки запроса по убыванию специфичности — как решено в обсуждении:
    несколько попыток (с именем/без, с регионом/без) до честной сдачи, не одна
    попытка и не бесконечный перебор."""
    queries: list[str] = []
    if name:
        if niche or region:
            queries.append(" ".join(p for p in (name, niche, region) if p))
        queries.append(" ".join(p for p in (name, region) if p) or name)
    if niche:
        queries.append(" ".join(p for p in (niche, region) if p))
        if region:
            queries.append(niche)  # без региона — последний резерв, если и это не дало сигнала
    seen: set[str] = set()
    out = []
    for q in queries:
        if q and q not in seen:
            seen.add(q)
            out.append(q)
    return out


async def search_company(niche: str = "", region: str = "", name: str = "") -> dict:
    """Ищет компанию/рынок в вебе по нише+региону+(опц.)имени — БЕЗ готового URL
    (см. docstring секции выше). Не бросает исключений наружу — недоступность
    поиска тоже честный исход (см. `stage.confidence == "unconfirmed"`).

    Возвращает {ok, queries_tried, candidates: [{title, snippet, url, source}],
    detected: {...}, stage: {key, label, reason, confidence}, findings: [...]}.
    """
    niche = (niche or "").strip()[:120]
    region = (region or "").strip()[:80]
    name = (name or "").strip()[:120]

    if not niche and not name:
        return {
            "ok": False, "queries_tried": [], "candidates": [], "detected": {},
            "stage": {"key": "idea", "label": _STAGE_LABELS["idea"], "confidence": "unconfirmed",
                     "reason": "ни ниша, ни название не указаны — искать нечему"},
            "findings": [],
        }

    queries = _investigation_queries(niche, region, name)
    t0 = time.monotonic()
    results: list[dict] = []
    tried: list[str] = []
    from src.core import search as search_module

    for q in queries:
        remaining = _SEARCH_BUDGET_SECONDS - (time.monotonic() - t0)
        if remaining <= 1.0:
            break
        tried.append(q)
        try:
            results = await asyncio.wait_for(
                asyncio.to_thread(search_module.web_search_raw, q, 6, 8),
                timeout=min(remaining, 10.0),
            )
        except Exception:
            results = []
        if results:
            break  # эта формулировка дала сигнал — не тратим остаток бюджета на следующие

    candidates: list[dict] = []
    aggregator_hits: dict[str, str] = {}
    has_reviews_signal = False
    for r in results[:6]:
        href = r.get("href", "") or ""
        title = r.get("title", "") or ""
        body = r.get("body", "") or ""
        cls = _classify_result_host(href)
        source = cls[0] if cls else "web"
        if cls:
            aggregator_hits[cls[0]] = cls[1]
        if _REVIEW_SIGNAL_RE.search(f"{title} {body}"):
            has_reviews_signal = True
        candidates.append({"title": title[:160], "snippet": body[:220], "url": href, "source": source})

    detected = {
        "queries_tried": tried,
        "aggregators": aggregator_hits,
        "has_reviews_signal": has_reviews_signal,
        "candidates_count": len(candidates),
    }
    last_query = tried[-1] if tried else ""

    if not candidates:
        stage = {"key": "idea", "label": _STAGE_LABELS["idea"], "confidence": "unconfirmed",
                 "reason": f"не нашёл сигналов в сети ни по одной из {len(tried)} формулировок запроса — "
                          "либо компания только начинает, либо ищу не там"}
        findings = [f"Пробовал {len(tried)} формулировок запроса — ничего не нашёл"]
    elif not name:
        # Есть результаты, но без имени они привязаны к нише/рынку в целом,
        # не к конкретной компании — законный исход "нашёл рынок, не компанию".
        stage = {"key": "idea", "label": _STAGE_LABELS["idea"], "confidence": "unconfirmed",
                 "reason": "нашёл рынок и похожие компании в этой нише, но не название вашей — "
                          "имени не было в запросе, привязать находки не к чему"}
        findings = [f"Нашёл {len(candidates)} результатов по рынку «{niche}»" + (f" в {region}" if region else "")]
    elif aggregator_hits and has_reviews_signal:
        stage = {"key": "growth", "label": _STAGE_LABELS["growth"], "confidence": "inferred",
                 "reason": "нашёл вас в " + ", ".join(aggregator_hits.values()) +
                          " с отзывами — похоже, вы уже работаете с клиентами"}
        findings = [f"Нашёл {len(candidates)} результатов по «{last_query}», есть отзывы"]
    elif aggregator_hits:
        stage = {"key": "launch", "label": _STAGE_LABELS["launch"], "confidence": "inferred",
                 "reason": "нашёл вас в " + ", ".join(aggregator_hits.values()) +
                          " — присутствие есть, но следов активности (отзывов) не вижу"}
        findings = [f"Нашёл {len(candidates)} результатов по «{last_query}»"]
    else:
        stage = {"key": "idea", "label": _STAGE_LABELS["idea"], "confidence": "unconfirmed",
                 "reason": "нашёл что-то похожее по названию, но не в узнаваемых источниках "
                          "(соцсети/карты/агрегаторы) — не уверен, что это точно вы"}
        findings = [f"Нашёл {len(candidates)} результатов по «{last_query}», но без явного подтверждения"]

    return {
        "ok": bool(candidates), "queries_tried": tried, "candidates": candidates,
        "detected": detected, "stage": stage, "findings": findings,
    }
