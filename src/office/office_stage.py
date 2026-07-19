"""
Office Stage — визуальный рост офиса как чистая проекция уже существующих чисел
(docs/product-portrait-2026-07-19.md §10): офис физически растёт вместе с
доверием/автономией/командой, БЕЗ единого нового источника истины — тот же
приём, что `world.py` уже использует для business_state в целом (CQRS-закон:
читающий модуль, не хранилище).

  stage()  — {level, label, rooms, team_size, trust_score, autonomy_level} —
             READ-ONLY проекция из trust.get_score()/autonomy.get_level()/
             org.open_departments()/registry.all_agents(). Ничего не пишет,
             ничего не хранит — вызывать можно на каждый рендер без побочных
             эффектов, как и любой другой срез world.snapshot().

Единственное легитимное новое состояние во всей механике игрового слоя —
маленький дедуп-маркер «эта Capability уже праздновалась» (портрет §10,
«разблокировка не переигрывается») — сюда НЕ входит: office_stage сам
остаётся чистой функцией, дедуп-маркер (если/когда понадобится) должен жить
в отдельном крошечном модуле рядом, не смешиваться с этой проекцией.
"""

from src.office import trust, autonomy, org, registry

_AUTONOMY_IDX = {"scout": 0, "guided": 1, "trusted": 2, "autonomous": 3}

_STAGE_LABELS = {
    0: "Один стол",
    1: "Комната",
    2: "Небольшой офис",
    3: "Этаж",
    4: "Полноценное здание",
}

# Порог доверия, после которого интерьер той же структурной стадии считается
# "дозревшим" (переход 3→4) — произвольная, но детерминированная граница;
# при необходимости синхронизировать с trust._UPGRADE_THRESHOLD в будущем.
_TRUST_MATURE = 50


def stage() -> dict:
    """Текущая визуальная стадия офиса. Пороги (портрет §10): размер команды и
    число открытых отделов двигают стадию по СТРУКТУРЕ (появляются комнаты),
    доверие/автономия — по "качеству" интерьера на уже достигнутой структуре."""
    team_size = len(registry.all_agents())
    depts = org.open_departments()
    trust_score = trust.get_score()
    autonomy_level = autonomy.get_level()
    autonomy_idx = _AUTONOMY_IDX.get(autonomy_level, 0)

    if team_size == 0:
        level = 0
    elif len(depts) == 0:
        level = 1
    elif len(depts) < 2:
        level = 2
    elif autonomy_idx >= 2 or trust_score >= _TRUST_MATURE:
        level = 4
    else:
        level = 3

    return {
        "level": level,
        "label": _STAGE_LABELS.get(level, _STAGE_LABELS[0]),
        # Реальные открытые отделы — UI решает, какие комнаты показать/скрыть
        # (портрет §10: «открытие нового отдела — уже реальное событие в
        # org.py — естественный повод для появления новой комнаты»).
        "rooms": depts,
        "team_size": team_size,
        "trust_score": trust_score,
        "autonomy_level": autonomy_level,
    }
