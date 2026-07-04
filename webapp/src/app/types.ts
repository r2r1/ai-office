// Разделы навигации — мои 4 + системные (решение пользователя).
export type Section = "office" | "dashboard" | "project" | "team" | "scenario" | "results" | "chats" | "company" | "account"

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
