"""Точка входа AI-офиса."""

import sys
from src.agents import researcher


def main():
    question = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else researcher.DEFAULT_QUESTION
    report = researcher.run(question)
    print("\n" + "=" * 60)
    print(report)


if __name__ == "__main__":
    main()
