---
id: telegram_bot_aiogram
title: Telegram-бот (aiogram)
description: Полный рабочий код Telegram-бота на aiogram 3.x: меню, FSM, запись лидов в платформу.
keywords: telegram, телеграм, бот, aiogram, чат-бот
roles: developer
---
СКИЛЛ: Telegram-бот на aiogram 3.x — полный рабочий код, без сборки.

ПЕРВЫМ ДЕЛОМ: list_files → read_file для ТЗ/текстов/услуг, уже сохранённых
коллегами в workspace (docs/bot_content.md и т.п.). ask_colleague — максимум
1 раз за задачу, только если файлов реально нет.

СТРУКТУРА:
• bot.py — основной файл: polling, обработчики, FSM-состояния.
• config.py — TOKEN, тексты кнопок, цены, услуги (легко менять).
• requirements.txt — aiogram>=3.0, aiosqlite если нужна БД.

ПРИЁМЫ:
• InlineKeyboardMarkup для кнопок выбора услуг/ответов.
• FSM (aiogram.fsm.state, StatesGroup) для многошаговых диалогов.
• Бот ЗАПИСЫВАЕТ лиды в платформу через POST /api/site-lead (эндпоинт уже есть).

ПРОВЕРКИ ПЕРЕД СДАЧЕЙ (чеклист):
1. write_file — пиши ПОЛНЫЙ код (не скелеты, не заглушки, не TODO).
2. verify_code для .py файлов — исправляй ошибки до нуля.
3. execute_code — запусти и убедись, что работает.
4. ask_user перед пушем в GitHub.

ВЫПОЛНЕНИЕ: код пишешь сам через write_file; ЗАПУСК бота (реальный polling
в проде) — задача интегратора, передай через delegate_task после готовности кода.
