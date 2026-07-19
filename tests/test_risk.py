"""
Риск как обучаемый Fact (docs/product-portrait-2026-07-19.md §5a/§13/§16 п.1):
- офис оценивает риск сам, постфактум — стартовая гипотеза inferred, после
  реального провала эскалирует и становится outcome с растущим confidence;
- autonomy.needs_approval() подмешивает эскалацию поверх статической таблицы
  (не заменяет её — trusted/autonomous всё равно требуют подтверждения, если
  риск обучением поднят);
- серьёзный провал (base level "high" — publish_site/push_code) откатывает
  уровень автономии автоматически, симметрично autonomy.upgrade().

    python tests/test_risk.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="backslashreplace")

os.environ.setdefault("DEMO_MODE", "1")

from src.saas import context as ctx


def _fresh(name: str) -> None:
    ctx.set_tenant(name)
    ctx.wipe()
    ctx.set_tenant(name)


def main() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        print(("[ok] " if cond else "[FAIL] ") + name)
        if not cond:
            failures.append(name)

    _fresh("risk_test")
    from src.office import risk, autonomy

    # 1) Без провалов — inferred-гипотеза, низкий confidence
    r = risk.level_for("send_message")
    check("send_message без истории — inferred, confidence 0.3",
          r["source"] == "inferred" and r["confidence"] == 0.3 and r["level"] == "medium")
    check("без провалов risk.escalated() ложно", not risk.escalated("send_message"))

    # 2) Реальный провал эскалирует риск на ступень, source=outcome
    risk.record_outcome("send_message", ok=False, note="письмо не доставлено")
    r2 = risk.level_for("send_message")
    check("после провала — source=outcome", r2["source"] == "outcome")
    check("после провала — эскалация на ступень (medium→high)", r2["level"] == "high")
    check("risk.escalated() истинно после провала", risk.escalated("send_message"))

    # 3) needs_approval требует подтверждения ДАЖЕ на autonomous + разовом одобрении,
    #    когда обучение подняло риск — сравниваем с состоянием ДО провала на чистом
    #    тенанте, чтобы не спутать эффект риска с эффектом самого autonomous-уровня.
    _fresh("risk_test_gate")
    from src.office import risk as risk3, autonomy as autonomy4
    autonomy4.set_level("autonomous")
    autonomy4.mark_action_approved("send_message")
    check("ДО провала: autonomous+approved_once ⇒ needs_approval=False",
          not autonomy4.needs_approval("send_message"))
    risk3.record_outcome("send_message", ok=False, note="письмо не доставлено")
    check("ПОСЛЕ провала: needs_approval=True даже на autonomous+approved_once",
          autonomy4.needs_approval("send_message"))

    # 4) Действие без реального провала не эскалирует — обычная таблица решает как раньше
    #    (create_repo требует "guided", autonomous выше порога — разрешено без обучения).
    check("необучавшееся действие (create_repo) на autonomous — needs_approval=False",
          not autonomy4.needs_approval("create_repo"))

    # 5) Серьёзный провал (base=high) откатывает автономию автоматически
    _fresh("risk_test_severe")
    from src.office import risk as risk2, autonomy as autonomy2
    autonomy2.set_level("autonomous")
    check("severe_failure ложно до провала", not risk2.severe_failure("publish_site"))
    risk2.record_outcome("publish_site", ok=False, note="сайт лёг после публикации")
    check("severe_failure истинно после провала publish_site (base=high)",
          risk2.severe_failure("publish_site"))
    new_level = autonomy2.downgrade(reason="test")
    check("downgrade() снижает уровень с autonomous до trusted",
          new_level == "trusted" and autonomy2.get_level() == "trusted")

    # 6) downgrade() на минимальном уровне (scout) не падает, остаётся scout
    _fresh("risk_test_floor")
    from src.office import autonomy as autonomy3
    autonomy3.set_level("scout")
    floor = autonomy3.downgrade()
    check("downgrade() на scout остаётся scout (нет провала ниже пола)",
          floor == "scout" and autonomy3.get_level() == "scout")

    ctx.wipe()
    print()
    if failures:
        print(f"ПРОВАЛЕНО: {len(failures)}")
        return 1
    print("Все проверки риска-как-Fact прошли.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
