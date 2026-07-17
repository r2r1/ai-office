import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import "./styles/design.css"
import { Gate } from "./app/Gate"
import { ErrorBoundary } from "./app/components/ErrorBoundary"

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ErrorBoundary>
      <Gate />
    </ErrorBoundary>
  </StrictMode>,
)
