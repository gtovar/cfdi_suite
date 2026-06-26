import React, { useState, useEffect, useRef } from 'react'

const TEMPLATE_ID = 'default'

export default function HtmlTemplateEditor({ templateId = TEMPLATE_ID }) {
  const [html, setHtml] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [previewing, setPreviewing] = useState(false)
  const [previewUrl, setPreviewUrl] = useState(null)
  const [status, setStatus] = useState(null)
  const textareaRef = useRef(null)

  useEffect(() => {
    fetch(`/api/templates/${templateId}/html`)
      .then(r => r.json())
      .then(d => { setHtml(d.html || ''); setLoading(false) })
      .catch(() => setLoading(false))
  }, [templateId])

  const handleSave = async () => {
    setSaving(true)
    setStatus(null)
    try {
      const res = await fetch(`/api/templates/${templateId}/html`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ html }),
      })
      if (res.ok) {
        setStatus({ type: 'success', msg: 'HTML guardado correctamente.' })
      } else {
        const d = await res.json()
        setStatus({ type: 'error', msg: d.detail || 'Error al guardar.' })
      }
    } catch (e) {
      setStatus({ type: 'error', msg: String(e) })
    } finally {
      setSaving(false)
    }
  }

  const handlePreview = async () => {
    setPreviewing(true)
    setStatus(null)
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl)
      setPreviewUrl(null)
    }
    try {
      const res = await fetch(`/api/templates/${templateId}/shell-preview`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ html }),
      })
      if (!res.ok) {
        const d = await res.json().catch(() => ({}))
        setStatus({ type: 'error', msg: d.detail || 'Error en preview.' })
        return
      }
      const blob = await res.blob()
      setPreviewUrl(URL.createObjectURL(blob))
    } catch (e) {
      setStatus({ type: 'error', msg: String(e) })
    } finally {
      setPreviewing(false)
    }
  }

  const handleTab = (e) => {
    if (e.key === 'Tab') {
      e.preventDefault()
      const ta = textareaRef.current
      const start = ta.selectionStart
      const end = ta.selectionEnd
      const next = html.substring(0, start) + '  ' + html.substring(end)
      setHtml(next)
      requestAnimationFrame(() => {
        ta.selectionStart = ta.selectionEnd = start + 2
      })
    }
  }

  if (loading) return (
    <div style={{ padding: '2rem', color: 'hsl(var(--muted-foreground))' }}>
      Cargando template HTML...
    </div>
  )

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', gap: '0.75rem' }}>
      {/* Toolbar */}
      <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexShrink: 0 }}>
        <button
          onClick={handleSave}
          disabled={saving}
          style={{
            padding: '0.4rem 1rem',
            background: 'hsl(var(--primary))',
            color: 'hsl(var(--primary-foreground))',
            border: 'none',
            borderRadius: '6px',
            cursor: saving ? 'not-allowed' : 'pointer',
            fontSize: '0.85rem',
            fontWeight: 600,
            opacity: saving ? 0.7 : 1,
          }}
        >
          {saving ? 'Guardando...' : 'Guardar HTML'}
        </button>
        <button
          onClick={handlePreview}
          disabled={previewing}
          style={{
            padding: '0.4rem 1rem',
            background: 'hsl(var(--secondary))',
            color: 'hsl(var(--secondary-foreground))',
            border: '1px solid hsl(var(--border))',
            borderRadius: '6px',
            cursor: previewing ? 'not-allowed' : 'pointer',
            fontSize: '0.85rem',
            fontWeight: 600,
            opacity: previewing ? 0.7 : 1,
          }}
        >
          {previewing ? 'Generando...' : 'Vista previa PDF'}
        </button>
        {status && (
          <span style={{
            fontSize: '0.8rem',
            color: status.type === 'success' ? '#276749' : '#C53030',
            padding: '0.25rem 0.5rem',
            borderRadius: '4px',
            background: status.type === 'success' ? '#F0FFF4' : '#FFF5F5',
          }}>
            {status.msg}
          </span>
        )}
        <span style={{ marginLeft: 'auto', fontSize: '0.75rem', color: 'hsl(var(--muted-foreground))' }}>
          Placeholders: {'{{'} emisor_nombre {'}}'},  {'{{'} receptor_nombre {'}}'},  {'{{'} total {'}}'},  {'{{'} fecha {'}}'}
        </span>
      </div>

      {/* Split panes */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem', flex: 1, minHeight: 0 }}>
        {/* Editor */}
        <div style={{
          display: 'flex',
          flexDirection: 'column',
          border: '1px solid hsl(var(--border))',
          borderRadius: '8px',
          overflow: 'hidden',
        }}>
          <div style={{
            padding: '0.35rem 0.75rem',
            background: 'hsl(var(--muted))',
            borderBottom: '1px solid hsl(var(--border))',
            fontSize: '0.75rem',
            color: 'hsl(var(--muted-foreground))',
            fontWeight: 600,
          }}>
            HTML + CSS
          </div>
          <textarea
            ref={textareaRef}
            value={html}
            onChange={e => setHtml(e.target.value)}
            onKeyDown={handleTab}
            spellCheck={false}
            style={{
              flex: 1,
              resize: 'none',
              border: 'none',
              outline: 'none',
              padding: '0.75rem',
              fontFamily: 'monospace',
              fontSize: '12px',
              lineHeight: 1.5,
              background: 'hsl(var(--card))',
              color: 'hsl(var(--foreground))',
              overflowY: 'auto',
            }}
          />
        </div>

        {/* Preview */}
        <div style={{
          border: '1px solid hsl(var(--border))',
          borderRadius: '8px',
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
        }}>
          <div style={{
            padding: '0.35rem 0.75rem',
            background: 'hsl(var(--muted))',
            borderBottom: '1px solid hsl(var(--border))',
            fontSize: '0.75rem',
            color: 'hsl(var(--muted-foreground))',
            fontWeight: 600,
          }}>
            Vista previa (PDF)
          </div>
          {previewUrl ? (
            <embed
              src={previewUrl}
              type="application/pdf"
              style={{ flex: 1, width: '100%', border: 'none' }}
            />
          ) : (
            <div style={{
              flex: 1,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: 'hsl(var(--muted-foreground))',
              fontSize: '0.85rem',
              flexDirection: 'column',
              gap: '0.5rem',
            }}>
              <span style={{ fontSize: '2rem' }}>📄</span>
              <span>Haz clic en "Vista previa PDF"</span>
              <span style={{ fontSize: '0.75rem', opacity: 0.7 }}>para renderizar el encabezado</span>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
