"""Сообщения между агентами — по тенанту.

Реальный найденный баг (тот же класс, что был у questions.py — см. его
докстринг): раньше это был чистый in-memory dict без единого следа на диске.
send() пишет сообщение в личном LLM-чате пользователя с агентом A (инструмент
send_message), read() агент B читает его при СВОЁМ следующем чате (инструмент
read_messages) — это не в рамках одного HTTP-запроса, а произвольно позже.
Рестарт сервера между send() и read() терял сообщение МОЛЧА: ни в одном json
не оставалось и следа, что оно вообще отправлялось — отправитель думал, что
написал коллеге, получатель никогда не узнавал. persist в agent_inbox.json
закрывает это — та же схема lazy-load/write-through, что в questions.py.
"""

from collections import defaultdict

from src.saas import context as ctx

_FILE = "agent_inbox.json"

_inboxes: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
# tenant_id'ы, для которых персистентный agent_inbox.json уже подгружен в
# память этого процесса — читаем с диска один раз на тенанта, не на вызов.
_loaded: set[str] = set()


def _ensure_loaded(tid: str) -> None:
    if tid in _loaded:
        return
    _loaded.add(tid)
    data = ctx.read_json(_FILE, {})
    for agent_id, msgs in data.items():
        _inboxes[tid][agent_id] = list(msgs)


def _persist(tid: str) -> None:
    # Пустые ящики не пишем — иначе файл растёт мусором из давно прочитанных
    # (и очищенных) адресатов на каждый send()/read() любого агента.
    ctx.write_json(_FILE, {aid: msgs for aid, msgs in _inboxes[tid].items() if msgs})


def send(to_agent_id: str, from_agent_id: str, message: str):
    tid = ctx.get_tenant()
    _ensure_loaded(tid)
    _inboxes[tid][to_agent_id].append({"from": from_agent_id, "text": message})
    _persist(tid)


def read(agent_id: str) -> list[dict]:
    tid = ctx.get_tenant()
    _ensure_loaded(tid)
    box = _inboxes[tid][agent_id]
    msgs = list(box)
    box.clear()
    _persist(tid)
    return msgs
