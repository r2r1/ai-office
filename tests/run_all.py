"""
Запускает все tests/test_*.py по очереди и печатает сводку.

    python tests/run_all.py

Раньше в CLAUDE.md перед коммитом упоминались только py_compile + tsc —
11 файлов юнит-тестов здесь существовали, но ни разу не были частью
задокументированного чек-листа, и как минимум один из них годами падал бы
на Windows (UnicodeEncodeError на "✓" в консоли cp1251) молча, если бы кто-то
попытался его запустить — а без единого раннера/чек-листа шанс, что кто-то
попытается, невелик.

RUN_ALL_SKIP — необязательный env var с именами файлов через запятую, которые
пропускаются (не запускаются вовсе, не считаются ни успехом, ни провалом).
Нужен CI (.github/workflows/tests.yml): test_exec_sandbox.py требует Docker-
демон, test_knowledge_embeddings.py и test_mcp_tenant_servers.py требуют
реальный LLM-ключ/сеть — окружение CI-раннера этого не даёт по конструкции,
это не регрессия кода. Локально (где Docker/сеть есть) переменная не задаётся,
и раннер по-прежнему прогоняет и репортит все файлы как раньше.
"""

import os
import subprocess
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="backslashreplace")

TESTS_DIR = Path(__file__).resolve().parent


def main() -> int:
    skip = {s.strip() for s in os.environ.get("RUN_ALL_SKIP", "").split(",") if s.strip()}
    files = [f for f in sorted(TESTS_DIR.glob("test_*.py")) if f.name not in skip]
    if skip:
        print(f"Пропущено (RUN_ALL_SKIP): {', '.join(sorted(skip))}\n")
    failed = []
    for f in files:
        print(f"=== {f.name} ===")
        res = subprocess.run([sys.executable, str(f)], capture_output=True,
                             text=True, encoding="utf-8", errors="replace")
        print(res.stdout.strip())
        if res.returncode != 0:
            print(res.stderr.strip())
            failed.append(f.name)
        print()
    print("=" * 60)
    if failed:
        print(f"ПРОВАЛЕНО файлов: {len(failed)} — {', '.join(failed)}")
        return 1
    print(f"Все {len(files)} тестовых файлов прошли.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
