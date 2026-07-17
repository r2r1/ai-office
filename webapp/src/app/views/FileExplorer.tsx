import { useEffect, useMemo, useRef, useState } from "react"
import { marked } from "marked"
import DOMPurify from "dompurify"
import { api } from "../../data/api"
import { Empty, ViewBody } from "./ui"

interface FileItem { path: string; size?: number }

// ── Дерево из плоских путей ("site/css/style.css" → вложенность) ──
interface TreeNode { name: string; path: string; dir: boolean; children: TreeNode[] }

function buildTree(files: FileItem[]): TreeNode {
  const root: TreeNode = { name: "", path: "", dir: true, children: [] }
  for (const f of files) {
    const parts = f.path.split("/")
    let node = root
    parts.forEach((part, i) => {
      const isLeaf = i === parts.length - 1
      const path = parts.slice(0, i + 1).join("/")
      let child = node.children.find(c => c.name === part && c.dir === !isLeaf)
      if (!child) {
        child = { name: part, path, dir: !isLeaf, children: [] }
        node.children.push(child)
      }
      node = child
    })
  }
  // папки выше файлов, по алфавиту
  const sort = (n: TreeNode) => {
    n.children.sort((a, b) => (a.dir === b.dir ? a.name.localeCompare(b.name) : a.dir ? -1 : 1))
    n.children.forEach(sort)
  }
  sort(root)
  return root
}

const RUNNABLE = /\.(py|js|mjs|sh)$/i
const isHtml = (p: string) => /\.html?$/i.test(p)
const isMd = (p: string) => /\.md$/i.test(p)

marked.setOptions({ breaks: true, gfm: true })

export function FileExplorer({ files, initialProjectFilter }: { files: FileItem[]; initialProjectFilter?: string }) {
  const [selected, setSelected] = useState<string | null>(null)
  const [content, setContent] = useState("")
  const [mode, setMode] = useState<"code" | "preview">("code")
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [runOut, setRunOut] = useState<string>("")
  const [running, setRunning] = useState(false)

  // Фильтр по проекту (параллельные Work, Фаза 3: у каждого проекта — своя
  // подпапка workspace/<workspace_dir>/, см. src/office/workspace.py). Без
  // фильтра дерево мешает файлы ВСЕХ проектов разом — читаемо, только когда
  // проект один; с несколькими параллельными это быстро становится кашей.
  const [projects, setProjects] = useState<{ id: string; title: string; workspace_dir?: string }[]>([])
  // Раньше сюда нельзя было попасть иначе, чем вручную выбрать проект из
  // выпадающего списка — переход «Проект → Хранилище» (живой аудит) теперь
  // сразу открывает нужную папку.
  const [projectFilter, setProjectFilter] = useState<string>(initialProjectFilter || "")
  useEffect(() => { api.projects().then(d => setProjects(d.projects || [])) }, [])
  const scoped = projects.filter(p => p.workspace_dir)
  const filteredFiles = useMemo(() => {
    if (!projectFilter) return files
    const prefix = projectFilter + "/"
    return files.filter(f => f.path.startsWith(prefix))
  }, [files, projectFilter])

  const tree = useMemo(() => buildTree(filteredFiles), [filteredFiles])

  // авто-раскрываем папки верхнего уровня при первой загрузке/смене фильтра
  useEffect(() => {
    if (filteredFiles.length) {
      setExpanded(new Set(tree.children.filter(c => c.dir).map(c => c.path)))
    }
  }, [filteredFiles.length, projectFilter]) // eslint-disable-line

  async function openFile(path: string) {
    setSelected(path); setRunOut(""); setMode(isHtml(path) || isMd(path) ? "preview" : "code")
    const d = await api.fileContent(path)
    setContent(d.content || "")
  }

  function toggle(path: string) {
    setExpanded(prev => {
      const next = new Set(prev)
      next.has(path) ? next.delete(path) : next.add(path)
      return next
    })
  }

  async function runSelected() {
    if (!selected) return
    setRunning(true); setRunOut("Запуск…")
    const d = await api.runFile(selected)
    setRunOut(d.output || "(нет вывода)")
    setRunning(false)
  }

  if (files.length === 0) return (
    <ViewBody>
      <Empty icon="⟨/⟩" text="Рабочая папка пуста"
        hint="Разработчик напишет код через write_file — файлы появятся здесь" />
    </ViewBody>
  )

  const selHtml = selected && isHtml(selected)
  const selMd = selected && isMd(selected)
  const selRun = selected && RUNNABLE.test(selected)

  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", minHeight: 0 }}>
      <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
        {/* дерево папок */}
        <div style={{ width: 250, flexShrink: 0, borderRight: "1px solid var(--hairline)", overflowY: "auto", padding: "10px 0", display: "flex", flexDirection: "column" }}>
          {/* Фильтр по проекту — только если реально есть что фильтровать
              (2+ проекта со своей подпапкой, Фаза 3); один проект — дерево и
              так читаемо целиком, лишний селектор не нужен. */}
          {scoped.length > 1 && (
            <select value={projectFilter} onChange={e => setProjectFilter(e.target.value)}
              style={{
                margin: "0 12px 8px", background: "var(--surface-soft)", border: "1px solid var(--hairline)",
                borderRadius: "var(--radius-sm)", padding: "6px 8px", color: "var(--text)", fontSize: 11.5, outline: "none",
              }}>
              <option value="">Все проекты</option>
              {scoped.map(p => <option key={p.id} value={p.workspace_dir}>{p.title}</option>)}
            </select>
          )}
          <div style={{ flex: 1, overflowY: "auto" }}>
            <TreeView nodes={tree.children} depth={0} selected={selected} expanded={expanded}
              onToggle={toggle} onOpen={openFile} />
          </div>
        </div>

        {/* правая часть: тулбар + код/превью */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
          {selected ? (
            <>
              <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "10px 16px",
                borderBottom: "1px solid var(--hairline)", flexShrink: 0 }}>
                <span className="mono" style={{ fontSize: 11, color: "var(--text-dim)", flex: 1,
                  overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{selected}</span>
                {(selHtml || selMd) && (
                  <>
                    <ToolBtn active={mode === "preview"} onClick={() => setMode("preview")}>Превью</ToolBtn>
                    <ToolBtn active={mode === "code"} onClick={() => setMode("code")}>Код</ToolBtn>
                    {selHtml && (
                      <a href={api.rawUrl(selected)} target="_blank" rel="noreferrer"
                        style={{ textDecoration: "none" }}>
                        <ToolBtn>↗ Открыть</ToolBtn>
                      </a>
                    )}
                  </>
                )}
                {selRun && (
                  <ToolBtn onClick={runSelected} accent disabled={running}>
                    {running ? "▶ …" : "▶ Запустить"}
                  </ToolBtn>
                )}
              </div>

              <div style={{ flex: 1, overflow: "hidden", display: "flex", flexDirection: "column", minHeight: 0 }}>
                {selHtml && mode === "preview" ? (
                  <iframe title="preview" src={api.rawUrl(selected)}
                    style={{ flex: 1, border: "none", background: "#fff", width: "100%" }} />
                ) : selMd && mode === "preview" ? (
                  <MarkdownView content={content} />
                ) : (
                  <pre style={{ flex: 1, overflow: "auto", margin: 0, padding: "16px 20px",
                    fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--text-dim)",
                    lineHeight: 1.6, whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
                    {content || "Загрузка…"}
                  </pre>
                )}
                {runOut && (
                  <div style={{ flexShrink: 0, maxHeight: "32%", overflow: "auto", borderTop: "1px solid var(--hairline)",
                    background: "var(--surface-soft)", padding: "10px 16px" }}>
                    <div className="mono" style={{ fontSize: 9, letterSpacing: "1px", color: "var(--faint)", marginBottom: 6 }}>ВЫВОД</div>
                    <pre style={{ margin: 0, fontFamily: "var(--font-mono)", fontSize: 11.5,
                      color: "var(--text-dim)", whiteSpace: "pre-wrap", wordBreak: "break-word" }}>{runOut}</pre>
                  </div>
                )}
              </div>
            </>
          ) : (
            <div style={{ color: "var(--faint)", fontSize: 13, margin: "auto" }}>Выберите файл слева</div>
          )}
        </div>
      </div>

      {/* терминал */}
      <Terminal />
    </div>
  )
}

// ── Рекурсивное дерево ──
function TreeView({ nodes, depth, selected, expanded, onToggle, onOpen }: {
  nodes: TreeNode[]; depth: number; selected: string | null; expanded: Set<string>
  onToggle: (p: string) => void; onOpen: (p: string) => void
}) {
  return (
    <>
      {nodes.map(node => {
        const isOpen = expanded.has(node.path)
        const isSel = selected === node.path
        return (
          <div key={node.path}>
            <div
              onClick={() => (node.dir ? onToggle(node.path) : onOpen(node.path))}
              style={{
                display: "flex", alignItems: "center", gap: 6, cursor: "pointer",
                padding: "5px 12px", paddingLeft: 12 + depth * 14, fontSize: 12,
                color: isSel ? "var(--text)" : "var(--text-dim)",
                background: isSel ? "var(--hairline-soft)" : "transparent",
                borderLeft: `2px solid ${isSel ? "var(--mercury-a)" : "transparent"}`,
              }}
              onMouseEnter={e => { if (!isSel) (e.currentTarget as HTMLElement).style.background = "var(--surface-soft)" }}
              onMouseLeave={e => { if (!isSel) (e.currentTarget as HTMLElement).style.background = "transparent" }}>
              <span style={{ fontSize: 11, width: 10, color: "var(--faint)" }}>
                {node.dir ? (isOpen ? "▾" : "▸") : ""}
              </span>
              <span style={{ fontSize: 13 }}>{node.dir ? (isOpen ? "📂" : "📁") : fileIcon(node.name)}</span>
              <span className="mono" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {node.name}
              </span>
            </div>
            {node.dir && isOpen && (
              <TreeView nodes={node.children} depth={depth + 1} selected={selected}
                expanded={expanded} onToggle={onToggle} onOpen={onOpen} />
            )}
          </div>
        )
      })}
    </>
  )
}

// ── Рендер .md-файлов, которые пишут агенты (offer.md, tech_design.md, strategy.md…) —
// раньше показывались сырым текстом с "#"/"**" вместо форматирования.
function MarkdownView({ content }: { content: string }) {
  // content — .md-файл, который пишет LLM-агент (write_file), не пользователь
  // напрямую: промпт-инъекция (через web_search/бриф) может заставить агента
  // записать HTML-payload в offer.md/strategy.md — sanitize обязателен, не
  // опционален (аудит docs/technical-due-diligence-2026-07-17.md §4.2).
  const html = useMemo(
    () => DOMPurify.sanitize(marked.parse(content || "") as string),
    [content])
  return (
    <div className="md-preview" style={{ flex: 1, overflow: "auto", padding: "20px 28px" }}
      dangerouslySetInnerHTML={{ __html: html }} />
  )
}

function fileIcon(name: string): string {
  if (/\.html?$/i.test(name)) return "🌐"
  if (/\.css$/i.test(name)) return "🎨"
  if (/\.(js|mjs|ts)$/i.test(name)) return "📜"
  if (/\.py$/i.test(name)) return "🐍"
  if (/\.(png|jpg|jpeg|svg|gif|webp)$/i.test(name)) return "🖼"
  if (/\.(md|txt)$/i.test(name)) return "📄"
  if (/\.json$/i.test(name)) return "⚙️"
  return "📄"
}

function ToolBtn({ children, onClick, active, accent, disabled }: {
  children: React.ReactNode; onClick?: () => void; active?: boolean; accent?: boolean; disabled?: boolean
}) {
  return (
    <button onClick={onClick} disabled={disabled}
      style={{
        padding: "5px 11px", borderRadius: "var(--radius-sm)", fontSize: 11, cursor: disabled ? "default" : "pointer",
        border: "1px solid var(--hairline-strong)",
        background: accent ? "var(--mercury-a)" : active ? "var(--surface-soft)" : "transparent",
        color: accent ? "#0b0b0b" : active ? "var(--text)" : "var(--text-dim)",
        fontWeight: accent ? 600 : 400, opacity: disabled ? 0.5 : 1, whiteSpace: "nowrap",
      }}>
      {children}
    </button>
  )
}

// ── Терминал рабочей папки ──
function Terminal() {
  const [open, setOpen] = useState(false)
  const [cmd, setCmd] = useState("")
  const [log, setLog] = useState<{ cmd: string; out: string }[]>([])
  const [busy, setBusy] = useState(false)
  const bodyRef = useRef<HTMLDivElement>(null)

  useEffect(() => { bodyRef.current?.scrollTo(0, bodyRef.current.scrollHeight) }, [log, open])

  async function send() {
    const c = cmd.trim()
    if (!c || busy) return
    setBusy(true); setCmd("")
    setLog(l => [...l, { cmd: c, out: "…" }])
    const d = await api.terminal(c)
    setLog(l => l.map((e, i) => (i === l.length - 1 ? { ...e, out: d.output || "(нет вывода)" } : e)))
    setBusy(false)
  }

  return (
    <div style={{ flexShrink: 0, borderTop: "1px solid var(--hairline-strong)", background: "var(--surface)" }}>
      <div onClick={() => setOpen(o => !o)}
        style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 16px", cursor: "pointer", userSelect: "none" }}>
        <span style={{ fontSize: 12 }}>{open ? "▾" : "▸"}</span>
        <span className="mono" style={{ fontSize: 11, letterSpacing: "1px", color: "var(--text-dim)" }}>ТЕРМИНАЛ</span>
        <span style={{ fontSize: 10, color: "var(--faint)" }}>рабочая папка проекта</span>
      </div>
      {open && (
        <div style={{ borderTop: "1px solid var(--hairline)" }}>
          <div ref={bodyRef} style={{ maxHeight: 180, overflowY: "auto", padding: "10px 16px",
            background: "var(--surface-soft)", fontFamily: "var(--font-mono)", fontSize: 11.5 }}>
            {log.length === 0 && <div style={{ color: "var(--faint)" }}>Введите команду (например: python bot.py, dir, pip install -r requirements.txt)</div>}
            {log.map((e, i) => (
              <div key={i} style={{ marginBottom: 8 }}>
                <div style={{ color: "var(--mercury-a)" }}>$ {e.cmd}</div>
                <pre style={{ margin: "2px 0 0", color: "var(--text-dim)", whiteSpace: "pre-wrap", wordBreak: "break-word" }}>{e.out}</pre>
              </div>
            ))}
          </div>
          <div style={{ display: "flex", gap: 8, padding: "8px 12px", borderTop: "1px solid var(--hairline)" }}>
            <span className="mono" style={{ color: "var(--mercury-a)", fontSize: 13, alignSelf: "center" }}>$</span>
            <input value={cmd} onChange={e => setCmd(e.target.value)} autoFocus
              onKeyDown={e => { if (e.key === "Enter") send() }}
              placeholder="команда…"
              style={{ flex: 1, background: "transparent", border: "none", outline: "none",
                color: "var(--text)", fontFamily: "var(--font-mono)", fontSize: 12 }} />
            <ToolBtn onClick={send} accent disabled={busy}>{busy ? "…" : "Выполнить"}</ToolBtn>
          </div>
        </div>
      )}
    </div>
  )
}
