// Порт из game.js — отображение ролей (имя + иконка). Источник истины для UI.
export const ROLE_NAMES: Record<string, string> = {
  orchestrator: "CEO", researcher: "Ресёрчер", strategist: "Стратег", architect: "Архитектор", hr: "HR",
  salesman: "Продажник", developer: "Разработчик", marketer: "Маркетолог", analyst: "Аналитик", integrator: "Интегратор",
  cto: "CTO", cmo: "CMO", sales_lead: "Head of Sales", designer: "Дизайнер", onboarding: "Онбординг",
}

export const ROLE_ICONS: Record<string, string> = {
  orchestrator: "🧭", researcher: "🔍", strategist: "📋", architect: "🏗️", hr: "👔",
  salesman: "💰", developer: "💻", marketer: "📢", analyst: "📊", integrator: "🔌",
  cto: "🛠️", cmo: "📣", sales_lead: "💼", designer: "🎨", onboarding: "✨",
}

export const ROLE_DESC: Record<string, string> = {
  orchestrator: "Управляет компанией: открывает отделы, ставит цели, принимает стратегические решения.",
  researcher:   "Исследует рынок и конкурентов через веб-поиск. Работает в режимах quick (3–5 мин) и deep (15–30 мин).",
  strategist:   "На основе данных от Ресёрчера строит бизнес-план: unit-экономика, дорожная карта, приоритеты.",
  architect:    "Проектирует техническое решение и пишет ТЗ — основу для всей разработки.",
  hr:           "Определяет, кого нанимать следующим, исходя из текущих потребностей команды.",
  cto:          "Руководит техническим отделом: ставит задачи разработчикам, контролирует качество.",
  cmo:          "Руководит маркетингом: контент, лиды, публикации сайтов и рекламные кампании.",
  sales_lead:   "Руководит продажами: воронка, работа с лидами, скрипты и конверсия.",
  developer:    "Пишет реальный код в рабочую папку проекта, проверяет и отправляет в GitHub.",
  marketer:     "Создаёт контент, публикует лендинги и собирает лиды с форм обратной связи.",
  salesman:     "Работает с потенциальными клиентами, ведёт переговоры и закрывает сделки.",
  analyst:      "Анализирует данные, строит отчёты и помогает принимать решения на основе цифр.",
  integrator:   "Подключает внешние сервисы через API, настраивает интеграции и автоматизации.",
  designer:     "Создаёт визуальные материалы: UI, иллюстрации, брендинг.",
  onboarding:   "Помогает настроить офис и провести клиента через первые шаги.",
}

export const ROLE_SKILLS: Record<string, string[]> = {
  orchestrator: ["Планирование", "Делегирование", "Управление отделами", "Стратегия"],
  researcher:   ["Веб-поиск", "Конкурентный анализ", "Trend spotting", "Отчёты"],
  strategist:   ["Бизнес-план", "Unit-экономика", "Роадмап", "Принятие решений"],
  architect:    ["ТЗ", "Системный дизайн", "API-проектирование", "Диаграммы"],
  hr:           ["Найм", "Описание ролей", "Структура команды", "Онбординг"],
  cto:          ["Технический надзор", "Code review", "Архитектура", "Деплой"],
  cmo:          ["Контент", "SEO", "Лиды", "Brand"],
  sales_lead:   ["Воронка продаж", "CRM", "Скрипты", "Конверсия"],
  developer:    ["Fullstack", "Git", "Тесты", "CI/CD"],
  marketer:     ["Лендинги", "Email", "Соцсети", "Аналитика"],
  salesman:     ["Переговоры", "Презентации", "Работа с лидами", "Закрытие сделок"],
  analyst:      ["Данные", "Дашборды", "SQL", "A/B тесты"],
  integrator:   ["REST API", "Webhook", "Telegram", "GitHub"],
  designer:     ["UI/UX", "Figma", "Иллюстрации", "Брендинг"],
  onboarding:   ["Настройка", "Гайды", "Бриф", "Поддержка"],
}

export function roleName(role: string): string { return ROLE_NAMES[role] || role }
export function roleIcon(role: string): string  { return ROLE_ICONS[role] || "🤖" }
export function roleDesc(role: string): string  { return ROLE_DESC[role] || "" }
export function roleSkills(role: string): string[] { return ROLE_SKILLS[role] || [] }

// developer_2 → Разработчик 2
export function agentDisplayName(agentId: string, role: string): string {
  const m = agentId.match(/_(\d+)$/)
  return roleName(role) + (m && m[1] !== "1" ? ` ${m[1]}` : "")
}
