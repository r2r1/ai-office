"""
Запускает все tests/test_*.py по очереди и печатает сводку.

    python tests/run_all.py

Раньше в CLAUDE.md перед коммитом упоминались только py_compile + tsc —
11 файлов юнит-тестов здесь существовали, но ни разу не были частью
задокументированного чек-листа, и как минимум один из них годами падал бы
на Windows (UnicodeEncodeError на "✓" в консоли cp1251) молча, если бы кто-то
попытался его запустить — а без единого раннера/чек-листа шанс, что кто-то
попытается, невелик.
"""

import subprocess
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="backslashreplace")

TESTS_DIR = Path(__file__).resolve().parent


def main() -> int:
    files = sorted(TESTS_DIR.glob("test_*.py"))
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
