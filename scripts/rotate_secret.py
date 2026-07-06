"""
Ротация APP_SECRET: перешифровывает все зашифрованные значения (connections.json,
llm_settings.json) всех тенантов со СТАРОГО ключа на НОВЫЙ, заданный в APP_SECRET.

Использование:
    1. Задайте НОВЫЙ APP_SECRET в .env, старое значение — в APP_SECRET_PREVIOUS
       (crypto.decrypt тем временем читает и то, и другое, см. src/saas/crypto.py).
    2. Сначала DRY-RUN (по умолчанию, ничего не пишет):
           python scripts/rotate_secret.py
       Проверьте вывод — сколько значений расшифровалось успешно, сколько
       НЕ расшифровалось (см. предупреждение ниже).
    3. Только когда уверены — реальный прогон с записью:
           python scripts/rotate_secret.py --apply
    4. Уберите APP_SECRET_PREVIOUS из .env — миграция завершена.

⚠️ ПРЕДОХРАНИТЕЛЬ (добавлен после реального инцидента потери креда при тесте
этого скрипта на боевых данных, см. git-историю): если значение НЕ расшифровывается
НИ текущим APP_SECRET, НИ ключами из APP_SECRET_PREVIOUS, скрипт НЕ перезаписывает
его пустой строкой — оставляет как есть и печатает предупреждение с
tenant/полем. Раньше decrypt() при неудаче тихо возвращал "", и скрипт эту
пустую строку заново шифровал и сохранял — необратимо стирая реальный
креденшл, если секреты в .env были указаны неверно. Перед записью каждый
файл дополнительно копируется в `<file>.bak-<unix_ts>` рядом — на случай,
если сам факт перешифровки окажется ошибкой.
"""

import sys
import time
from pathlib import Path

# Windows-консоль часто в cp1251 — эмодзи в предупреждениях ронял скрипт
# исключением UnicodeEncodeError прямо на моменте вывода критичного
# предупреждения (обнаружено тестом этого же скрипта). reconfigure делает
# stdout/stderr терпимыми к любым символам вместо падения.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="backslashreplace")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.saas import context as ctx
from src.saas import crypto

APPLY = "--apply" in sys.argv


def _backup(path: Path) -> None:
    if path.exists():
        path.with_name(f"{path.name}.bak-{int(time.time())}").write_bytes(path.read_bytes())


def _rotate_connections(tenant_dir: Path) -> tuple[int, int]:
    """Возвращает (перешифровано, пропущено_с_ошибкой)."""
    ctx.set_tenant(tenant_dir.name)
    conns = ctx.read_json("connections.json", [])
    if not conns:
        return 0, 0
    n = skipped = 0
    for c in conns:
        fields = c.get("fields") or {}
        new_fields = {}
        for k, v in fields.items():
            if not v:
                new_fields[k] = v
                continue
            plain = crypto.decrypt(v)
            if not plain:
                # Расшифровка не удалась НИ одним из ключей (текущим/previous) —
                # НЕ затираем значение пустотой, оставляем оригинал как есть.
                print(f"  ⚠ {tenant_dir.name}: connections[{c.get('name')}].{k} "
                      f"НЕ расшифровалось ни APP_SECRET, ни APP_SECRET_PREVIOUS — "
                      f"оставлено без изменений (проверьте секреты!)")
                new_fields[k] = v
                skipped += 1
                continue
            new_fields[k] = crypto.encrypt(plain)
            if new_fields[k] != v:
                n += 1
        c["fields"] = new_fields
    if n and APPLY:
        _backup(ctx.tenant_dir() / "connections.json")
        ctx.write_json("connections.json", conns)
    return n, skipped


def _rotate_llm_settings(tenant_dir: Path) -> tuple[int, int]:
    ctx.set_tenant(tenant_dir.name)
    cfg = ctx.read_json("llm_settings.json", {})
    if not cfg.get("api_key_enc"):
        return 0, 0
    plain = crypto.decrypt(cfg["api_key_enc"])
    if not plain:
        print(f"  ⚠ {tenant_dir.name}: llm_settings.api_key_enc НЕ расшифровалось — "
              f"оставлено без изменений (проверьте секреты!)")
        return 0, 1
    new_enc = crypto.encrypt(plain)
    if new_enc == cfg["api_key_enc"]:
        return 0, 0
    if APPLY:
        _backup(ctx.tenant_dir() / "llm_settings.json")
        cfg["api_key_enc"] = new_enc
        ctx.write_json("llm_settings.json", cfg)
    return 1, 0


def main() -> None:
    root = ctx.ROOT
    if not root.exists():
        print(f"Нет директории {root} — нечего ротировать.")
        return
    mode = "ПРИМЕНЯЮ (--apply)" if APPLY else "DRY-RUN (ничего не пишу — добавьте --apply для записи)"
    print(f"Режим: {mode}\n")
    total = total_skipped = 0
    for tenant_dir in sorted(root.iterdir()):
        if not tenant_dir.is_dir():
            continue
        n1, s1 = _rotate_connections(tenant_dir)
        n2, s2 = _rotate_llm_settings(tenant_dir)
        n, s = n1 + n2, s1 + s2
        if n:
            print(f"  {tenant_dir.name}: перешифровано значений — {n}")
        total += n
        total_skipped += s
    print(f"\nГотово. {'Перешифровано' if APPLY else 'Будет перешифровано'}: {total}."
          + (f" Пропущено с ошибкой расшифровки: {total_skipped} (см. предупреждения выше)." if total_skipped else ""))
    if total == 0 and total_skipped == 0:
        print("Ничего не изменилось — либо нет сохранённых кредов, либо текущий "
              "APP_SECRET уже совпадает с тем, которым всё зашифровано.")


if __name__ == "__main__":
    main()
