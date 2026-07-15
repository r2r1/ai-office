"""
Обработчик analyze_image — единственное место, где агент реально «смотрит» на
картинку (vision-модель), а не только читает текстовую структуру Figma
(figma.get_file). Отдельный модуль по образцу file_tool_handlers.py/
comms_tool_handlers.py (декомпозиция agent_factory.py, см. её докстринг).

Роль-гейт (кто получает этот инструмент) держится в agent_factory.py рядом с
остальными role-based гейтами (ask_user/ask_leader, portfolio) — не здесь.
"""

from typing import Awaitable, Callable

from src.core import llm


def build(agent_id: str, role: str,
          publish: Callable[[dict], Awaitable[None]],
          publish_and_log: Callable[[dict], Awaitable[None]]) -> dict[str, Callable]:

    async def _handle_analyze_image(args: dict) -> str:
        image_url = (args.get("image_url") or "").strip()
        question = (args.get("question") or "").strip()
        res = await llm.describe_image(image_url, question, agent_id=agent_id)
        await publish_and_log({"type": "speech", "agent_id": agent_id, "text": f"🖼 {res[:200]}"})
        return res

    return {"analyze_image": _handle_analyze_image}
