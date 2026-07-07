"""
Обработчики интеграций/способностей (list_integrations/use_integration/
use_capability/use_skill/find_skills) — четвёртый проход декомпозиции
agent_factory.py (docs/audit-dd-2026-07-06.md §19 п.6, см. tool_schemas.py,
file_tool_handlers.py, comms_tool_handlers.py — предыдущие проходы).

`build()` — та же фабрика: принимает (agent_id, role, publish, publish_and_log),
возвращает словарь обработчиков.
"""

import json
from typing import Awaitable, Callable

from src.office import skills as skills_module
from src.office import tool_router
from src.integrations import registry as integrations_registry


def build(agent_id: str, role: str,
          publish: Callable[[dict], Awaitable[None]],
          publish_and_log: Callable[[dict], Awaitable[None]]) -> dict[str, Callable]:

    async def _report_connection_error(platform: str, error: str) -> None:
        """Публикует событие ошибки подключения чтобы пользователь видел в интерфейсе."""
        await publish({"type": "connection_error", "agent_id": agent_id,
                       "platform": platform, "error": error,
                       "text": f"❌ Ошибка подключения к {platform}: {error}"})
        await publish({"type": "speech", "agent_id": agent_id,
                       "text": f"❌ Не могу подключиться к {platform}: {error[:100]}"})

    async def _handle_list_integrations(args: dict) -> str:
        lines = []
        for integ in integrations_registry.all_integrations():
            status = "✅ подключено" if integrations_registry.is_connected(integ) else "⚪ не подключено"
            acts = ", ".join(
                f"{a.name}({', '.join(a.required) or '—'})" for a in integ.actions.values()
            )
            lines.append(f"• {integ.name} [{status}] — {integ.description}\n    действия: {acts}")
        if not lines:
            return "Пока нет доступных интеграций."
        return "Доступные интеграции:\n" + "\n".join(lines)

    async def _execute_integration(name: str, action_name: str, params: dict) -> str:
        """Ядро вызова интеграции — общее для use_integration и use_capability."""
        if isinstance(params, str):
            try:
                params = json.loads(params)
            except json.JSONDecodeError:
                params = {}

        integ = integrations_registry.get(name)
        if not integ:
            avail = ", ".join(i.name for i in integrations_registry.all_integrations()) or "нет"
            return f"Интеграция '{name}' не найдена. Доступные: {avail}."
        action = integ.actions.get(action_name)
        if not action:
            acts = ", ".join(integ.actions.keys())
            return f"У '{integ.name}' нет действия '{action_name}'. Доступные действия: {acts}."

        # Гейт автономии для ВНЕШНЕ-видимых действий: на уровнях ниже требуемого офис
        # не выполняет действие сам, а просит OK клиента. website публикует через свой
        # гейт (loop._publish_site_auto), поэтому его здесь не дублируем.
        if integ.name != "website":
            from src.office import autonomy
            act_type = autonomy._action_type_for(action_name)
            if autonomy.needs_approval(act_type):
                return (f"Действие «{integ.title}.{action_name}» затрагивает внешний мир, а уровень "
                        f"автономии «{autonomy.get_level()}» (только рекомендации) не позволяет офису "
                        f"делать это самостоятельно. НЕ повторяй вызов: сообщи клиенту через ask_user, "
                        f"что рекомендуешь сделать, и предложи повысить уровень автономии в «Компания», "
                        f"если он хочет, чтобы офис выполнял такое сам.")

        creds = integrations_registry.credentials_for(integ)
        if not integrations_registry.is_connected(integ):
            if getattr(integ, "oauth_url", ""):
                return (
                    f"Сервис '{integ.title}' не подключён. НЕ проси API-ключ. "
                    f"Попроси пользователя через ask_user нажать кнопку «Подключить {integ.title}» "
                    f"в разделе «Доступы» (вход по аккаунту, OAuth). После подключения повтори действие."
                )
            return (
                f"Сервис '{integ.title}' ещё не подключён — нет учётных данных. "
                f"Запроси их у пользователя через ask_user. Как получить:\n{integ.how_to}"
            )

        await publish_and_log({"type": "speech", "agent_id": agent_id,
                               "text": f"⚙️ {integ.title}.{action_name}…"})
        try:
            result = await action.handler(creds, params or {})
        except Exception as e:
            err = str(e)[:200]
            await _report_connection_error(integ.title, err)
            return f"Ошибка при вызове {integ.name}.{action_name}: {err}"

        await publish_and_log({"type": "speech", "agent_id": agent_id,
                               "text": f"✅ {integ.title}.{action_name}: {result[:80]}"})
        await publish({"type": "integration_used", "agent_id": agent_id,
                       "integration": integ.name, "action": action_name,
                       "text": f"⚙️ {integ.title}.{action_name} → {result[:120]}"})
        return result

    async def _handle_use_integration(args: dict) -> str:
        return await _execute_integration(
            (args.get("name") or "").strip(),
            (args.get("action") or "").strip(),
            args.get("params") or {},
        )

    async def _handle_use_capability(args: dict) -> str:
        """Tool Router: потребность словами → подбор интеграции+действия → исполнение."""
        need = (args.get("need") or "").strip()
        params = args.get("params") or {}
        if not need:
            return "Опиши потребность словами (например «опубликовать лендинг»)."
        match = tool_router.best(need)
        if match:
            await publish_and_log({"type": "speech", "agent_id": agent_id,
                                   "text": f"🧭 «{need[:50]}» → {match['title']}.{match['action']}"})
            return await _execute_integration(match["integration"], match["action"], params)
        # Неоднозначно или нет совпадений — показываем варианты, пусть агент выберет
        cands = tool_router.route(need, top=3)
        if not cands:
            avail = ", ".join(i.name for i in integrations_registry.all_integrations())
            return (f"Под потребность «{need}» не нашёл готового инструмента. "
                    f"Доступные интеграции: {avail}. Посмотри list_integrations.")
        lines = "\n".join(
            f"- {c['integration']}.{c['action']} ({c['title']}, {'✅' if c['connected'] else '⚪'})"
            for c in cands
        )
        return ("Уточни — под эту потребность подходят несколько инструментов. "
                f"Вызови use_integration с нужным:\n{lines}")

    async def _handle_use_skill(args: dict) -> str:
        """Skills: потребность словами → подбор скилла → его экспертный плейбук."""
        need = (args.get("need") or "").strip()
        if not need:
            return "Опиши потребность словами (например «3D-лендинг с анимациями»)."
        skill = skills_module.match(need, role)
        if skill:
            await publish_and_log({"type": "speech", "agent_id": agent_id,
                                   "text": f"🧩 Беру скилл «{skill.title}»"})
            await publish({"type": "skill_used", "agent_id": agent_id,
                           "skill": skill.id, "text": f"🧩 Скилл «{skill.title}»"})
            if skill.handler:
                return await skill.handler({"need": need})
            return skill.playbook or f"Скилл «{skill.title}»: {skill.description}"
        cands = skills_module.suggestions(need, role, top=3)
        if not cands:
            avail = skills_module.catalog_for(role) or "пока нет подходящих"
            return (f"Под потребность «{need}» готового скилла нет — делай напрямую "
                    f"своими инструментами. Доступные скиллы: {avail}.")
        lines = "\n".join(f"- {s.title}: {s.description}" for s in cands)
        return f"Уточни — подходят несколько скиллов:\n{lines}"

    async def _handle_find_skills(args: dict) -> str:
        """Дискавери каталога скиллов (внутренний find-skills): вернуть СПИСОК
        подходящих способов, чтобы воркер/лидер выбрал и взял через use_skill."""
        query = (args.get("query") or "").strip()
        found = skills_module.search(query, role, top=6)
        if not found:
            return "В каталоге пока нет скиллов, доступных твоей роли — делай напрямую."
        lines = "\n".join(f"• {s.title} — {s.description}" for s in found)
        head = (f"Скиллы под «{query}»:" if query else "Доступные тебе скиллы:")
        return (f"{head}\n{lines}\n\nЧтобы взять нужный — вызови use_skill с "
                f"потребностью словами, получишь его экспертный плейбук.")

    async def _handle_record_metric(args: dict) -> str:
        """Записывает числовое значение метрики бизнеса (BOS §4 Measurement) —
        единственный способ для ЛЮБОГО процесса/скрипта (курс валюты, остатки
        склада, что угодно) появиться на бизнес-дашборде: без этого дашборд
        не может знать про метрику, которую сам не придумывал. Не хардкод —
        расширяемость: metric_id придумывает сам агент (латиницей, снэйк-кейс),
        дашборд подхватит её автоматически при следующем открытии."""
        import re
        metric_id = re.sub(r"[^a-z0-9_]+", "_", (args.get("metric_id") or "").strip().lower()).strip("_")
        if not metric_id:
            return "Укажи metric_id латиницей (например usd_rub_rate)."
        try:
            value = float(args.get("value"))
        except (TypeError, ValueError):
            return "value должно быть числом."
        label = (args.get("label") or metric_id).strip()[:80]
        unit = (args.get("unit") or "").strip()[:20]
        source = args.get("source") if args.get("source") in ("факт", "оценка") else "факт"
        from src.office import metrics as metrics_module
        point = metrics_module.record(metric_id, value, source, label=label, unit=unit)
        await publish({"type": "speech", "agent_id": agent_id,
                       "text": f"📈 Записал метрику «{label}»: {value} {unit} — появится на дашборде"})
        return f"Записано: {point['metric_id']}={point['value']} {unit} ({source})."

    return {
        "list_integrations": _handle_list_integrations,
        "use_integration": _handle_use_integration,
        "use_capability": _handle_use_capability,
        "use_skill": _handle_use_skill,
        "find_skills": _handle_find_skills,
        "record_metric": _handle_record_metric,
    }
