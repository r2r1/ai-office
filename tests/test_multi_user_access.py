"""
Multi-user доступ к тенанту (docs/product-portrait-2026-07-19.md §12) —
implementation-prompt §3.6:
- три раздельно выдаваемых права (visibility/decide/direct), выдаёт ТОЛЬКО
  основатель (saas/members.py);
- store.workspace_for_user() падает на членство, если пользователь не
  владелец ни одного воркспейса (не ломает прежнее поведение владельцев);
- intent.py эскалирует РЕАЛЬНОЕ пересечение директив от разных людей
  основателю (blocker-событие), не тихо теряет и не блокирует запись.

Своя изолированная sqlite БД (не data/app.db — не трогаем боевую/dev базу).

    python tests/test_multi_user_access.py
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="backslashreplace")

os.environ.setdefault("DEMO_MODE", "1")


def main() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        print(("[ok] " if cond else "[FAIL] ") + name)
        if not cond:
            failures.append(name)

    # ---- Изолированная sqlite БД для этого теста (не боевая data/app.db) ----
    from src.saas import db
    tmp_dir = tempfile.mkdtemp(prefix="aio_test_members_")
    db.DB_PATH = __import__("pathlib").Path(tmp_dir) / "test_app.db"
    db.init_db()

    from src.saas import store, members
    import time, uuid

    def _raw_user(email: str) -> dict:
        """Пользователь БЕЗ авто-воркспейса (в обход _ensure_workspace) —
        нужен «чистый» участник, не владеющий ничем своим, чтобы честно
        проверить fallback на членство в workspace_for_user()."""
        uid = f"u_{uuid.uuid4().hex[:12]}"
        db.execute("INSERT INTO users (id, email, name, created_at) VALUES (?,?,?,?)",
                   (uid, email, email.split("@")[0], time.time()))
        return db.query_one("SELECT * FROM users WHERE id=?", (uid,))

    founder = store.get_or_create_dev_user("founder@members.test")
    ws = store.workspace_for_user(founder["id"])
    check("основатель получил свой воркспейс", ws is not None)
    tid = ws["id"]

    colleague = _raw_user("colleague@members.test")
    stranger = _raw_user("stranger@members.test")

    # 1) До выдачи прав — участник вообще не находит тенант
    check("до выдачи прав workspace_for_user(колlega) не находит тенант основателя",
          store.workspace_for_user(colleague["id"]) is None)

    # 2) Не-основатель не может выдавать права (NotFounder)
    threw = False
    try:
        members.grant(tid, stranger["id"], colleague["id"], visibility_domains=["finance"])
    except members.NotFounder:
        threw = True
    check("не-основатель не может выдать права (NotFounder)", threw)

    # 3) Основатель выдаёт права коллеге: видимость finance, решение НЕ выдано,
    #    прямых поручений агентам нет.
    rights = members.grant(tid, colleague["id"], founder["id"],
                           visibility_domains=["finance"], decide_domains=[],
                           can_direct_agents=False)
    check("grant вернул права с visibility_domains=['finance']",
          rights["visibility_domains"] == ["finance"])
    check("decide_domains пуст по умолчанию", rights["decide_domains"] == [])
    check("can_direct_agents=False по умолчанию", rights["can_direct_agents"] is False)

    # 4) После выдачи — workspace_for_user находит тенант ЧЕРЕЗ членство
    ws2 = store.workspace_for_user(colleague["id"])
    check("после grant workspace_for_user(колlega) находит тенант основателя",
          ws2 is not None and ws2["id"] == tid)

    # 4b) Регрессия, найденная живой HTTP-проверкой (не придумана заранее):
    # человек, у которого УЖЕ ЕСТЬ свой авто-созданный воркспейс (обычный вход
    # через get_or_create_dev_user до всякого приглашения), после grant должен
    # попадать в тенант ОСНОВАТЕЛЯ, не в свой пустой — иначе фича физически
    # недостижима обычным логином (см. комментарий в store.workspace_for_user).
    already_owner = store.get_or_create_dev_user("already-has-own-workspace@members.test")
    own_ws = store.workspace_for_user(already_owner["id"])
    check("до grant человек со своим воркспейсом видит именно его",
          own_ws is not None and own_ws["owner_user_id"] == already_owner["id"])
    members.grant(tid, already_owner["id"], founder["id"], visibility_domains=["sales"])
    after_grant_ws = store.workspace_for_user(already_owner["id"])
    check("после grant человек СО СВОИМ воркспейсом видит тенант основателя, не свой",
          after_grant_ws is not None and after_grant_ws["id"] == tid)

    # 5) can_view/can_decide/can_direct — раздельные права, не пакет
    check("может видеть finance", members.can_view(tid, colleague["id"], "finance"))
    check("НЕ может видеть marketing (не выдано)",
          not members.can_view(tid, colleague["id"], "marketing"))
    check("НЕ может решать даже в finance (decide не выдан)",
          not members.can_decide(tid, colleague["id"], "finance"))
    check("НЕ может напрямую поручать агентам", not members.can_direct(tid, colleague["id"]))
    check("основатель видит/решает/поручает всегда, без записи в members",
          members.can_view(tid, founder["id"], "anything")
          and members.can_decide(tid, founder["id"], "anything")
          and members.can_direct(tid, founder["id"]))
    check("посторонний (не участник) не видит ничего",
          not members.can_view(tid, stranger["id"], "finance"))

    # 6) Основатель не может выдать права самому себе
    threw2 = False
    try:
        members.grant(tid, founder["id"], founder["id"], visibility_domains=["*"])
    except ValueError:
        threw2 = True
    check("основатель не может выдать права себе (ValueError)", threw2)

    # 7) revoke — только основатель, и реально убирает доступ
    threw3 = False
    try:
        members.revoke(tid, colleague["id"], stranger["id"])
    except members.NotFounder:
        threw3 = True
    check("не-основатель не может отозвать права (NotFounder)", threw3)
    ok = members.revoke(tid, colleague["id"], founder["id"])
    check("основатель отзывает права", ok)
    check("после revoke колlega больше не видит finance",
          not members.can_view(tid, colleague["id"], "finance"))
    check("после revoke workspace_for_user(колlega) снова не находит тенант",
          store.workspace_for_user(colleague["id"]) is None)

    # ---- intent.py: конфликт директив разных людей эскалируется основателю ----
    from src.saas import context as ctx
    from src.office import intent, events

    def _fresh(name: str) -> None:
        ctx.set_tenant(name)
        ctx.wipe()
        ctx.set_tenant(name)

    _fresh("intent_conflict_test")
    # Эвристика — простое пересечение слов по пробелам (та же, что уже есть в
    # initiatives.has_pending_similar), без нормализации пунктуации — тексты
    # должны быть почти дословно одинаковы, чтобы ratio > 0.5 сработал честно.
    intent.capture("опубликовать лендинг со скидкой 50 процентов для всех клиентов",
                   source="owner")
    before = len(events.pending())
    intent.capture("не публиковать лендинг со скидкой 50 процентов для всех клиентов",
                   source="member:u_colleague")
    after = events.pending()
    check("реальное пересечение директив создало ровно один новый blocker",
          len(after) == before + 1 and after[-1]["kind"] == "blocker")

    _fresh("intent_no_conflict_test")
    intent.capture("публиковать сайт", source="owner")
    before2 = len(events.pending())
    intent.capture("написать план контента на месяц", source="member:u_colleague")
    check("несвязанные директивы НЕ создают blocker",
          len(events.pending()) == before2)

    ctx.wipe()
    print()
    if failures:
        print(f"ПРОВАЛЕНО: {len(failures)}")
        return 1
    print("Все проверки multi-user доступа прошли.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
