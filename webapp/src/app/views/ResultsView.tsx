import { useEffect, useState } from "react"
import { useOffice, refreshData } from "../../data/OfficeProvider"
import { api } from "../../data/api"
import { ViewShell, ViewHead, ViewBody, SubTabs, Card, Empty, SectionLabel } from "./ui"
import { Modal, ModalSection } from "../components/Modal"

// «Результаты» (product-manager разбор, вместо бывшей отдельной «Лиды»):
// лиды — не процесс наравне с «Работа»/«Команда», а ОДИН из ИСХОДОВ, которые
// эта работа производит. Вкладки здесь рендерятся по РЕЕСТРУ (results.py) —
// добавление нового типа результата (приложения, сообщения…) не требует
// правки этого файла целиком, только: (1) регистрация в модуле-производителе,
// (2) один рендерер в RESULT_RENDERERS ниже. Порядок/видимость персональные —
// хранятся per-tenant (ui_prefs.py) и правятся через шестерёнку в шапке.
interface KindMeta { id: string; label: string; icon: string; order: number; count: number }
interface Prefs { order: string[]; hidden: string[] }

function orderKinds(kinds: KindMeta[], prefs: Prefs): KindMeta[] {
  if (!prefs.order.length) return kinds
  const idx = (id: string) => { const i = prefs.order.indexOf(id); return i === -1 ? 999 : i }
  return [...kinds].sort((a, b) => idx(a.id) - idx(b.id))
}

export function ResultsView() {
  const [kinds, setKinds] = useState<KindMeta[]>([])
  const [prefs, setPrefs] = useState<Prefs>({ order: [], hidden: [] })
  const [active, setActive] = useState<string>("leads")
  const [prefsOpen, setPrefsOpen] = useState(false)

  useEffect(() => {
    api.results().then(d => setKinds(d.kinds || []))
    api.uiPrefs("results").then(setPrefs)
  }, [])

  const ordered = orderKinds(kinds, prefs)
  const visible = ordered.filter(k => !prefs.hidden.includes(k.id))
  const tabs = visible.map(k => ({ id: k.id, label: k.label, badge: k.count }))

  useEffect(() => {
    if (tabs.length && !tabs.find(t => t.id === active)) setActive(tabs[0].id)
  }, [tabs.map(t => t.id).join(",")]) // eslint-disable-line

  async function savePrefs(next: Prefs) {
    setPrefs(next)
    await api.setUiPrefs("results", next.order, next.hidden)
  }

  function toggleHidden(id: string) {
    const hidden = prefs.hidden.includes(id) ? prefs.hidden.filter(x => x !== id) : [...prefs.hidden, id]
    savePrefs({ ...prefs, hidden })
  }

  function move(id: string, dir: -1 | 1) {
    const order = ordered.map(k => k.id)
    const i = order.indexOf(id)
    const j = i + dir
    if (j < 0 || j >= order.length) return
    ;[order[i], order[j]] = [order[j], order[i]]
    savePrefs({ ...prefs, order })
  }

  return (
    <ViewShell>
      <ViewHead title="Результаты" sub="Что команда произвела для бизнеса — лиды, сайты и другие исходы работы"
        right={
          <button onClick={() => setPrefsOpen(v => !v)} title="Настроить вкладки"
            style={{ width: 30, height: 30, borderRadius: "var(--radius-pill)", border: "1px solid var(--hairline)",
              background: prefsOpen ? "var(--surface-soft)" : "transparent", color: "var(--muted)", cursor: "pointer",
              display: "flex", alignItems: "center", justifyContent: "center", fontSize: 14 }}>
            ⚙
          </button>
        } />
      {tabs.length > 0 && <SubTabs tabs={tabs} active={active} onChange={setActive} />}
      {prefsOpen && (
        <div style={{ padding: "14px 28px", borderBottom: "1px solid var(--hairline)", background: "var(--surface-soft)" }}>
          <SectionLabel style={{ marginBottom: 10 }}>Порядок и видимость вкладок (только у вас)</SectionLabel>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {ordered.map((k, i) => (
              <div key={k.id} style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 12.5 }}>
                <button onClick={() => move(k.id, -1)} disabled={i === 0}
                  style={{ border: "none", background: "none", color: "var(--muted)", cursor: i === 0 ? "default" : "pointer", opacity: i === 0 ? 0.3 : 1, fontSize: 12 }}>▲</button>
                <button onClick={() => move(k.id, 1)} disabled={i === ordered.length - 1}
                  style={{ border: "none", background: "none", color: "var(--muted)", cursor: i === ordered.length - 1 ? "default" : "pointer", opacity: i === ordered.length - 1 ? 0.3 : 1, fontSize: 12 }}>▼</button>
                <label style={{ display: "flex", alignItems: "center", gap: 8, flex: 1, cursor: "pointer", color: prefs.hidden.includes(k.id) ? "var(--faint)" : "var(--text)" }}>
                  <input type="checkbox" checked={!prefs.hidden.includes(k.id)} onChange={() => toggleHidden(k.id)} />
                  {k.label}
                </label>
              </div>
            ))}
          </div>
        </div>
      )}
      {tabs.length === 0 ? (
        <ViewBody><Empty icon="◈" text="Результатов пока нет" hint="Появятся, когда офис опубликует лендинг или соберёт первую заявку" /></ViewBody>
      ) : (
        <>
          {active === "leads" && <LeadsTab />}
          {active === "sites" && <SitesTab />}
        </>
      )}
    </ViewShell>
  )
}

// ── Лиды: канбан по статусам + карточка с историей (перенесено из бывшей
// отдельной вкладки «Лиды» без изменения логики) ───────────────────────────
const LEAD_COLUMNS = ["new", "contacted", "qualified", "won", "lost"] as const
const STATUS_COLOR: Record<string, string> = {
  new: "#ffac2e", contacted: "#4fc3f7", qualified: "#81c784", won: "#a0e0ab", lost: "var(--faint)",
}
const STALE_MS = 72 * 3600 * 1000

function LeadsTab() {
  const { state } = useOffice()
  const leads = state.leads
  const [labels, setLabels] = useState<Record<string, string>>({})
  const [selected, setSelected] = useState<any | null>(null)
  const [note, setNote] = useState("")
  const [followup, setFollowup] = useState("")
  const [followupResult, setFollowupResult] = useState("")
  const [busy, setBusy] = useState(false)

  useEffect(() => { api.leads().then(d => setLabels(d.labels || {})) }, [])

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
    <>
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
    </>
  )
}

// ── Сайты: опубликованные лендинги компании (across всех проектов) — тот же
// /api/sites, что и «Работа» → карточка проекта → «Артефакты», только здесь
// сводно по всей компании, не по одному проекту. ───────────────────────────
function SitesTab() {
  const { state } = useOffice()
  const sites = state.sites

  if (sites.length === 0) return (
    <ViewBody>
      <Empty icon="🌐" text="Сайтов пока нет" hint="Появятся, когда агент опубликует лендинг" />
    </ViewBody>
  )

  return (
    <ViewBody>
      <SectionLabel>Опубликовано сайтов: {sites.length}</SectionLabel>
      <div style={{ display: "grid", gap: 10, gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))" }}>
        {sites.map((s: any) => (
          <Card key={s.slug}>
            <div style={{ fontSize: 14, fontWeight: 500, color: "var(--text)", marginBottom: 4 }}>{s.title || s.slug}</div>
            <a href={s.url} target="_blank" rel="noreferrer" style={{ fontSize: 11.5, color: "var(--mercury-a)", wordBreak: "break-all" }}>{s.url}</a>
            <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 8, display: "flex", justifyContent: "space-between" }}>
              <span>лидов: {s.leads ?? 0}</span>
              <span className="mono">
                {s.updated_ts ? new Date(s.updated_ts * 1000).toLocaleDateString("ru", { day: "2-digit", month: "short" }) : ""}
              </span>
            </div>
          </Card>
        ))}
      </div>
    </ViewBody>
  )
}
