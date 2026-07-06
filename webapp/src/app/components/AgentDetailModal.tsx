import { useEffect, useState } from "react"
import { Modal, ModalSection, ModalPre } from "./Modal"
import { api } from "../../data/api"
import { roleName, roleDesc, roleSkills, roleFromAgentId } from "../../data/roles"
import { STATUS_COLOR } from "../views/ui"

const STATUS_LABEL: Record<string, string> = { active: "В работе", thinking: "Думает", done: "Готов", idle: "Свободен" }

interface Props {
  agentId: string | null
  emoji?: string
  onClose: () => void
  onOpenChat?: (id: string) => void
}

export function AgentDetailModal({ agentId, emoji, onClose, onOpenChat }: Props) {
  const [d, setD] = useState<any>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!agentId) { setD(null); return }
    setLoading(true)
    api.agentDetail(agentId).then(x => { setD(x); setLoading(false) })
  }, [agentId])

  const role = d?.role || (agentId ? roleFromAgentId(agentId) : "")
  const status = d?.status || "idle"
  const done = d?.done || []
  const activity = d?.activity || []
  const skills = roleSkills(role)
  // costs.for_agent() возвращает объект {cost, in_tokens, ...} — берём число
  const costVal = typeof d?.cost === "number" ? d.cost : (d?.cost?.cost || 0)

  return (
    <Modal
      open={!!agentId}
      onClose={onClose}
      title={<span>{emoji} {agentId ? `${roleName(role)}` : ""}</span>}
      subtitle={d ? `${agentId} · модель: ${d.model || "по умолчанию"} · расход $${costVal.toFixed(4)}` : "загрузка…"}
      badge={
        <span style={{ padding: "3px 10px", borderRadius: "var(--radius-pill)", fontSize: 10, fontWeight: 600,
          fontFamily: "var(--font-mono)", letterSpacing: "0.5px",
          background: `${STATUS_COLOR[status]}22`, color: STATUS_COLOR[status],
          border: `1px solid ${STATUS_COLOR[status]}44` }}>
          {STATUS_LABEL[status] || "Свободен"}
        </span>
      }>

      {loading && !d ? (
        <div style={{ color: "var(--muted)", fontSize: 13 }}>Загрузка…</div>
      ) : (
        <>
          {roleDesc(role) && (
            <ModalSection label="Роль">
              <div style={{ fontSize: 13, color: "var(--text-dim)", lineHeight: 1.6 }}>{roleDesc(role)}</div>
              {skills.length > 0 && (
                <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 10 }}>
                  {skills.map(s => (
                    <span key={s} style={{ fontSize: 11, padding: "3px 10px", borderRadius: "var(--radius-pill)",
                      border: "1px solid var(--hairline)", color: "var(--text-dim)", background: "var(--surface-soft)" }}>{s}</span>
                  ))}
                </div>
              )}
            </ModalSection>
          )}

          {(d?.current || d?.task) && (
            <ModalSection label="Текущая работа">
              {d?.task && <div style={{ fontSize: 13, color: "var(--text)", fontWeight: 500, marginBottom: 6 }}>{d.task}</div>}
              {d?.current && d.current !== d.task && (
                <div style={{ fontSize: 12.5, color: "var(--text-dim)", lineHeight: 1.6 }}>{d.current}</div>
              )}
            </ModalSection>
          )}

          {done.length > 0 && (
            <ModalSection label={`Готовые результаты · ${done.length}`}>
              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                {done.map((x: any, i: number) => (
                  <DeliverableItem key={i} title={x.task || x.title || "Результат"} content={x.content || x.result || ""} />
                ))}
              </div>
            </ModalSection>
          )}

          {activity.length > 0 && (
            <ModalSection label="Лента действий">
              <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
                {activity.slice(-30).reverse().map((e: any, i: number) => (
                  <div key={i} style={{ fontSize: 12, color: "var(--text-dim)", lineHeight: 1.5, paddingLeft: 12,
                    borderLeft: "2px solid var(--hairline-strong)" }}>
                    {e.text || e.summary || e.type}
                  </div>
                ))}
              </div>
            </ModalSection>
          )}

          {done.length === 0 && activity.length === 0 && (
            <div style={{ color: "var(--muted)", fontSize: 13 }}>Агент ещё не приступил к работе.</div>
          )}

          {onOpenChat && agentId && (
            <button onClick={() => { onOpenChat(agentId); onClose() }}
              style={{ marginTop: 8, border: "none", borderRadius: "var(--radius-pill)", padding: "10px 20px",
                background: "var(--text)", color: "var(--bg)", cursor: "pointer", fontSize: 13, fontWeight: 500 }}>
              Написать агенту →
            </button>
          )}
        </>
      )}
    </Modal>
  )
}

const PREVIEW_LEN = 220

// Короткий превью результата + кнопка «Показать полностью» вместо простыни текста
// целиком (реальный баг: вкладка «Готовые результаты» рендерила ПОЛНЫЙ контент,
// включая инжектированный контекст задачи, на весь экран).
function DeliverableItem({ title, content }: { title: string; content: string }) {
  const [open, setOpen] = useState(false)
  const isLong = content.length > PREVIEW_LEN
  // Защита от старых записей (до фикса короткой подписи на бэкенде), где title
  // мог содержать весь контекст задачи целиком, а не короткий титул.
  const shortTitle = title.length > 100 ? title.slice(0, 100) + "…" : title
  return (
    <div>
      <div style={{ fontSize: 12, color: "var(--mercury-a)", marginBottom: 6 }}>{shortTitle}</div>
      <ModalPre>{open || !isLong ? content : content.slice(0, PREVIEW_LEN) + "…"}</ModalPre>
      {isLong && (
        <button onClick={() => setOpen(v => !v)}
          style={{ marginTop: 6, fontSize: 11, color: "var(--mercury-a)", background: "transparent",
            border: "none", cursor: "pointer", padding: 0, textDecoration: "underline" }}>
          {open ? "Свернуть ↑" : "Показать полностью →"}
        </button>
      )}
    </div>
  )
}
