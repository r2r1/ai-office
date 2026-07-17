import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import "./styles/design.css"
import { Gate } from "./app/Gate"
import { ErrorBoundary } from "./app/components/ErrorBoundary"

// OAuth-подключение интеграции (Google/Bitrix24/Figma) открывается в ОТДЕЛЬНОМ
// окне (ConnectionsView.tsx:openOAuthPopup), а не той же вкладке — раньше
// window.location.href уводил всю SPA на страницу согласия Google, и если
// последний шаг подключения зависал (реальный кейс), пользователь возвращался
// кнопкой «назад» браузера — это ломало историю/состояние SPA и выглядело как
// "всё зависло". Теперь редирект от бэкенда (/auth/*/callback → /webapp/
// ?connected=X) всё ещё прилетает НА ЭТУ страницу, просто в popup-окне —
// перехватываем ДО монтирования React-приложения (незачем грузить весь
// офис ради окна, которое через мгновение закроется), сообщаем результат
// открывшей вкладке через postMessage и закрываемся сами.
const params = new URLSearchParams(window.location.search)
const oauthResult = params.get("connected")
  || (params.has("google_error") && "google_error")
  || (params.has("figma_error") && "figma_error")
  || (params.has("bitrix24_error") && "bitrix24_error")
if (window.opener && !window.opener.closed && oauthResult) {
  window.opener.postMessage({ source: "ai-office-oauth", result: oauthResult }, window.location.origin)
  window.close()
} else {
  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      <ErrorBoundary>
        <Gate />
      </ErrorBoundary>
    </StrictMode>,
  )
}
