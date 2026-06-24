import { useEffect } from "react"
import { motion, AnimatePresence } from "motion/react"
import type { ReactNode } from "react"

interface ModalProps {
  open: boolean
  onClose: () => void
  title: ReactNode
  subtitle?: ReactNode
  badge?: ReactNode
  children: ReactNode
}

/** Универсальное модальное окно для полной информации по карточке. */
export function Modal({ open, onClose, title, subtitle, badge, children }: ModalProps) {
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose() }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [open, onClose])

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
          transition={{ duration: 0.18 }}
          onClick={onClose}
          style={{ position: "fixed", inset: 0, zIndex: 90, display: "flex", alignItems: "center", justifyContent: "center",
            background: "rgba(0,0,0,0.5)", backdropFilter: "blur(6px)", WebkitBackdropFilter: "blur(6px)", padding: 24 }}>
          <motion.div
            initial={{ opacity: 0, y: 22, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 16, scale: 0.98 }}
            transition={{ type: "spring", stiffness: 300, damping: 30 }}
            onClick={e => e.stopPropagation()}
            className="glass"
            style={{ width: "100%", maxWidth: 680, maxHeight: "84vh", borderRadius: "var(--radius-xl)",
              display: "flex", flexDirection: "column", overflow: "hidden", position: "relative" }}>

            {/* шапка */}
            <div style={{ padding: "22px 26px 18px", borderBottom: "1px solid var(--hairline)", flexShrink: 0,
              display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 14 }}>
              <div style={{ minWidth: 0 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <div className="display" style={{ fontSize: 22, color: "var(--text)", lineHeight: 1.1 }}>{title}</div>
                  {badge}
                </div>
                {subtitle && <div style={{ fontSize: 12.5, color: "var(--muted)", marginTop: 6 }}>{subtitle}</div>}
              </div>
              <button onClick={onClose} aria-label="Закрыть"
                style={{ width: 30, height: 30, flexShrink: 0, border: "1px solid var(--hairline)", borderRadius: "50%",
                  background: "transparent", color: "var(--muted)", cursor: "pointer", fontSize: 15 }}>
                ✕
              </button>
            </div>

            {/* контент (скролл) */}
            <div style={{ flex: 1, overflowY: "auto", padding: "20px 26px 26px" }}>
              {children}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

/** Блок-секция внутри модалки. */
export function ModalSection({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div style={{ marginBottom: 22 }}>
      <div className="mono" style={{ fontSize: 10, color: "var(--muted)", textTransform: "uppercase",
        letterSpacing: "1.5px", marginBottom: 10 }}>{label}</div>
      {children}
    </div>
  )
}

/** Моноширинный/предформатированный текст (полное содержимое результата). */
export function ModalPre({ children }: { children: ReactNode }) {
  return (
    <div style={{ fontSize: 13, color: "var(--text-dim)", lineHeight: 1.65, whiteSpace: "pre-wrap",
      wordBreak: "break-word", background: "var(--surface-soft)", border: "1px solid var(--hairline)",
      borderRadius: "var(--radius-md)", padding: "14px 16px" }}>
      {children}
    </div>
  )
}
