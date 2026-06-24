// Разделы навигации — мои 4 + системные (решение пользователя).
export type Section = "office" | "project" | "team" | "results" | "chats" | "connections" | "account"

export type AgentStatus = "active" | "thinking" | "idle" | "done"

export interface Agent {
  id: string
  name: string
  emoji: string
  role: string
  status: AgentStatus
  lastMessage?: string
}

export type Theme = "dark" | "light"
