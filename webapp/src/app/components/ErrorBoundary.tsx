import { Component, type ErrorInfo, type ReactNode } from "react"

interface Props { children: ReactNode }
interface State { error: Error | null }

// Аудит docs/technical-due-diligence-2026-07-17.md §4.4: до этого компонента
// НИ ОДНОЙ необработанной ошибки рендера не было где перехватить — любое
// исключение в любом дочернем компоненте (например, некорректные данные с
// бэкенда) ронялo всё приложение в белый пустой экран без единой подсказки
// пользователю, что случилось и что делать.
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // eslint-disable-next-line no-console
    console.error("[ErrorBoundary] необработанная ошибка рендера:", error, info.componentStack)
  }

  render() {
    if (!this.state.error) return this.props.children
    return (
      <div style={{
        display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
        height: "100vh", gap: 16, padding: 24, textAlign: "center",
        background: "var(--bg, #0a0908)", color: "var(--text, #f2f0ed)",
      }}>
        <div style={{ fontSize: 32 }}>⚠️</div>
        <div style={{ fontSize: 18, fontWeight: 600 }}>Что-то пошло не так</div>
        <div style={{ fontSize: 14, color: "var(--muted, #9b968f)", maxWidth: 480 }}>
          Произошла непредвиденная ошибка интерфейса. Ваши данные не затронуты —
          попробуйте перезагрузить страницу.
        </div>
        <button
          onClick={() => window.location.reload()}
          style={{
            marginTop: 8, padding: "10px 20px", borderRadius: 8, border: "none",
            background: "var(--accent, #a0e0ab)", color: "#0a0908", fontWeight: 600,
            cursor: "pointer", fontSize: 14,
          }}>
          Перезагрузить страницу
        </button>
      </div>
    )
  }
}
