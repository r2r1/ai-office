import type { ReactNode } from "react"

/* Линейные иконки навигации — монохром, stroke=currentColor.
   Один источник истины; никаких эмодзи/символов-заглушек. */
const PATHS: Record<string, ReactNode> = {
  // Офис — дашборд 2×2
  office: (
    <>
      <rect x="3" y="3" width="7.5" height="7.5" rx="1.5" />
      <rect x="13.5" y="3" width="7.5" height="7.5" rx="1.5" />
      <rect x="3" y="13.5" width="7.5" height="7.5" rx="1.5" />
      <rect x="13.5" y="13.5" width="7.5" height="7.5" rx="1.5" />
    </>
  ),
  // Сводка — спидометр/датчик
  dashboard: (
    <>
      <path d="M3.5 14a8.5 8.5 0 0 1 17 0" />
      <path d="M12 14l4-3.5" />
      <circle cx="12" cy="14" r="1.3" />
    </>
  ),
  // Компания — здание с колоннами
  company: (
    <>
      <path d="M3.5 9.5 12 4l8.5 5.5" />
      <path d="M5 9.5V20h14V9.5" />
      <path d="M9 20v-6M12 20v-6M15 20v-6" />
      <path d="M3.5 20h17" />
    </>
  ),
  // Проект — канбан-колонки
  project: (
    <>
      <rect x="3" y="4" width="5" height="16" rx="1.2" />
      <rect x="9.5" y="4" width="5" height="11" rx="1.2" />
      <rect x="16" y="4" width="5" height="7" rx="1.2" />
    </>
  ),
  // Команда — двое людей
  team: (
    <>
      <circle cx="9" cy="7.5" r="3.2" />
      <path d="M3.5 20a5.5 5.5 0 0 1 11 0" />
      <path d="M16 4.8a3 3 0 0 1 0 5.4" />
      <path d="M17.5 14.3A5.5 5.5 0 0 1 20.5 20" />
    </>
  ),
  // Чаты — пузырь сообщения
  chats: (
    <path d="M20 11.5a7.5 7.5 0 0 1-10.6 6.84L4 20l1.66-5.4A7.5 7.5 0 1 1 20 11.5z" />
  ),
  // Итоги — столбчатая диаграмма
  results: (
    <>
      <path d="M3.5 20.5h17" />
      <rect x="6" y="13" width="3" height="7" rx="0.7" />
      <rect x="10.5" y="8" width="3" height="12" rx="0.7" />
      <rect x="15" y="15" width="3" height="5" rx="0.7" />
    </>
  ),
  // Сценарии — узлы связей (граф)
  scenario: (
    <>
      <circle cx="6" cy="6" r="2.4" />
      <circle cx="18" cy="6" r="2.4" />
      <circle cx="12" cy="13" r="2.4" />
      <circle cx="6" cy="20" r="2.4" />
      <circle cx="18" cy="20" r="2.4" />
      <path d="M8 7.5 10.3 11.3M16 7.5 13.7 11.3M10.3 14.8 8 18.5M13.7 14.8 16 18.5" />
    </>
  ),
  // Лиды — карточка контакта
  leads: (
    <>
      <rect x="3" y="5" width="18" height="14" rx="2" />
      <circle cx="9" cy="11" r="2" />
      <path d="M6.5 16a2.5 2.5 0 0 1 5 0" />
      <path d="M14 10h4M14 14h3" />
    </>
  ),
  // Доступы — вилка/разъём
  connections: (
    <>
      <path d="M12 22v-5" />
      <path d="M9 8V2.5" />
      <path d="M15 8V2.5" />
      <path d="M6 8h12v4.5a6 6 0 0 1-12 0z" />
    </>
  ),
  // Аккаунт — пользователь в круге
  account: (
    <>
      <circle cx="12" cy="12" r="9" />
      <circle cx="12" cy="10" r="3.2" />
      <path d="M6.2 18.8a6 6 0 0 1 11.6 0" />
    </>
  ),
  // Настройки (IA-пересборка, вариант C) — шестерёнка
  settings: (
    <>
      <circle cx="12" cy="12" r="3.2" />
      <path d="M19.4 13.5a1.7 1.7 0 0 0 .34 1.87l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.7 1.7 0 0 0-1.87-.34 1.7 1.7 0 0 0-1.04 1.56V20a2 2 0 1 1-4 0v-.09a1.7 1.7 0 0 0-1.04-1.56 1.7 1.7 0 0 0-1.87.34l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.7 1.7 0 0 0 .34-1.87 1.7 1.7 0 0 0-1.56-1.04H4a2 2 0 1 1 0-4h.09a1.7 1.7 0 0 0 1.56-1.04 1.7 1.7 0 0 0-.34-1.87l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.7 1.7 0 0 0 1.87.34H10a1.7 1.7 0 0 0 1.04-1.56V4a2 2 0 1 1 4 0v.09a1.7 1.7 0 0 0 1.04 1.56 1.7 1.7 0 0 0 1.87-.34l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.7 1.7 0 0 0-.34 1.87V10a1.7 1.7 0 0 0 1.56 1.04H20a2 2 0 1 1 0 4h-.09a1.7 1.7 0 0 0-1.56 1.04z" />
    </>
  ),
  // Ресурсы (IA-пересборка, вариант C: Хранилище+Доступы+Приложения+MCP) — стек слоёв
  resources: (
    <>
      <path d="M12 3.5 3.5 8l8.5 4.5L20.5 8z" />
      <path d="M3.5 12 12 16.5l8.5-4.5" />
      <path d="M3.5 16 12 20.5l8.5-4.5" />
    </>
  ),
}

export interface IconProps {
  name: keyof typeof PATHS | string
  size?: number
  strokeWidth?: number
  color?: string
}

export function Icon({ name, size = 19, strokeWidth = 1.7, color = "currentColor" }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
      stroke={color} strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round"
      style={{ display: "block", flexShrink: 0 }}>
      {PATHS[name] ?? null}
    </svg>
  )
}

export type IconName = keyof typeof PATHS
