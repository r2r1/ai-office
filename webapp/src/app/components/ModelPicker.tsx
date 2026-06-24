import { useEffect, useState } from "react"

const MERCURY = "linear-gradient(90deg, #a0e0ab, #ffac2e 50%, #a52d25)"

export interface Preset { id: string; label: string }

interface ModelPickerProps {
  value: string                       // текущая модель (id) или "" (= по умолчанию офиса)
  presets: Preset[]
  onSave: (model: string) => void     // "" допустимо при allowDefault (сброс к дефолту)
  allowDefault?: boolean              // показать опцию «По умолчанию офиса»
  saving?: boolean
  compact?: boolean
}

/** Выбор модели: список пресетов (с ценами) + возможность вписать свою. */
export function ModelPicker({ value, presets, onSave, allowDefault, saving, compact }: ModelPickerProps) {
  const known = new Set(presets.map(p => p.id))
  const valueIsCustom = !!value && !known.has(value)
  const [mode, setMode] = useState<"list" | "custom">(valueIsCustom ? "custom" : "list")
  const [custom, setCustom] = useState(valueIsCustom ? value : "")

  useEffect(() => {
    const c = !!value && !known.has(value)
    setMode(c ? "custom" : "list")
    if (c) setCustom(value)
  }, [value]) // eslint-disable-line

  const selectValue = mode === "custom" ? "__custom__" : (value || (allowDefault ? "" : (presets[0]?.id || "")))

  function onSelect(v: string) {
    if (v === "__custom__") { setMode("custom"); return }
    setMode("list")
    onSave(v)
  }

  const pad = compact ? "8px 12px" : "10px 14px"
  const fs = compact ? 12 : 13

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8, width: "100%" }}>
      <select value={selectValue} onChange={e => onSelect(e.target.value)}
        style={{
          width: "100%", background: "var(--surface-soft)", border: "1px solid var(--hairline)",
          borderRadius: "var(--radius-md)", padding: pad, color: "var(--text)", fontSize: fs,
          outline: "none", cursor: "pointer", fontFamily: "var(--font-sans)",
        }}>
        {allowDefault && <option value="">По умолчанию офиса</option>}
        {presets.map(p => <option key={p.id} value={p.id}>{p.label}</option>)}
        <option value="__custom__">✏️ Другая модель…</option>
      </select>

      {mode === "custom" && (
        <div style={{ display: "flex", gap: 8 }}>
          <input value={custom} onChange={e => setCustom(e.target.value)}
            onKeyDown={e => e.key === "Enter" && custom.trim() && onSave(custom.trim())}
            placeholder="например gpt-5.4 или своя модель" autoFocus
            style={{
              flex: 1, background: "var(--surface-soft)", border: "1px solid rgba(255,172,46,0.4)",
              borderRadius: "var(--radius-md)", padding: pad, color: "var(--text)", fontSize: fs,
              outline: "none", fontFamily: "var(--font-mono)",
            }} />
          <button onClick={() => custom.trim() && onSave(custom.trim())} disabled={saving || !custom.trim()}
            style={{
              border: "none", borderRadius: "var(--radius-md)", padding: "0 16px",
              background: custom.trim() ? MERCURY : "var(--ghost)", color: custom.trim() ? "#0a0a0a" : "var(--muted)",
              cursor: custom.trim() ? "pointer" : "default", fontSize: fs, fontWeight: 500, fontFamily: "var(--font-sans)",
            }}>
            {saving ? "…" : "OK"}
          </button>
        </div>
      )}
    </div>
  )
}
