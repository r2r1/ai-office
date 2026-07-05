import { useEffect, useState } from "react"
import { useOffice, refreshData } from "../../data/OfficeProvider"
import { api } from "../../data/api"
import { ViewShell, ViewHead, ViewBody, Card, Empty, SectionLabel } from "./ui"
import { Modal, ModalSection } from "../components/Modal"

// Лиды — мини-CRM (канбан по статусам, клик → карточка с историей). Раньше жил
// под-вкладкой в «Результатах» — вынесен на верхний уровень (карта сайта,
// рефакторинг сессии 2026-07-05): CRM — корневая зависимость продукта
// (product-vision.md §4), не второстепенный артефакт наравне с файлами кода.
const LEAD_COLUMNS = ["new", "contacted", "qualified", "won", "lost"] as const
const STATUS_COLOR: Record<string, string> = {
  new: "#ffac2e", contacted: "#4fc3f7", qualified: "#81c784", won: "#a0e0ab", lost: "var(--faint)",
}
const STALE_MS = 72 * 3600 * 1000

export function LeadsView() {
  const { state } = useOffice()
  const leads = state.leads
  const [labels, setLabels] = useState<Record<string, string>>({})
  const [selected, setSelected] = useState<any | null>(null)
  const [note, setNote] = useState("")
  const [followup, setFollowup] = useState("")
  const [followupResult, setFollowupResult] = useState("")
  const [busy, setBusy] = useState(false)

  useEffect(() => { api.leads().then(d => setLabels(d.labels || {})) }, [])

  // Карточка лида раньше закрывалась после КАЖДОГО действия (смена статуса,
  // заметка) — чтобы сделать два действия подряд, приходилось открывать её
  // заново (найдено при разборе governance/CRM-виджетов). Теперь модалка
  // остаётся открытой, а её содержимое само подтягивает свежие данные лида
  // из общего state после refreshData — карточка "живая", а не одноразовая.
  useEffect(() => {
    if (!selected) return
    const updated = leads.find((l: any) => l.id === selected.id)
    if (updated) setSelected(updated)
  }, [leads]) // eslint-disable-line

  async function act(fn: () => Promise<any>) {
    setBusy(true)
    try { await fn() } finally { setBusy(false); await refreshData(["leads"]); setNote("") }
  }

  async function sendFollowup() {
    if (!selected || !followup.trim()) return
    setBusy(true); setFollowupResult("")
    try {
      const r = await api.sendLeadFollowup(selected.id, followup.trim())
      setFollowupResult(r?.ok ? "✅ Отправлено" : `⚠ ${r?.error || r?.result || "Не удалось отправить"}`)
      if (r?.ok) setFollowup("")
      await refreshData(["leads"])
    } finally { setBusy(false) }
  }

  const byStatus = (s: string) => leads.filter((l: any) => (l.status || "new") === s)
  const isStale = (l: any) => (l.status || "new") === "new" && l.ts && (Date.now() - l.ts * 1000) > STALE_MS

  return (
    <ViewShell>
      <ViewHead title="Лиды" sub="Заявки, собранные лендингами и ботами — мини-CRM" />
      {leads.length === 0 ? (
        <ViewBody>
          <Empty icon="◈" text="Заявок пока нет"
            hint="Лиды появятся, когда агент опубликует лендинг и посетители оставят контакты" />
        </ViewBody>
      ) : (
        <ViewBody style={{ overflowX: "auto" }}>
          <SectionLabel style={{ marginBottom: 16 }}>Всего заявок: {leads.length}</SectionLabel>
          <div style={{ display: "flex", gap: 14, minWidth: 900 }}>
            {LEAD_COLUMNS.map(col => {
              const items = byStatus(col)
              return (
                <div key={col} style={{ flex: 1, minWidth: 180 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 10 }}>
                    <span style={{ width: 7, height: 7, borderRadius: "50%", background: STATUS_COLOR[col] }} />
                    <span style={{ fontSize: 11.5, fontWeight: 600, color: "var(--text-dim)", textTransform: "uppercase", letterSpacing: "0.5px" }}>
                      {labels[col] || col}
                    </span>
                    <span className="mono" style={{ fontSize: 10.5, color: "var(--faint)" }}>{items.length}</span>
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    {items.map((l: any) => (
                      <Card key={l.id} onClick={() => { setSelected(l); setFollowup(""); setFollowupResult("") }} style={{ padding: "10px 12px" }}>
                        <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                          <div style={{ fontSize: 12.5, fontWeight: 500, color: "var(--text)", minWidth: 0,
                            overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                            {l.name || "Аноним"}
                          </div>
                          {isStale(l) && <span title="Без ответа 72+ часов" style={{ fontSize: 11, flexShrink: 0 }}>🟡</span>}
                        </div>
                        {(l.contact) && (
                          <div style={{ fontSize: 11, color: "var(--mercury-a)", marginTop: 2 }}>{l.contact}</div>
                        )}
                        <div className="mono" style={{ fontSize: 9.5, color: "var(--faint)", marginTop: 5 }}>
                          {l.ts ? new Date(l.ts * 1000).toLocaleDateString("ru", { day: "2-digit", month: "short" }) : ""}
                        </div>
                      </Card>
                    ))}
                    {items.length === 0 && (
                      <div style={{ fontSize: 11, color: "var(--faint)", padding: "8px 2px" }}>—</div>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        </ViewBody>
      )}

      <Modal open={!!selected} onClose={() => setSelected(null)}
        title={selected?.name || "Аноним"} subtitle={selected?.contact}>
        {selected && (
          <>
            {selected.message && (
              <ModalSection label="Сообщение">
                <div style={{ fontSize: 13, color: "var(--text-dim)", lineHeight: 1.5 }}>{selected.message}</div>
              </ModalSection>
            )}
            <ModalSection label="Статус">
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                {LEAD_COLUMNS.map(s => (
                  <button key={s} disabled={busy || (selected.status || "new") === s}
                    onClick={() => act(() => api.setLeadStatus(selected.id, s))}
                    style={{
                      padding: "6px 12px", borderRadius: "var(--radius-pill)", fontSize: 11.5,
                      border: `1px solid ${(selected.status || "new") === s ? STATUS_COLOR[s] : "var(--hairline-strong)"}`,
                      background: (selected.status || "new") === s ? STATUS_COLOR[s] + "22" : "transparent",
                      color: (selected.status || "new") === s ? "var(--text)" : "var(--muted)",
                      cursor: busy ? "default" : "pointer", opacity: busy ? 0.6 : 1,
                    }}>
                    {labels[s] || s}
                  </button>
                ))}
              </div>
            </ModalSection>
            <ModalSection label="История">
              <div style={{ display: "flex", flexDirection: "column", gap: 8, maxHeight: 200, overflowY: "auto" }}>
                {(selected.history || []).slice().reverse().map((h: any, i: number) => (
                  <div key={i} style={{ fontSize: 12, color: "var(--text-dim)", lineHeight: 1.5,
                    borderLeft: "2px solid var(--hairline-strong)", paddingLeft: 10 }}>
                    <div className="mono" style={{ fontSize: 9.5, color: "var(--faint)" }}>
                      {new Date(h.ts * 1000).toLocaleString("ru", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" })}
                    </div>
                    {h.text}
                  </div>
                ))}
              </div>
            </ModalSection>
            <ModalSection label="Написать в Telegram (личный аккаунт)">
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                <textarea value={followup} onChange={e => setFollowup(e.target.value)} rows={3}
                  placeholder="Например: Добрый день! Уточняю, актуален ли ещё вопрос по замеру?"
                  style={{ padding: "8px 10px", borderRadius: "var(--radius-md)", resize: "vertical",
                    border: "1px solid var(--hairline-strong)", background: "var(--surface)",
                    color: "var(--text)", fontSize: 12.5, fontFamily: "var(--font-sans)" }} />
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
                  <span style={{ fontSize: 11, color: "var(--faint)" }}>
                    Уйдёт как личное сообщение с вашего Telegram-аккаунта (не от бота)
                  </span>
                  <button disabled={busy || !followup.trim()} onClick={sendFollowup}
                    style={{ padding: "8px 14px", borderRadius: "var(--radius-pill)", border: "1px solid var(--hairline-strong)",
                      background: "transparent", color: "var(--text)", cursor: busy ? "default" : "pointer",
                      fontSize: 12.5, opacity: busy || !followup.trim() ? 0.5 : 1, flexShrink: 0 }}>
                    Отправить
                  </button>
                </div>
                {followupResult && (
                  <div style={{ fontSize: 11.5, color: followupResult.startsWith("✅") ? "#a0e0ab" : "#ffac2e" }}>
                    {followupResult}
                  </div>
                )}
              </div>
            </ModalSection>
            <ModalSection label="Добавить заметку">
              <div style={{ display: "flex", gap: 8 }}>
                <input value={note} onChange={e => setNote(e.target.value)}
                  placeholder="Например: договорились созвониться завтра"
                  onKeyDown={e => { if (e.key === "Enter" && note.trim()) act(() => api.addLeadNote(selected.id, note)) }}
                  style={{ flex: 1, padding: "8px 10px", borderRadius: "var(--radius-md)",
                    border: "1px solid var(--hairline-strong)", background: "var(--surface)", color: "var(--text)", fontSize: 12.5 }} />
                <button disabled={busy || !note.trim()} onClick={() => act(() => api.addLeadNote(selected.id, note))}
                  style={{ padding: "8px 14px", borderRadius: "var(--radius-pill)", border: "1px solid var(--hairline-strong)",
                    background: "transparent", color: "var(--text)", cursor: busy ? "default" : "pointer",
                    fontSize: 12.5, opacity: busy || !note.trim() ? 0.5 : 1 }}>
                  Добавить
                </button>
              </div>
            </ModalSection>
          </>
        )}
      </Modal>
    </ViewShell>
  )
}
