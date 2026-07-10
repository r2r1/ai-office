"""
Игрушечный платформенный MCP-сервер — доказать, что мост (mcp_bridge.py)
реально работает end-to-end как ОТДЕЛЬНЫЙ ПРОЦЕСС за протоколом (Layer 2,
"Как это может работать у тебя" — MCP-сервер вместо Python-модуля в общем
адресном пространстве), прежде чем подключать настоящие платформенные серверы.

Инструменты нарочно бесполезны — только доказывают, что схема/вызов проходят
через MCP-протокол (stdio), а не просто вызывают локальную функцию.

Сервер НЕ запускается вручную — его стартует mcp_bridge.py как дочерний
процесс через stdio_client(StdioServerParameters(command=sys.executable,
args=[этот файл])).
"""

from datetime import datetime, timezone

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("ai-office-toy")


@mcp.tool()
def mcp_ping(text: str) -> str:
    """Эхо-инструмент: возвращает переданный текст с меткой, что запрос прошёл
    через MCP-мост (а не был обработан локальным Python-хендлером)."""
    return f"[toy MCP] получено: {text}"


@mcp.tool()
def mcp_server_time() -> str:
    """Текущее время ЭТОГО процесса (UTC) — маркер изоляции: это отдельный
    процесс, не импорт в адресном пространстве агента."""
    return datetime.now(timezone.utc).isoformat()


if __name__ == "__main__":
    mcp.run()
