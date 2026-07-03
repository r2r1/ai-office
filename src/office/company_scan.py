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
        return {"ok": False, "url": "", "findings": [], "detected": {}}

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
                "detected": {},
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

    return {"ok": True, "url": url, "findings": findings, "detected": detected}


def summary_line(scan_result: dict) -> str:
    """Одна строка для брифа/памяти — кратко, для контекста воркеров."""
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
    return f"Автоскан сайта {url}: " + ("; ".join(bits) if bits else "минимум признаков, изучим детальнее")
