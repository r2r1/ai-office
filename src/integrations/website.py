"""
Интеграция «Сайт/Лендинг» — публикация реальной посадочной страницы.

В отличие от остальных интеграций НЕ требует учётных данных: страницу хостит
сам бэкенд (/site/{slug}), а форма собирает живых лидов (POST /api/lead/{slug}).
Это даёт предпринимателю осязаемый результат сразу — ссылку, которую можно
разослать, и базу реальных заявок (а не выдуманных агентом).
"""

from src.integrations.base import Action, Integration
from src.office import sites, leads, autonomy
from src.saas import context as ctx


def _publish_needs_approval() -> bool:
    """
    Публикация — внешне видимое действие: на уровнях автономии ниже автопубликации
    её решает клиент. Один гейт для ВСЕХ путей: и центральной авто-публикации офиса
    (loop._publish_site_auto), и прямого вызова агентом (эта интеграция). Иначе агент
    публиковал сайт сам, в обход разрешения, а офис потом спрашивал и публиковал повторно.
    """
    return autonomy.needs_approval("publish_site")


_AWAIT_APPROVAL_MSG = (
    "Публиковать НЕ нужно и сейчас нельзя: публикация требует разрешения клиента. "
    "Просто оставь готовые файлы в папке site/ — офис сам спросит клиента и опубликует "
    "после его «да». Задача считается выполненной, когда файлы записаны."
)


def _esc(s: str) -> str:
    return (str(s or "")
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def _render_html(lead_url: str, title: str, headline: str, sub: str,
                 bullets: list[str], cta: str, accent: str) -> str:
    accent = accent if (accent or "").startswith("#") else "#4f7cff"
    bl = "".join(f'<li>{_esc(b)}</li>' for b in bullets if b)
    bullets_block = f'<ul class="benefits">{bl}</ul>' if bl else ""
    return f"""<!doctype html>
<html lang="ru"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(title)}</title>
<style>
 :root {{ --accent: {accent}; }}
 * {{ box-sizing: border-box; }}
 body {{ margin:0; font-family: 'Inter', system-ui, Arial, sans-serif; color:#1a1a2e; background:#f5f6fb; }}
 .hero {{ background: linear-gradient(135deg, var(--accent), #1a1a3a); color:#fff; padding:72px 20px 64px; text-align:center; }}
 .hero h1 {{ font-size:38px; margin:0 0 14px; line-height:1.15; }}
 .hero p {{ font-size:18px; opacity:.92; max-width:640px; margin:0 auto; }}
 .wrap {{ max-width:680px; margin:-40px auto 40px; background:#fff; border-radius:16px;
          box-shadow:0 18px 50px rgba(20,20,60,.12); padding:32px; }}
 .benefits {{ list-style:none; padding:0; margin:0 0 28px; }}
 .benefits li {{ padding:12px 0 12px 34px; position:relative; font-size:16px; border-bottom:1px solid #eef0f7; }}
 .benefits li:before {{ content:"✓"; position:absolute; left:0; color:var(--accent); font-weight:bold; }}
 form {{ display:flex; flex-direction:column; gap:12px; }}
 input, textarea {{ padding:13px 14px; border:1px solid #d8dcea; border-radius:10px; font-size:15px; font-family:inherit; }}
 input:focus, textarea:focus {{ outline:none; border-color:var(--accent); }}
 button {{ background:var(--accent); color:#fff; border:none; border-radius:10px; padding:15px; font-size:16px;
           font-weight:600; cursor:pointer; }}
 button:disabled {{ opacity:.6; cursor:default; }}
 .ok {{ text-align:center; padding:24px; font-size:17px; color:#1a7a4a; }}
 .foot {{ text-align:center; color:#9aa; font-size:12px; padding:18px; }}
</style></head>
<body>
 <div class="hero">
   <h1>{_esc(headline)}</h1>
   {f'<p>{_esc(sub)}</p>' if sub else ''}
 </div>
 <div class="wrap">
   {bullets_block}
   <form id="lead-form">
     <input name="name" placeholder="Ваше имя" required>
     <input name="contact" placeholder="Телефон или email" required>
     <textarea name="message" placeholder="Комментарий (необязательно)" rows="3"></textarea>
     <button type="submit">{_esc(cta)}</button>
   </form>
   <div class="ok" id="ok" style="display:none">Спасибо! Мы свяжемся с вами в ближайшее время.</div>
 </div>
 <div class="foot">Сделано автономным AI-офисом</div>
<script>
 const f = document.getElementById('lead-form');
 f.addEventListener('submit', async (e) => {{
   e.preventDefault();
   const btn = f.querySelector('button'); btn.disabled = true;
   const data = {{ name: f.name.value, contact: f.contact.value, message: f.message.value }};
   try {{
     const r = await fetch('{lead_url}', {{ method:'POST',
       headers:{{'Content-Type':'application/json'}}, body: JSON.stringify(data) }});
     if (r.ok) {{ f.style.display='none'; document.getElementById('ok').style.display='block'; }}
     else {{ btn.disabled = false; alert('Не удалось отправить, попробуйте ещё раз'); }}
   }} catch {{ btn.disabled = false; alert('Ошибка сети'); }}
 }});
</script>
</body></html>"""


async def _publish_landing(creds: dict, params: dict) -> str:
    title = (params.get("title") or "").strip()
    headline = (params.get("headline") or title or "").strip()
    if not headline:
        return "Нужен хотя бы headline или title для лендинга."
    if _publish_needs_approval():
        return _AWAIT_APPROVAL_MSG
    sub = (params.get("subheadline") or "").strip()
    bullets = params.get("bullets") or []
    if isinstance(bullets, str):
        bullets = [b.strip() for b in bullets.split("\n") if b.strip()]
    cta = (params.get("cta_text") or "Оставить заявку").strip()
    accent = (params.get("accent_color") or "").strip()

    tid = ctx.get_tenant()
    slug = sites.make_slug(title or headline)
    lead_url = f"/api/lead/{tid}/{slug}"
    html = _render_html(lead_url, title or headline, headline, sub, bullets, cta, accent)
    site = sites.save(title or headline, html, slug)
    return (f"Лендинг опубликован: /site/{tid}/{site['slug']} "
            f"(заголовок «{site['title']}»). Форма уже собирает заявки в раздел «Лиды». "
            f"Разошли ссылку аудитории.")


async def _publish_site(creds: dict, params: dict) -> str:
    """Публикует МНОГОСТРАНИЧНЫЙ сайт из папки рабочей директории (живой хостинг)."""
    from src.office import workspace
    if _publish_needs_approval():
        return _AWAIT_APPROVAL_MSG
    directory = (params.get("directory") or "").strip().strip("/")
    title = (params.get("title") or "").strip()
    idx_rel = f"{directory}/index.html" if directory else "index.html"
    idx = workspace.resolve(idx_rel)
    # Авто-детект: агент часто зовёт publish_site без directory (или с неверной) —
    # вместо бессмысленной ошибки находим index.html там, где он реально лежит.
    if idx is None or not idx.is_file():
        for cand in ("site", "", "public", "dist", "www", "build"):
            cand_rel = f"{cand}/index.html" if cand else "index.html"
            ci = workspace.resolve(cand_rel)
            if ci is not None and ci.is_file():
                directory, idx, idx_rel = cand, ci, cand_rel
                break
    if idx is None or not idx.is_file():
        for f in workspace.list_files():  # последний шанс — любой */index.html
            if f["path"].endswith("index.html"):
                idx_rel = f["path"]
                directory = idx_rel.rsplit("/", 1)[0] if "/" in idx_rel else ""
                idx = workspace.resolve(idx_rel)
                break
    if idx is None or not idx.is_file():
        return ("Не найден index.html. Сначала напиши через write_file сайт в папке site/: "
                "index.html (главная) + css/style.css, js/script.js, при необходимости другие "
                "страницы. Публиковать не обязательно — офис опубликует папку site/ сам.")
    files = workspace.list_dir(directory)
    tid = ctx.get_tenant()
    # Стабильный адрес ТЕКУЩЕГО проекта (Фаза 3, параллельные проекты — свой слаг
    # на проект, не общий на тенанта). ПУБЛИКУЕТ офис централизованно
    # (loop._publish_site_auto после задач и на завершении). Если сайт уже живой —
    # агент НЕ переиздаёт его (иначе счётчик правок рос бы от каждого вызова агента,
    # дублируя авто-публикацию офиса). Просто подтверждаем, что сайт актуален.
    slug = sites.slug_for_current_project()
    if sites.get(slug):
        return (f"🌐 Сайт уже опубликован и живой: /site/{tid}/{slug}. Офис сам держит его "
                f"в актуальном состоянии при изменении файлов — повторно публиковать не нужно. "
                f"Форма с POST на /api/site-lead собирает заявки в «Лиды».")
    site = sites.save_dir(title or "Сайт", directory, slug)  # первая публикация
    return (f"🌐 Сайт опубликован: /site/{tid}/{site['slug']} "
            f"(файлов: {len(files)}). Постоянный адрес; дальше офис обновляет его сам. "
            f"Форма с POST на /api/site-lead собирает заявки в «Лиды».")


async def _list_pages(creds: dict, params: dict) -> str:
    items = sites.all_sites()
    if not items:
        return "Пока не опубликовано ни одного лендинга."
    tid = ctx.get_tenant()
    lines = []
    for s in items:
        n = len(leads.for_site(s["slug"]))
        lines.append(f"- /site/{tid}/{s['slug']} — «{s['title']}» (заявок: {n})")
    return "Опубликованные лендинги:\n" + "\n".join(lines)


INTEGRATION = Integration(
    name="website",
    title="Сайт / Лендинг",
    category="publishing",
    icon="🌐",
    description="Публикация посадочной страницы с формой захвата лидов. Хостинг и сбор заявок — встроенные, ключи не нужны.",
    how_to="Учётные данные не нужны — страница публикуется и хостится самим офисом. "
           "Просто поручи агенту создать лендинг под оффер клиента.",
    cred_fields=[],  # без кредов — всегда доступна
    actions={
        "publish_site": Action(
            name="publish_site",
            description="Опубликовать ПОЛНОЦЕННЫЙ многостраничный сайт из папки рабочей директории "
                        "(index.html + другие страницы, css, js, картинки). Хостинг живой — сайт "
                        "обновляется при изменении файлов. Используй для настоящих сайтов, не лендингов-заглушек.",
            handler=_publish_site,
            params={
                "directory": {"type": "string", "description": "Папка сайта в рабочей директории "
                              "(например 'site' или '' для корня). Должна содержать index.html."},
                "title": {"type": "string", "description": "Название сайта (определяет адрес)"},
            },
            required=[],
            synonyms=["сайт", "лендинг", "landing", "страниц", "опубликова"],
        ),
        "list_pages": Action(
            name="list_pages",
            description="Показать опубликованные лендинги и число собранных заявок.",
            handler=_list_pages,
        ),
    },
)
