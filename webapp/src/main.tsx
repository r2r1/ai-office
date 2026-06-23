import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import "./styles/design.css"
import App from "./app/App"
import { OfficeProvider } from "./data/OfficeProvider"

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <OfficeProvider>
      <App />
    </OfficeProvider>
  </StrictMode>,
)
