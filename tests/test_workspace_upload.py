"""
Тест workspace.write_bytes — сохранение сырых байтов (загрузка пользователя:
фото/аудио/PDF, round2 audit, раунд1 #2). Раньше в workspace.py была только
write_file (текст) — бинарные вложения сохранить было нечем.

    python tests/test_workspace_upload.py
"""

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.saas import context as ctx
from src.office import workspace


def _fresh(name: str) -> None:
    ctx.set_tenant(name)
    ctx.wipe()
    ctx.set_tenant(name)


def test_write_bytes_creates_file_with_exact_content():
    _fresh("ws_upload_test_basic")
    data = b"\x89PNG\r\n\x1a\nfake-png-bytes"
    full = workspace.write_bytes("uploads/photo.png", data)
    assert full is not None
    assert full.is_file()
    assert full.read_bytes() == data


def test_write_bytes_creates_parent_dirs():
    _fresh("ws_upload_test_parents")
    full = workspace.write_bytes("uploads/deep/nested/file.pdf", b"pdf-bytes")
    assert full is not None
    assert full.is_file()


def test_write_bytes_rejects_path_traversal():
    _fresh("ws_upload_test_traversal")
    assert workspace.write_bytes("../../etc/passwd", b"x") is None


def test_write_bytes_rejects_oversized_upload():
    _fresh("ws_upload_test_oversized")
    too_big = b"x" * (workspace.MAX_UPLOAD_BYTES + 1)
    assert workspace.write_bytes("uploads/huge.bin", too_big) is None


def test_write_bytes_accepts_file_at_exact_limit():
    _fresh("ws_upload_test_at_limit")
    exact = b"x" * workspace.MAX_UPLOAD_BYTES
    assert workspace.write_bytes("uploads/exact.bin", exact) is not None


def test_read_bytes_reads_back_what_write_bytes_wrote():
    _fresh("ws_upload_test_roundtrip")
    data = b"round-trip-bytes-\x00\x01\x02"
    workspace.write_bytes("uploads/roundtrip.bin", data)
    assert workspace.read_bytes("uploads/roundtrip.bin") == data


def _cleanup_test_tenants() -> None:
    for d in ctx.ROOT.glob("ws_upload_test_*"):
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
