---
id: vite_react_site
title: Сайт на фреймворке со сборкой (Vite + React/Vue)
description: Полноценное фронтенд-приложение с настоящим шагом сборки — Vite + React или Vue; платформа сама собирает проект (npm install + build) и публикует dist/.
keywords: vite, вайт, react, реакт, vue, вью, npm, сборк, build, билд, фреймворк, framework, spa, приложени, компонент, jsx, tsx
roles: designer, developer
---
СКИЛЛ: сайт на полноценном фреймворке со сборкой. Платформа умеет собирать проект
сама: ты пишешь ИСХОДНИКИ, офис запускает npm install + npm run build и публикует
результат (dist/). НЕ запускай npm/сборку сам через execute_code — это работа
платформы, она сделает это при публикации.

⚠️ КОГДА БРАТЬ ЭТОТ СКИЛЛ, А КОГДА НЕТ:
- Обычный лендинг/многостраничник → НЕ этот скилл: статический HTML/CSS/JS
  (скилл «Продающий лендинг») быстрее и надёжнее — сборка не нужна.
- «Вау»-лендинг с 3D/анимациями → скилл «3D-лендинг» (React через esm.sh, без сборки).
- Этот скилл — когда нужно НАСТОЯЩЕЕ приложение: сложное состояние, роутинг,
  много интерактивных компонентов, или клиент явно попросил React/Vue-стек.
- Если платформа ответит, что сборка отключена оператором — вернись к статике
  или esm.sh: не настаивай на сборке.

СТРУКТУРА ПРОЕКТА (всё внутри site/):
  site/package.json      — scripts.build ОБЯЗАТЕЛЕН: {"build": "vite build"}
  site/vite.config.js    — ОБЯЗАТЕЛЬНО base: './' (сайт хостится под
                           /site/{tenant}/{slug}/ — абсолютные /assets/ не работают):
                             import { defineConfig } from 'vite'
                             export default defineConfig({ base: './', plugins: [...] })
  site/index.html        — entry Vite (<div id="root"> + <script type="module" src="/src/main.jsx">)
  site/src/main.jsx      — маунт приложения
  site/src/App.jsx       — компоненты
  Зависимости — в package.json (react, react-dom, @vitejs/plugin-react, vite в
  devDependencies). Точные версии не выдумывай — мажорные ("^18", "^5") достаточно.

ФОРМА ЗАЯВКИ (обязательна, иначе сайт не пройдёт приёмку):
  Компонент формы шлёт POST на /api/site-lead через fetch:
    fetch('/api/site-lead', { method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ name, contact, message }) })
  Поле contact (телефон или email) обязательно. После успеха покажи
  «Спасибо, свяжемся с вами».

ПРОВЕРКИ ПЕРЕД СДАЧЕЙ:
- verify_code — синтаксис исходников (сборку прогонит платформа при публикации).
- Если публикация вернула «Сборка не прошла» с логом — прочитай лог, почини
  ошибку в исходниках (read_file → write_file), НЕ переписывай проект с нуля.
- Контент (офферы, тексты) бери из docs/site_content.md от маркетолога, стиль —
  из строки «Стиль: …» там же; не выдумывай палитру сам.
