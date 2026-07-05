// Разделы навигации — мои 4 + системные (решение пользователя).
// "chats" остаётся валидным Section (используется программно — клик по агенту
// открывает его), но убран из верхнего NavRail (см. NavRail.tsx): Чаты
// открываются из Команды, а не висят отдельным пунктом. "scenario" как Section
// больше не существует — органиграмма стала режимом ВНУТРИ "office"
// (App.tsx: officeMode), а не отдельным разделом (карта сайта, рефакторинг
// сессии 2026-07-05).
export type Section = "office" | "dashboard" | "project" | "team" | "leads" | "chats" | "company" | "account"

// Терминология BOS §12 п.4: домен называет исполнителя Worker (agent — допустимый
// внутренний код-термин, не контрактное имя). Тип переименован из Agent/AgentStatus;
// поле `id` уже было нейтральным к терминологии, не трогаем.
export type WorkerStatus = "active" | "thinking" | "idle" | "done"

export interface Worker {
  id: string
  name: string
  emoji: string
  role: string
  status: WorkerStatus
  lastMessage?: string
}

export type Theme = "dark" | "light"
