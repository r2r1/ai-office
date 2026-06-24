import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import "./styles/design.css"
import { Gate } from "./app/Gate"

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Gate />
  </StrictMode>,
)
