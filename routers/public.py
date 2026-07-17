"""
Публичные маршруты: опубликованные сайты, приложения-прокси, оплата, приём лидов, Telegram-вебхук, конфиг бота записи. Перенесено из server.py (docs/technical-due-diligence-
2026-07-17.md §3.2.1, PR-5) механически — тот же код, то же поведение.
"""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from fastapi.responses import JSONResponse
from fastapi.responses import RedirectResponse
from fastapi.requests import Request
from fastapi.responses import Response
from src.office import bot_config as bot_config_module
from src.office import bot_engine as bot_engine_module
from src.office import bus
import json
from src.office import leads as leads_module
from src.integrations import payments as payments_module
from src.saas import context as saas_context
from src.office import sites as sites_module
from src.office import threads as threads_module
from routers.shared import client_ip as _client_ip
from routers.shared import rate_limited as _rate_limited
from routers.shared import serve_site_file as _serve_site_file

router = APIRouter()


@router.get("/site/{tenant}/{slug}", response_class=HTMLResponse)
async def serve_site(tenant: str, slug: str):
    """Отдаёт опубликованный сайт тенанта (публично). Инлайн-лендинг или папка с файлами."""
    saas_context.set_tenant(tenant)
    site = sites_module.get(slug)
    if site is None:
        return HTMLResponse("<h1>Страница не найдена</h1>", status_code=404)
    if site.get("html") is not None:
        return HTMLResponse(site["html"])  # шаблонный лендинг (publish_landing)
    return _serve_site_file(site, "index.html")  # многофайловый сайт (publish_site)


@router.get("/site/{tenant}/{slug}/{path:path}")
async def serve_site_asset(tenant: str, slug: str, path: str):
    """Отдаёт ресурс многофайлового сайта (css/js/картинки/доп. страницы)."""
    saas_context.set_tenant(tenant)
    site = sites_module.get(slug)
    if site is None or site.get("html") is not None:
        return HTMLResponse("<h1>Не найдено</h1>", status_code=404)
    return _serve_site_file(site, path or "index.html")

@router.api_route("/apps/{tenant}/{app_id}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
@router.api_route("/apps/{tenant}/{app_id}/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def proxy_tenant_app(request: Request, tenant: str, app_id: str, path: str = ""):
    """Reverse-proxy к постоянному приложению тенанта (office/tenant_apps.py —
    например self-hosted Postiz). Тенант НЕ получает прямой сетевой доступ к
    порту хоста — платформа проксирует запрос сама, тот же приём, что уже есть
    у /site/{tenant}/{slug} для лендингов, только двусторонний (методы+тело)."""
    saas_context.set_tenant(tenant)
    from src.office import tenant_apps
    app_item = tenant_apps.get(app_id)
    if app_item is None or app_item.get("status") != "running":
        return HTMLResponse("<h1>Приложение не найдено или не запущено</h1>", status_code=404)
    import httpx
    url = f"http://127.0.0.1:{app_item['host_port']}/{path}"
    headers = {k: v for k, v in request.headers.items() if k.lower() not in ("host", "content-length")}
    body = await request.body()
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            upstream = await client.request(request.method, url, params=request.query_params,
                                             headers=headers, content=body)
    except httpx.ConnectError:
        return HTMLResponse("<h1>Приложение не отвечает</h1>", status_code=502)
    resp_headers = {k: v for k, v in upstream.headers.items()
                    if k.lower() not in ("content-encoding", "transfer-encoding", "connection")}
    return Response(content=upstream.content, status_code=upstream.status_code,
                    headers=resp_headers, media_type=upstream.headers.get("content-type"))

@router.get("/pay/{tenant}/{payment_id}", response_class=HTMLResponse)
async def serve_test_checkout(tenant: str, payment_id: str):
    """Публичная TEST-страница оплаты (см. src/integrations/payments.py) — пока нет
    реального провайдера, ссылка ведёт сюда и позволяет вручную «оплатить» для
    проверки сценария целиком (форма → лид → ссылка на оплату → статус paid)."""
    saas_context.set_tenant(tenant)
    p = payments_module.get(payment_id)
    if p is None:
        return HTMLResponse("<h1>Платёж не найден</h1>", status_code=404)
    paid = p["status"] == "paid"
    action = ("<p style='color:#1a7a4a;font-weight:600'>✅ Оплачено (тест)</p>" if paid else
              f"<form method='post' action='/api/payments/{tenant}/{payment_id}/mark-paid'>"
              f"<button style='padding:12px 20px;font-size:16px;border-radius:8px;border:none;"
              f"background:#1a7a4a;color:#fff;cursor:pointer'>Оплатить (тест)</button></form>")
    return HTMLResponse(f"""<!doctype html><html lang="ru"><head><meta charset="utf-8">
<title>Тестовая оплата</title></head>
<body style="font-family:system-ui,sans-serif;max-width:420px;margin:60px auto;text-align:center">
<h2>{p['description']}</h2>
<p style="font-size:28px;font-weight:700">{p['amount']} {p['currency']}</p>
<p style="color:#888;font-size:13px">⚠️ Тестовый режим — реальный платёжный провайдер не подключён,
деньги не списываются.</p>
{action}
</body></html>""")

@router.post("/api/payments/{tenant}/{payment_id}/mark-paid")
async def mark_payment_paid(tenant: str, payment_id: str):
    """Имитация вебхука провайдера — единственный способ перевести тестовый платёж
    в paid, пока реального провайдера нет (см. payments.py::mark_paid)."""
    saas_context.set_tenant(tenant)
    p = payments_module.mark_paid(payment_id)
    if p is None:
        return JSONResponse({"error": "платёж не найден или уже обработан"}, status_code=404)
    return RedirectResponse(url=f"/pay/{tenant}/{payment_id}", status_code=303)

async def _notify_lead(lead: dict) -> None:
    """
    Заметное уведомление о новой заявке: событие в ленту + сообщение в личный чат CEO,
    чтобы сработал бейдж непрочитанного (раньше лид был только строкой в SSE-ленте и
    легко терялся — для лид-ген продукта это ключевое событие).
    """
    text = f"🎯 Новая заявка с сайта: {lead.get('name') or 'без имени'} — {lead.get('contact','')}"
    if (lead.get("message") or "").strip():
        text += f'\n«{lead["message"][:160]}»'
    await bus.publish({"type": "lead_captured", "slug": lead.get("slug", ""), "lead": lead, "text": text})
    try:
        threads_module.post("orchestrator_1", "agent", text, kind="msg")
        await bus.publish({"type": "agent_message", "agent_id": "orchestrator_1",
                           "from": "agent", "kind": "msg", "text": text})
    except Exception:
        pass

async def _lead_payload(request: Request) -> tuple[dict, bool]:
    """
    Данные заявки из запроса: JSON ИЛИ обычная HTML-форма (form-urlencoded/multipart).
    Агенты иногда делают <form method=POST action=...> без fetch — раньше такой POST
    падал на request.json() → data={} → 400 «нужен контакт», и ЛИД ТЕРЯЛСЯ (реальный
    кейс из прода). Возвращает (data, is_native_form) — для нативной формы отвечаем
    HTML-страницей «Спасибо», а не JSON.
    """
    ctype = (request.headers.get("content-type") or "").lower()
    if "json" in ctype:
        try:
            return dict(await request.json()), False
        except Exception:
            return {}, False
    if "form" in ctype:  # application/x-www-form-urlencoded или multipart/form-data
        try:
            form = await request.form()
            return {k: str(v) for k, v in form.items()}, True
        except Exception:
            return {}, True
    try:  # content-type не выставлен — пробуем JSON, затем форму
        return dict(await request.json()), False
    except Exception:
        try:
            form = await request.form()
            return {k: str(v) for k, v in form.items()}, True
        except Exception:
            return {}, False


_LEAD_THANKS_HTML = """<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Заявка отправлена</title>
<style>body{margin:0;min-height:100svh;display:grid;place-items:center;font-family:Inter,system-ui,Arial,sans-serif;background:#0d1220;color:#ecf2ff}.card{max-width:440px;padding:40px 36px;text-align:center;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.12);border-radius:22px}.ok{font-size:44px}h1{font-size:22px;margin:14px 0 8px}p{color:#a9b5d1;line-height:1.6;margin:0 0 22px}a{display:inline-block;padding:12px 22px;border-radius:12px;background:linear-gradient(135deg,#8dd3ff,#6f8cff);color:#08111f;font-weight:700;text-decoration:none}</style>
</head><body><div class="card"><div class="ok">✅</div><h1>Заявка отправлена</h1>
<p>Спасибо! Мы получили вашу заявку и свяжемся с вами в ближайшее время.</p>
<a href="javascript:history.back()">← Вернуться на сайт</a></div></body></html>"""

# Нативная HTML-форма без контакта: посетитель должен увидеть страницу с просьбой
# вернуться и заполнить поле, а не сырой JSON {"error": ...} (реальный UX публичного сайта).
_LEAD_NO_CONTACT_HTML = _LEAD_THANKS_HTML \
    .replace('<title>Заявка отправлена</title>', '<title>Не хватает контакта</title>') \
    .replace('<div class="ok">✅</div>', '<div class="ok">✍️</div>') \
    .replace('<h1>Заявка отправлена</h1>', '<h1>Не хватает контакта</h1>') \
    .replace('Спасибо! Мы получили вашу заявку и свяжемся с вами в ближайшее время.',
             'Укажите, пожалуйста, телефон или email — иначе мы не сможем с вами связаться.')

def _extract_lead_fields(data: dict) -> tuple[str, str, str]:
    """Имя/контакт/сообщение из полей формы с учётом всех вариантов имён полей агентов."""
    name = (data.get("name") or data.get("имя") or "").strip()
    contact = (data.get("contact") or data.get("phone") or data.get("tel")
               or data.get("telefon") or data.get("email") or data.get("телефон") or "").strip()
    msg = (data.get("message") or data.get("comment") or data.get("комментарий") or "").strip()
    # Служебные поля (utm_*, quiz-выбор) — в хвост сообщения, чтобы не терять контекст лида.
    extra = "; ".join(f"{k}={v}" for k, v in data.items()
                      if v and k not in ("name", "имя", "contact", "phone", "tel", "telefon",
                                         "email", "телефон", "message", "comment", "комментарий"))
    if extra:
        msg = (msg + " | " + extra) if msg else extra
    return name, contact, msg[:600]

@router.post("/api/lead/{tenant}/{slug}")
async def capture_lead(tenant: str, slug: str, request: Request):
    """Приём заявки с формы лендинга — реальный лид для тенанта (публично)."""
    if _rate_limited("lead", _client_ip(request), 20):
        return JSONResponse({"error": "слишком много заявок, попробуйте позже"}, status_code=429)
    saas_context.set_tenant(tenant)
    if sites_module.get(slug) is None:
        return JSONResponse({"error": "страница не найдена"}, status_code=404)
    data, native = await _lead_payload(request)
    name, contact, msg = _extract_lead_fields(data)
    if not contact:
        if native:
            return HTMLResponse(_LEAD_NO_CONTACT_HTML, status_code=400)
        return JSONResponse({"error": "нужен контакт"}, status_code=400)
    lead = leads_module.add(slug, name, contact, msg)
    _record_lead_metrics()
    await _notify_lead(dict(lead, slug=slug))
    return HTMLResponse(_LEAD_THANKS_HTML) if native else {"ok": True}

def _record_lead_metrics() -> None:
    """Снимок метрик при новом лиде — тренд «заявки/выручка» пополняется фактом
    (Measurement, Phase 3b). Не роняет приём лида, если что-то пошло не так."""
    try:
        from src.office import metrics as metrics_module
        metrics_module.collect()
    except Exception:
        pass

@router.post("/api/site-lead")
async def capture_site_lead(request: Request):
    """
    Приём заявки с многофайлового сайта. Тенант и slug берутся из Referer
    (страница хостится по /site/{tenant}/{slug}/...), поэтому форма может слать
    POST на стабильный /api/site-lead, не зная slug заранее.
    """
    import re as _re
    ref = request.headers.get("referer") or request.headers.get("origin") or ""
    m = _re.search(r"/site/([^/]+)/([^/?#]+)", ref)
    if not m:
        return JSONResponse({"error": "не удалось определить сайт"}, status_code=400)
    tenant, slug = m.group(1), m.group(2)
    saas_context.set_tenant(tenant)
    if sites_module.get(slug) is None:
        return JSONResponse({"error": "сайт не найден"}, status_code=404)
    data, native = await _lead_payload(request)
    name, contact, msg = _extract_lead_fields(data)
    if not contact:
        if native:
            return HTMLResponse(_LEAD_NO_CONTACT_HTML, status_code=400)
        return JSONResponse({"error": "нужен контакт (телефон или email)"}, status_code=400)
    lead = leads_module.add(slug, name, contact, msg)
    _record_lead_metrics()
    await _notify_lead(dict(lead, slug=slug))
    return HTMLResponse(_LEAD_THANKS_HTML) if native else {"ok": True}

@router.post("/tg/{tenant}/{secret}")
async def telegram_webhook(tenant: str, secret: str, request: Request):
    """Вебхук Telegram: апдейты бота клиента (публично — вызывает Telegram).

    Безопасность: secret в URL должен совпадать с конфигом тенанта. Движок один
    (bot_engine), поведение бота определяется конфигом этого тенанта.

    Идемпотентность (docs/technical-due-diligence-2026-07-17.md §5.6): Telegram
    ретраит вебхук, если не получил 200 вовремя (медленный handle_update) — тот
    же update_id мог обработаться дважды (два ответа боту, задвоенный лид).
    Ключ дедупликации берём из САМОГО апдейта (update_id — Telegram гарантирует
    его уникальность и монотонный рост на бота), не от клиента: это server-to-
    server вебхук, а не действие владельца в UI, спрашивать заголовок не у кого.
    """
    saas_context.set_tenant(tenant)
    cfg = bot_config_module.get()
    if not cfg.get("enabled") or secret != cfg.get("webhook_secret"):
        return {"ok": True}  # тихо игнорируем чужие/выключенные
    try:
        update = await request.json()
    except Exception:
        return {"ok": True}

    async def _handle():
        try:
            await bot_engine_module.handle_update(update)
        except Exception:
            pass  # не отдаём Telegram ошибку, чтобы он не ретраил бесконечно
        return {"ok": True}

    update_id = update.get("update_id")
    if update_id is None:
        return await _handle()
    from routers.shared import idempotent
    return await idempotent(f"tg_update:{tenant}", str(update_id), 600, _handle)

@router.get("/api/bot")
async def get_bot_config():
    """Текущий конфиг Telegram-бота тенанта (для UI/агентов)."""
    cfg = bot_config_module.get()
    cfg["has_token"] = bool(bot_config_module.resolve_token())
    cfg.pop("webhook_secret", None)  # секрет наружу не отдаём
    return cfg


@router.post("/api/bot")
async def set_bot_config(request: Request):
    """Обновить конфиг бота (услуги, приветствие, поля и т.д.)."""
    data = await request.json()
    return bot_config_module.update(data)
