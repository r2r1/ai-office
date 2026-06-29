"""Лаунчер для preview: поднимает сервер в DEMO_MODE (без расхода баланса)."""
import os
import sys

# Корень проекта = родитель папки scripts. Гарантируем импорт server:app.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)
os.environ["DEMO_MODE"] = "1"

import uvicorn

if __name__ == "__main__":
    uvicorn.run("server:app", host="127.0.0.1", port=5599, log_level="warning")
