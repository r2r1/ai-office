// Вкладка «Сценарии» — живая диаграмма оргструктуры и потока работы
// (см. docs/scenario-graph-tab-spec.md). НЕ дублирует план-граф задач вкладки
// «Проект» — узлы здесь это компания → отделы → сотрудники, клик даёт
// write-управление узлом (пауза/переназначение/чат), а не только просмотр.
import { useEffect, useRef, useState, useLayoutEffect, useCallback } from "react"
import { api } from "../../data/api"
import { roleIcon, roleName, workerDisplayName } from "../../data/roles"
import { ViewShell, ViewHead, ViewBody, Pill, STATUS_COLOR } from "./ui"
import { Modal, ModalSection } from "../components/Modal"

interface GNode {
  id: string
  type: "ceo" | "department" | "leader" | "agent"
  label: string
  status: string
  role?: string
  agent_id?: string
  task_id?: string
  task_title?: string
  objective?: string
}
interface GEdge { from: string; to: string; kind: string }

const STATUS_LABEL: Record<string, string> = {
  thinking: "думает", idle: "свободен", done: "свободен", paused: "на паузе",
  open: "открыт", closed: "не открыт", hiring: "ещё не нанят",
}

function statusColor(s: string): string {
  if (s === "paused") return "var(--faint)"
  if (s === "closed" || s === "hiring") return "var(--faint)"
  return STATUS_COLOR[s] || "var(--whisper)"
}

export function ScenarioView({ onOpenChat }: { onOpenChat: (id: string) => void }) {
  const [nodes, setNodes] = useState<GNode[]>([])
  const [edges, setEdges] = useState<GEdge[]>([])
  const [selected, setSelected] = useState<GNode | null>(null)
  const [reassignTo, setReassignTo] = useState("")
  const [busy, setBusy] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)
  const nodeRefs = useRef<Record<string, HTMLDivElement | null>>({})
  const [lines, setLines] = useState<Array<{ x1: number; y1: number; x2: number; y2: number }>>([])

  const load = useCallback(() => {
    api.orgGraph().then(g => { setNodes(g.nodes || []); setEdges(g.edges || []) })
  }, [])

  useEffect(() => { load(); const t = setInterval(load, 4000); return () => clearInterval(t) }, [load])

  // Пересчитываем линии связей ПОСЛЕ того, как узлы реально легли в поток (обычный
  // flex-layout, не абсолютное позиционирование) — координаты меряем по факту, не
  // считаем вручную, иначе перенос строк на узком экране рассинхронит линии с узлами.
  useLayoutEffect(() => {
    const cont = containerRef.current
    if (!cont) return
    const cr = cont.getBoundingClientRect()
    const next: Array<{ x1: number; y1: number; x2: number; y2: number }> = []
    for (const e of edges) {
      const a = nodeRefs.current[e.from]
      const b = nodeRefs.current[e.to]
      if (!a || !b) continue
      const ar = a.getBoundingClientRect()
      const br = b.getBoundingClientRect()
      next.push({
        x1: ar.left - cr.left + ar.width / 2, y1: ar.bottom - cr.top,
        x2: br.left - cr.left + br.width / 2, y2: br.top - cr.top,
      })
    }
    setLines(next)
  }, [nodes, edges])

  const ceo = nodes.find(n => n.type === "ceo")
  const depts = nodes.filter(n => n.type === "department")
  const staff = nodes.filter(n => n.type === "agent" && !depts.some(d => edges.some(e => e.from === d.id && e.to === n.id)))
  const membersOf = (deptId: string) => {
    const ids = new Set(edges.filter(e => e.from === deptId).map(e => e.to))
    return nodes.filter(n => ids.has(n.id))
  }

  async function refreshAfter(fn: () => Promise<any>) {
    setBusy(true)
    try { await fn() } finally { setBusy(false); load(); setSelected(null) }
  }

  const sameRoleFree = selected
    ? nodes.filter(n => n.type !== "department" && n.role === selected.role
        && n.agent_id !== selected.agent_id && n.status === "idle")
    : []

  return (
    <ViewShell>
      <ViewHead title="Сценарии" sub="Оргструктура и живой поток работы — кликните на узел" />
      <ViewBody>
        {!ceo ? (
          <div style={{ padding: 40, textAlign: "center", color: "var(--muted)", fontSize: 13 }}>
            Компания ещё не сформирована
          </div>
        ) : (
          <div ref={containerRef} style={{ position: "relative", minHeight: 320 }}>
            <svg style={{ position: "absolute", inset: 0, width: "100%", height: "100%", pointerEvents: "none", zIndex: 0 }}>
              {lines.map((l, i) => (
                <path key={i} d={`M ${l.x1} ${l.y1} C ${l.x1} ${(l.y1 + l.y2) / 2}, ${l.x2} ${(l.y1 + l.y2) / 2}, ${l.x2} ${l.y2}`}
                  fill="none" stroke="var(--hairline-strong)" strokeWidth={1.5} />
              ))}
            </svg>

            <div style={{ position: "relative", zIndex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 36 }}>
              <NodeCard node={ceo} refCb={el => (nodeRefs.current[ceo.id] = el)} onClick={() => setSelected(ceo)} />

              <div style={{ display: "flex", gap: 28, flexWrap: "wrap", justifyContent: "center", width: "100%" }}>
                {staff.length > 0 && (
                  <Column title="Штаб CEO">
                    {staff.map(n => (
                      <NodeCard key={n.id} node={n} refCb={el => (nodeRefs.current[n.id] = el)} onClick={() => setSelected(n)} />
                    ))}
                  </Column>
                )}
                {depts.map(d => (
                  <Column key={d.id} title={d.label} statusBadge={d.status === "open" ? undefined : "не открыт"}>
                    <NodeCard node={d} refCb={el => (nodeRefs.current[d.id] = el)} onClick={() => setSelected(d)} compact />
                    {membersOf(d.id).map(n => (
                      <NodeCard key={n.id} node={n} refCb={el => (nodeRefs.current[n.id] = el)} onClick={() => setSelected(n)} />
                    ))}
                  </Column>
                ))}
              </div>
            </div>
          </div>
        )}
      </ViewBody>

      <Modal open={!!selected} onClose={() => setSelected(null)}
        title={selected ? nodeTitle(selected) : ""}
        subtitle={selected?.type === "department" ? (selected.objective || "Цель ещё не поставлена")
          : selected?.role ? roleName(selected.role) : undefined}>
        {selected && selected.type !== "department" && (
          <>
            <ModalSection label="Статус">
              <span style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12, color: "var(--text-dim)" }}>
                <span style={{ width: 7, height: 7, borderRadius: "50%", background: statusColor(selected.status) }} />
                {STATUS_LABEL[selected.status] || selected.status}
              </span>
            </ModalSection>
            {selected.task_id && (
              <ModalSection label="Текущая задача">
                <div style={{ fontSize: 13, color: "var(--text-dim)", lineHeight: 1.5 }}>{selected.task_title}</div>
              </ModalSection>
            )}
            {!selected.agent_id ? (
              <ModalSection label="Действия">
                <div style={{ fontSize: 12, color: "var(--faint)" }}>Ещё не нанят — управление появится после найма</div>
              </ModalSection>
            ) : (
              <ModalSection label="Действия">
                <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                  <ActionButton disabled={busy} onClick={() => onOpenChat(selected.agent_id!)}>
                    💬 Написать
                  </ActionButton>
                  {selected.status === "paused" ? (
                    <ActionButton disabled={busy} onClick={() => refreshAfter(() => api.resumeAgent(selected.agent_id!))}>
                      ▶ Снять с паузы
                    </ActionButton>
                  ) : (
                    <ActionButton disabled={busy} onClick={() => refreshAfter(() => api.pauseAgent(selected.agent_id!))}>
                      ⏸ Поставить на паузу
                    </ActionButton>
                  )}
                </div>
              </ModalSection>
            )}
            {selected.task_id && (
              <ModalSection label="Переназначить задачу">
                {sameRoleFree.length === 0 ? (
                  <div style={{ fontSize: 12, color: "var(--faint)" }}>
                    Нет свободных сотрудников той же роли ({roleName(selected.role || "")})
                  </div>
                ) : (
                  <div style={{ display: "flex", gap: 8 }}>
                    <select value={reassignTo} onChange={e => setReassignTo(e.target.value)}
                      style={{ flex: 1, padding: "8px 10px", borderRadius: "var(--radius-md)",
                        border: "1px solid var(--hairline-strong)", background: "var(--surface)", color: "var(--text)", fontSize: 12.5 }}>
                      <option value="">Выберите сотрудника…</option>
                      {sameRoleFree.map(n => (
                        <option key={n.agent_id} value={n.agent_id}>{workerDisplayName(n.agent_id!, n.role!)}</option>
                      ))}
                    </select>
                    <ActionButton disabled={busy || !reassignTo}
                      onClick={() => refreshAfter(() => api.reassignTask(selected.task_id!, reassignTo))}>
                      Переназначить
                    </ActionButton>
                  </div>
                )}
              </ModalSection>
            )}
          </>
        )}
      </Modal>
    </ViewShell>
  )
}

function nodeTitle(n: GNode): string {
  if (n.type === "ceo") return "CEO"
  if (n.type === "department") return n.label
  return workerDisplayName(n.agent_id || n.label, n.role || "")
}

function Column({ title, statusBadge, children }: { title: string; statusBadge?: string; children: React.ReactNode }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 12, minWidth: 160 }}>
      <div style={{ fontSize: 11, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "1px", display: "flex", gap: 6, alignItems: "center" }}>
        {title}
        {statusBadge && <Pill>{statusBadge}</Pill>}
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 10, alignItems: "center" }}>{children}</div>
    </div>
  )
}

function NodeCard({ node, refCb, onClick, compact }: {
  node: GNode; refCb: (el: HTMLDivElement | null) => void; onClick: () => void; compact?: boolean
}) {
  const color = statusColor(node.status)
  const icon = node.type === "ceo" ? "🧭" : node.type === "department" ? "🏢" : roleIcon(node.role || "")
  const label = node.type === "ceo" ? "CEO" : node.type === "department" ? node.label
    : workerDisplayName(node.agent_id || node.label, node.role || "")
  return (
    <div ref={refCb} onClick={onClick} className="card"
      style={{
        width: compact ? 150 : 138, padding: compact ? "10px 12px" : "10px 12px", borderRadius: "var(--radius-md)",
        cursor: "pointer", textAlign: "center", position: "relative",
        borderColor: node.status === "thinking" ? "rgba(255,172,46,0.4)" : undefined,
        transition: "transform 0.15s, border-color 0.15s",
      }}
      onMouseEnter={e => (e.currentTarget.style.transform = "translateY(-2px)")}
      onMouseLeave={e => (e.currentTarget.style.transform = "")}>
      <span style={{ position: "absolute", top: 8, right: 8, width: 7, height: 7, borderRadius: "50%", background: color }} />
      <div style={{ fontSize: 18, marginBottom: 4 }}>{icon}</div>
      <div style={{ fontSize: 12, fontWeight: 500, color: "var(--text)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
        {label}
      </div>
      {node.task_title && (
        <div style={{ fontSize: 10, color: "var(--muted)", marginTop: 3, lineHeight: 1.3,
          display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
          {node.task_title}
        </div>
      )}
    </div>
  )
}

function ActionButton({ children, onClick, disabled }: { children: React.ReactNode; onClick: () => void; disabled?: boolean }) {
  return (
    <button onClick={onClick} disabled={disabled}
      style={{ padding: "8px 14px", borderRadius: "var(--radius-pill)", border: "1px solid var(--hairline-strong)",
        background: "transparent", color: "var(--text)", cursor: disabled ? "default" : "pointer",
        fontSize: 12.5, opacity: disabled ? 0.5 : 1, fontFamily: "var(--font-sans)" }}>
      {children}
    </button>
  )
}
