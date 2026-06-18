"""Точка входа AI-офиса.

Использование:
  python main.py                      # полная цепочка: ресёрчер → стратег
  python main.py research             # только ресёрчер
  python main.py research "вопрос"    # ресёрчер с кастомным вопросом
  python main.py plan reports/research_XXX.md   # стратег по готовому отчёту
"""

import sys
from pathlib import Path

from src.agents import researcher, strategist


def main():
    args = sys.argv[1:]
    command = args[0] if args else "all"

    if command == "research":
        question = " ".join(args[1:]) if len(args) > 1 else researcher.DEFAULT_QUESTION
        report = researcher.run(question)
        print("\n" + "=" * 60)
        print(report)

    elif command == "plan":
        if len(args) < 2:
            print("Укажи путь к отчёту: python main.py plan reports/research_XXX.md")
            sys.exit(1)
        report = Path(args[1]).read_text(encoding="utf-8")
        plan = strategist.run(report)
        print("\n" + "=" * 60)
        print(plan)

    else:  # "all" — полная цепочка
        print("=== ЭТАП 1: ИССЛЕДОВАНИЕ ===\n")
        report = researcher.run()
        print("\n" + "=" * 60)
        print(report)

        print("\n\n=== ЭТАП 2: СТРАТЕГИЯ ===\n")
        plan = strategist.run(report)
        print("\n" + "=" * 60)
        print(plan)


if __name__ == "__main__":
    main()
