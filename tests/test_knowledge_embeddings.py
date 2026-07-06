"""
Юнит-тесты гибридного (TF + эмбеддинги) ранжирования в knowledge.py
(docs/audit-dd-2026-07-06.md §8/§19 п.11).

⚠️ Баланс аккаунта apinet сейчас ~$0 (проверено вживую 2026-07-06) — реальный
embeddings.embed() возвращает None (insufficient_user_quota). Поэтому:
  - тесты "graceful fallback" вызывают embed() РЕАЛЬНО (без моков) — доказывают,
    что при недоступном провайдере ранжирование не ломается и ведёт себя как раньше;
  - тесты "semantic boost" мокают embeddings.embed()/cosine, чтобы проверить сам
    механизм смешивания сигналов независимо от того, есть ли деньги на счету.

Запуск: python tests/test_knowledge_embeddings.py
"""

import shutil
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.saas import context as ctx
from src.office import knowledge


def _fresh(name: str) -> None:
    ctx.set_tenant(name)
    knowledge.reset()


# ── Graceful fallback: провайдер недоступен (реальный embed(), баланс $0) ───

def test_remember_and_retrieve_work_without_embeddings_provider():
    """embed() реально вызывается и возвращает None (баланс $0) — remember()/
    retrieve() не должны падать и должны вести себя как чистый TF-поиск."""
    _fresh("kn_test_fallback1")
    knowledge.remember("Клиент просил не звонить после 18:00", department="sales")
    facts = knowledge.retrieve("во сколько можно звонить клиенту", department="sales")
    assert any("18:00" in f for f in facts)


def test_stored_fact_has_no_emb_field_when_provider_unavailable():
    _fresh("kn_test_fallback2")
    knowledge.remember("Уникальный тестовый факт про звонки", department="sales")
    raw = knowledge._store()["facts"]
    assert raw and raw[-1]["text"] == "Уникальный тестовый факт про звонки"
    assert "emb" not in raw[-1]  # embed() вернул None → поле не добавлено


# ── Semantic boost: мокаем embed()/cosine, чтобы проверить сам механизм ──────

def test_semantic_similarity_rescues_fact_with_zero_word_overlap():
    """Ключевой сценарий: факт и запрос не имеют ни одного общего слова, но
    семантически близки (по мок-эмбеддингу) — раньше такой факт НЕ находился
    вообще (TF=0 → пропуск), теперь эмбеддинг должен его вытащить."""
    _fresh("kn_test_semantic1")

    # Мок: у "жалоба на дороговизну" и "клиент недоволен ценой" одинаковый вектор
    # (имитирует, что модель эмбеддингов считает их семантически идентичными).
    fake_vectors = {
        "клиент недоволен ценой": [1.0, 0.0, 0.0],
        "жалоба на дороговизну": [1.0, 0.0, 0.0],
    }

    def fake_embed(text, agent_id="knowledge_embeddings"):
        return fake_vectors.get(text.strip().lower())

    with patch("src.core.embeddings.embed", side_effect=fake_embed):
        knowledge.remember("клиент недоволен ценой", department="sales")
        facts = knowledge.retrieve("жалоба на дороговизну", department="sales")
    assert any("недоволен ценой" in f for f in facts), (
        "факт без единого общего слова с запросом должен найтись через эмбеддинг")


def test_semantic_similarity_below_threshold_does_not_rescue():
    """Низкая косинусная близость НЕ должна вытаскивать нерелевантный факт —
    иначе гибридный скор превратился бы в «показывай всё подряд»."""
    _fresh("kn_test_semantic2")

    def fake_embed(text, agent_id="knowledge_embeddings"):
        # Слабо похожие векторы (косинус ~0.1, ниже порога _SEM_MIN=0.35)
        if "рецепт борща" in text.lower():
            return [1.0, 0.1, 0.0]
        return [0.1, 1.0, 0.0]

    with patch("src.core.embeddings.embed", side_effect=fake_embed):
        knowledge.remember("рецепт борща с уткой", department="marketer")
        facts = knowledge.retrieve("настройка рекламного кабинета", department="marketer")
    assert not any("борщ" in f for f in facts)


def test_tf_overlap_still_works_with_embeddings_enabled():
    """Обычное словесное совпадение по-прежнему находит факт — гибрид не должен
    сломать базовый TF-путь, когда эмбеддинги просто не участвуют (нет общих слов
    для семантики, но есть точное текстовое совпадение)."""
    _fresh("kn_test_tf_still_works")

    def fake_embed(text, agent_id="knowledge_embeddings"):
        return [0.0, 0.0, 1.0]  # одинаковый нейтральный вектор — не даёт буста

    with patch("src.core.embeddings.embed", side_effect=fake_embed):
        knowledge.remember("Интеграция с Bitrix24 настроена вручную", department="developer")
        facts = knowledge.retrieve("как настроена интеграция с Bitrix24", department="developer")
    assert any("Bitrix24" in f for f in facts)


def _cleanup_test_tenants() -> None:
    """data/tenants/kn_test_* — реальные файлы на диске, не только in-memory
    (data/ в .gitignore, но диск разработчика захламляется с каждым прогоном)."""
    for d in ctx.ROOT.glob("kn_test_*"):
        if d.is_dir():
            shutil.rmtree(d, ignore_errors=True)


def _run():
    passed = 0
    try:
        for name, fn in sorted(globals().items()):
            if name.startswith("test_") and callable(fn):
                fn()
                print(f"  ✓ {name}")
                passed += 1
    finally:
        _cleanup_test_tenants()
    print(f"ВСЕ {passed} ТЕСТОВ ПРОШЛИ")


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    _run()
