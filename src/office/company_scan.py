"""
Instant Learning — автоскан сайта клиента по URL, БЕЗ единого вопроса и БЕЗ LLM
(вау-эффект «офис уже изучил вас» за секунды онбординга — см. project memory
company-understanding-vision). Чистый httpx + regex по HTML, $0 стоимости.

Считается сигналом, не истиной: сайт может быть недоступен/защищён — тогда
возвращается частичный результат с тем, что удалось получить.
"""

import re
import time

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


async def scan(url: str) -> dict:
    """Возвращает {ok, url, findings: [str], detected: {...}}. Не бросает исключений
    наружу — недоступный сайт тоже даёт полезный сигнал (findings об этом)."""
    url = _normalize_url(url)
    if not url:
        return {"ok": False, "url": "", "findings": [], "detected": {}, "pain_points": [], "headline": ""}

    detected: dict = {}
    findings: list[str] = []

    async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_HEADERS, follow_redirects=True) as client:
        t0 = time.monotonic()
        try:
            resp = await client.get(url)
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
    }


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
