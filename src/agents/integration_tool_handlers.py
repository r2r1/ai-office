"""
Обработчики интеграций/способностей (list_integrations/use_integration/
use_capability/use_skill/find_skills) — четвёртый проход декомпозиции
agent_factory.py (docs/audit-dd-2026-07-06.md §19 п.6, см. tool_schemas.py,
file_tool_handlers.py, comms_tool_handlers.py — предыдущие проходы).

`build()` — та же фабрика: принимает (agent_id, role, publish, publish_and_log),
возвращает словарь обработчиков.
"""

import json
import sys
from pathlib import Path
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

        # Department-скоуп (BOS: модуль соответствует своему отделу): способность
        # без department (по умолчанию, "") — общий доступ, прежнее поведение
        # (инвариант "общие доступы" из CLAUDE.md не тронут). Способность С
        # department — только своя роль или portfolio-роль (CEO/лидер/штаб,
        # у них и так обзор всего бизнеса); иначе, например, salesman мог бы
        # дёрнуть 1С просто потому что ключ технически доступен всем.
        if integ.department:
            from src.office import org as org_module
            role_dept = org_module.department_of_role(role)
            if role_dept != integ.department and not org_module.is_portfolio_role(role):
                dept_name = org_module.catalog().get(integ.department, {}).get("name", integ.department)
                return (f"«{integ.title}» закреплена за отделом «{dept_name}» — твоя роль к нему не "
                        f"относится. Поставь задачу через delegate_task нужной роли этого отдела "
                        f"или попроси лидера («{org_module.lead_title(integ.department)}») выполнить это.")

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

    async def _handle_discover_resource(args: dict) -> str:
        """Discovery-слой (office/discovery.py): голая ссылка → что это и как
        с этим работать. Не выполняет действие сама — только классифицирует и
        рекомендует следующий шаг (существующая интеграция / register_external_api)."""
        url = (args.get("url") or "").strip()
        if not url:
            return "Укажи url."
        from src.office import discovery
        classification = await discovery.probe(url)
        rec = discovery.recommend(classification)
        await publish_and_log({"type": "speech", "agent_id": agent_id,
                               "text": f"🔎 {url} → {classification['kind']}"})
        return f"Тип ресурса: {classification['kind']}.\n{rec}"

    async def _handle_register_external_api(args: dict) -> str:
        """Подключает обобщённый REST/OpenAPI MCP-мост под конкретный URL —
        реализация Layer 4 "connect_external_resource": не пишет новый код,
        конфигурирует уже существующий обобщённый шаблон
        (mcp_generic_rest_server.py) через тенантский MCP-реестр, который сам
        требует готовую Docker-песочницу (mcp_tenant_servers.add)."""
        url = (args.get("url") or "").strip().rstrip("/")
        label = (args.get("label") or "").strip()
        if not url or not label:
            return "Укажи url и label (короткое имя сервиса)."
        auth_header = (args.get("auth_header") or "").strip()
        auth_value = (args.get("auth_value") or "").strip()
        env = {"BASE_URL": url}
        if auth_header and auth_value:
            env["AUTH_HEADER"] = auth_header
            env["AUTH_VALUE"] = auth_value
        from src.office import mcp_tenant_servers, exec_sandbox
        try:
            item = mcp_tenant_servers.add(
                label, sys.executable,
                [str(Path(__file__).resolve().parents[1] / "office" / "mcp_generic_rest_server.py")],
                env=env, allow_network=True,
            )
        except exec_sandbox.SandboxUnavailable as e:
            return f"Не удалось подключить «{label}»: {e}"
        await publish_and_log({"type": "speech", "agent_id": agent_id,
                               "text": f"🔌 Подключил «{label}» как MCP-инструмент ({url})"})
        return (f"«{label}» подключён (id {item['id']}). Инструменты появятся у тебя со следующей "
                f"задачи с префиксом mcp__tenant_{item['id']}__ — list_endpoints/call_endpoint.")

    async def _handle_register_mcp_server(args: dict) -> str:
        """Подключает РОДНОЙ MCP-сервер стороннего сервиса как есть (npx-пакет
        и т.п.) — в отличие от register_external_api (который всегда поднимает
        НАШ обобщённый REST-мост поверх голого API), команда/аргументы здесь
        произвольные, задаются моделью. Тот же тенантский реестр и то же
        требование Docker-песочницы, что у register_external_api — просто без
        хардкода command на mcp_generic_rest_server.py."""
        label = (args.get("label") or "").strip()
        command = (args.get("command") or "").strip()
        if not label or not command:
            return "Укажи label и command."
        raw_args = args.get("args") or []
        if not isinstance(raw_args, list):
            return "args должен быть списком строк."
        raw_env = args.get("env") or {}
        if not isinstance(raw_env, dict):
            return "env должен быть объектом строка→строка."
        from src.office import mcp_tenant_servers, exec_sandbox
        try:
            item = mcp_tenant_servers.add(
                label, command, [str(a) for a in raw_args],
                env={str(k): str(v) for k, v in raw_env.items()},
                allow_network=bool(args.get("allow_network", False)),
            )
        except exec_sandbox.SandboxUnavailable as e:
            return f"Не удалось подключить «{label}»: {e}"
        await publish_and_log({"type": "speech", "agent_id": agent_id,
                               "text": f"🔌 Подключил родной MCP-сервер «{label}»"})
        return (f"«{label}» подключён (id {item['id']}). Инструменты появятся у тебя со следующей "
                f"задачи с префиксом mcp__tenant_{item['id']}__ .")

    async def _handle_find_mcp_connectors(args: dict) -> str:
        """Каталог готовых рецептов подключения известных open-source MCP-сервисов
        (office/mcp_connectors.py) — чтобы агент не изобретал command/args сам для
        сервисов, под которые уже есть проверенный рецепт (напр. Postiz)."""
        from src.office import mcp_connectors
        query = (args.get("query") or "").strip()
        items = mcp_connectors.match(query) if query else mcp_connectors.all_connectors()
        if not items:
            return "В каталоге нет подходящего рецепта — подключи через register_mcp_server вручную."
        lines = []
        for c in items:
            needs_txt = ", ".join(n["key"] for n in c.needs) or "—"
            lines.append(f"- {c.id}: {c.title} (нужны значения: {needs_txt})")
        return "Готовые рецепты:\n" + "\n".join(lines)

    async def _handle_connect_mcp_connector(args: dict) -> str:
        """Подключает сервис из каталога по id — command/args берутся из рецепта,
        агент передаёт только собранные значения needs (через ask_user, не выдумывает)."""
        from src.office import mcp_connectors
        connector_id = (args.get("connector_id") or "").strip()
        values = args.get("values") or {}
        if not connector_id:
            return "Укажи connector_id (см. find_mcp_connectors)."
        if not isinstance(values, dict):
            return "values должен быть объектом строка→строка."
        c = mcp_connectors.get(connector_id)
        if not c:
            return f"В каталоге нет рецепта «{connector_id}» — проверь find_mcp_connectors или используй register_mcp_server."
        resolved_args, missing = c.resolve({str(k): str(v) for k, v in values.items()})
        if missing:
            return f"Не хватает значений: {', '.join(missing)}. Получи их у пользователя через ask_user."
        from src.office import mcp_tenant_servers, exec_sandbox
        try:
            item = mcp_tenant_servers.add(
                c.title, c.command, resolved_args, env={}, allow_network=c.allow_network,
            )
        except exec_sandbox.SandboxUnavailable as e:
            return f"Не удалось подключить «{c.title}»: {e}"
        await publish_and_log({"type": "speech", "agent_id": agent_id,
                               "text": f"🔌 Подключил «{c.title}» по готовому рецепту"})
        return (f"«{c.title}» подключён (id {item['id']}). Инструменты появятся у тебя со следующей "
                f"задачи с префиксом mcp__tenant_{item['id']}__ .")

    return {
        "list_integrations": _handle_list_integrations,
        "use_integration": _handle_use_integration,
        "use_capability": _handle_use_capability,
        "use_skill": _handle_use_skill,
        "find_skills": _handle_find_skills,
        "record_metric": _handle_record_metric,
        "discover_resource": _handle_discover_resource,
        "register_external_api": _handle_register_external_api,
        "register_mcp_server": _handle_register_mcp_server,
        "find_mcp_connectors": _handle_find_mcp_connectors,
        "connect_mcp_connector": _handle_connect_mcp_connector,
    }
