import React, { useState, useEffect } from 'react'
import HtmlTemplateEditor from './HtmlTemplateEditor'

const DEFAULT_DESIGN = {
  tabla: {
    header_bg: '#1A365D',
    accent: '#2B6CB0',
    even_bg: '#F8FAFC',
    border: '#E2E8F0',
    density: 'normal',
  },
  cierre: {
    show_uuid: true,
    show_fecha_timbrado: true,
    show_disclaimer: true,
  },
}

const TABS = [
  { id: 'caratula', label: 'Caratula' },
  { id: 'tabla', label: 'Tabla de conceptos' },
  { id: 'cierre', label: 'Cierre' },
]

export default function PdfTemplateDesigner({ templateId = 'default' }) {
  const [activeTab, setActiveTab] = useState('caratula')
  const [design, setDesign] = useState(DEFAULT_DESIGN)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [status, setStatus] = useState(null)

  useEffect(() => {
    fetch(`/api/templates/${templateId}/design`)
      .then(r => r.json())
      .then(data => {
        if (data && Object.keys(data).length > 0) {
          setDesign({
            tabla: { ...DEFAULT_DESIGN.tabla, ...(data.tabla || {}) },
            cierre: { ...DEFAULT_DESIGN.cierre, ...(data.cierre || {}) },
          })
        }
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [templateId])

  const handleSave = async () => {
    setSaving(true)
    setStatus(null)
    try {
      const res = await fetch(`/api/templates/${templateId}/design`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(design),
      })
      if (res.ok) {
        setStatus({ type: 'success', msg: 'Configuración guardada.' })
      } else {
        const d = await res.json().catch(() => ({}))
        setStatus({ type: 'error', msg: d.detail || 'Error al guardar.' })
      }
    } catch (e) {
      setStatus({ type: 'error', msg: String(e) })
    } finally {
      setSaving(false)
    }
  }

  const setTabla = (key, val) => setDesign(d => ({ ...d, tabla: { ...d.tabla, [key]: val } }))
  const setCierre = (key, val) => setDesign(d => ({ ...d, cierre: { ...d.cierre, [key]: val } }))

  if (loading) {
    return (
      <div style={{ padding: '2rem', color: 'hsl(var(--muted-foreground))' }}>
        Cargando configuración...
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Tab bar */}
      <div style={{
        display: 'flex',
        borderBottom: '1px solid hsl(var(--border))',
        background: 'hsl(var(--muted))',
        flexShrink: 0,
        padding: '0 0.75rem',
      }}>
        {TABS.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            style={{
              padding: '0.6rem 1rem',
              background: 'none',
              border: 'none',
              borderBottom: activeTab === tab.id
                ? '2px solid hsl(var(--primary))'
                : '2px solid transparent',
              cursor: 'pointer',
              fontSize: '0.85rem',
              fontWeight: activeTab === tab.id ? 600 : 400,
              color: activeTab === tab.id
                ? 'hsl(var(--primary))'
                : 'hsl(var(--muted-foreground))',
              whiteSpace: 'nowrap',
              outline: 'none',
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div style={{
        flex: 1,
        minHeight: 0,
        overflow: activeTab === 'caratula' ? 'hidden' : 'auto',
        padding: activeTab === 'caratula' ? '0.75rem' : '1.25rem',
        display: 'flex',
        flexDirection: 'column',
      }}>
        {activeTab === 'caratula' && (
          <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
            <HtmlTemplateEditor templateId={templateId} />
          </div>
        )}

        {activeTab === 'tabla' && (
          <TablaEditor
            design={design}
            setTabla={setTabla}
            onSave={handleSave}
            saving={saving}
            status={status}
          />
        )}

        {activeTab === 'cierre' && (
          <CierreEditor
            design={design}
            setCierre={setCierre}
            onSave={handleSave}
            saving={saving}
            status={status}
          />
        )}
      </div>
    </div>
  )
}

function TablaEditor({ design, setTabla, onSave, saving, status }) {
  const t = design.tabla

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '300px 1fr', gap: '1.5rem', alignItems: 'start' }}>
      {/* Controls */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
        <Section title="Colores">
          <ColorField
            label="Encabezado de tabla"
            value={t.header_bg}
            onChange={v => setTabla('header_bg', v)}
          />
          <ColorField
            label="Filas alternas"
            value={t.even_bg}
            onChange={v => setTabla('even_bg', v)}
          />
          <ColorField
            label="Bordes"
            value={t.border}
            onChange={v => setTabla('border', v)}
          />
        </Section>

        <Section title="Densidad de filas">
          {[
            { value: 'compact', label: 'Compacto', desc: '11pt — más filas por página' },
            { value: 'normal', label: 'Normal', desc: '13pt — tamaño estándar' },
            { value: 'comfortable', label: 'Cómodo', desc: '16pt — más espacio entre filas' },
          ].map(({ value, label, desc }) => (
            <label
              key={value}
              style={{ display: 'flex', alignItems: 'flex-start', gap: '0.5rem', cursor: 'pointer' }}
            >
              <input
                type="radio"
                name="density"
                value={value}
                checked={t.density === value}
                onChange={() => setTabla('density', value)}
                style={{ marginTop: 3 }}
              />
              <div>
                <div style={{ fontSize: '0.85rem', fontWeight: 500 }}>{label}</div>
                <div style={{ fontSize: '0.75rem', color: 'hsl(var(--muted-foreground))' }}>{desc}</div>
              </div>
            </label>
          ))}
        </Section>

        <SaveBar onSave={onSave} saving={saving} status={status} />
      </div>

      {/* Mini CSS preview */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
        <div style={{
          fontSize: '0.72rem',
          fontWeight: 700,
          color: 'hsl(var(--muted-foreground))',
          textTransform: 'uppercase',
          letterSpacing: '0.06em',
        }}>
          Vista previa (navegador)
        </div>
        <div style={{
          border: '1px solid hsl(var(--border))',
          borderRadius: '8px',
          overflow: 'hidden',
          boxShadow: '0 1px 4px rgba(0,0,0,0.06)',
        }}>
          <PreviewTable design={t} />
        </div>
        <div style={{ fontSize: '0.7rem', color: 'hsl(var(--muted-foreground))' }}>
          Vista aproximada — el PDF final usa tipografía y métricas distintas
        </div>
      </div>
    </div>
  )
}

function CierreEditor({ design, setCierre, onSave, saving, status }) {
  const c = design.cierre

  return (
    <div style={{ maxWidth: 480, display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
      <Section title="Elementos del cierre">
        <p style={{ fontSize: '0.8rem', color: 'hsl(var(--muted-foreground))', margin: '0 0 0.75rem' }}>
          Controla qué información aparece al final de la última página del PDF.
        </p>
        <Toggle
          label="Folio Fiscal (UUID)"
          desc="Imprime el UUID del timbre fiscal digital"
          value={c.show_uuid}
          onChange={v => setCierre('show_uuid', v)}
        />
        <Toggle
          label="Fecha de timbrado"
          desc="Incluye la fecha y número de certificado SAT"
          value={c.show_fecha_timbrado}
          onChange={v => setCierre('show_fecha_timbrado', v)}
        />
        <Toggle
          label="Leyenda de representación impresa"
          desc='"Este documento es una representación impresa de un CFDI"'
          value={c.show_disclaimer}
          onChange={v => setCierre('show_disclaimer', v)}
        />
      </Section>

      <SaveBar onSave={onSave} saving={saving} status={status} />
    </div>
  )
}

function Section({ title, children }) {
  return (
    <div>
      <div style={{
        fontSize: '0.72rem',
        fontWeight: 700,
        color: 'hsl(var(--muted-foreground))',
        textTransform: 'uppercase',
        letterSpacing: '0.06em',
        marginBottom: '0.75rem',
        paddingBottom: '0.4rem',
        borderBottom: '1px solid hsl(var(--border))',
      }}>
        {title}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.65rem' }}>
        {children}
      </div>
    </div>
  )
}

function ColorField({ label, value, onChange }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '0.5rem' }}>
      <label style={{ fontSize: '0.85rem', color: 'hsl(var(--foreground))' }}>{label}</label>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
        <input
          type="color"
          value={value}
          onChange={e => onChange(e.target.value)}
          style={{
            width: 30,
            height: 26,
            border: '1px solid hsl(var(--border))',
            borderRadius: 4,
            cursor: 'pointer',
            padding: 1,
            background: 'none',
          }}
        />
        <input
          type="text"
          value={value}
          onChange={e => onChange(e.target.value)}
          style={{
            width: 78,
            padding: '0.2rem 0.4rem',
            fontFamily: 'monospace',
            fontSize: '0.8rem',
            border: '1px solid hsl(var(--border))',
            borderRadius: 4,
            background: 'hsl(var(--card))',
            color: 'hsl(var(--foreground))',
            outline: 'none',
          }}
        />
      </div>
    </div>
  )
}

function Toggle({ label, desc, value, onChange }) {
  return (
    <div
      style={{ display: 'flex', alignItems: 'flex-start', gap: '0.75rem', cursor: 'pointer' }}
      onClick={() => onChange(!value)}
    >
      <div
        style={{
          width: 36,
          height: 20,
          borderRadius: 10,
          background: value ? 'hsl(var(--primary))' : 'hsl(var(--muted))',
          position: 'relative',
          flexShrink: 0,
          transition: 'background 0.15s',
          marginTop: 2,
          border: '1px solid hsl(var(--border))',
        }}
      >
        <div style={{
          position: 'absolute',
          top: 2,
          left: value ? 16 : 2,
          width: 14,
          height: 14,
          borderRadius: '50%',
          background: '#fff',
          transition: 'left 0.15s',
          boxShadow: '0 1px 3px rgba(0,0,0,0.2)',
        }} />
      </div>
      <div>
        <div style={{ fontSize: '0.85rem', fontWeight: 500 }}>{label}</div>
        {desc && (
          <div style={{ fontSize: '0.75rem', color: 'hsl(var(--muted-foreground))', marginTop: 1 }}>
            {desc}
          </div>
        )}
      </div>
    </div>
  )
}

function SaveBar({ onSave, saving, status }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
      <button
        onClick={onSave}
        disabled={saving}
        style={{
          padding: '0.45rem 1.2rem',
          background: 'hsl(var(--primary))',
          color: 'hsl(var(--primary-foreground))',
          border: 'none',
          borderRadius: 6,
          cursor: saving ? 'not-allowed' : 'pointer',
          fontSize: '0.85rem',
          fontWeight: 600,
          opacity: saving ? 0.7 : 1,
        }}
      >
        {saving ? 'Guardando...' : 'Guardar cambios'}
      </button>
      {status && (
        <span style={{
          fontSize: '0.8rem',
          color: status.type === 'success' ? '#276749' : '#C53030',
          padding: '0.25rem 0.5rem',
          borderRadius: 4,
          background: status.type === 'success' ? '#F0FFF4' : '#FFF5F5',
        }}>
          {status.msg}
        </span>
      )}
    </div>
  )
}

function PreviewTable({ design }) {
  const rowH = { compact: 22, normal: 28, comfortable: 36 }[design.density] || 28
  const rows = [
    { id: 'PROD-001', qty: '2.00', desc: 'Servicio de consultoría empresarial', imp: '$8,400.00' },
    { id: 'PROD-002', qty: '1.00', desc: 'Licencia anual de software', imp: '$3,200.00' },
    { id: 'PROD-003', qty: '5.00', desc: 'Capacitación al personal', imp: '$1,750.00' },
  ]

  return (
    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
      <thead>
        <tr>
          {['No.Id', 'Cant', 'Descripcion', 'Importe'].map(h => (
            <th
              key={h}
              style={{
                background: design.header_bg,
                color: '#fff',
                padding: '4px 8px',
                textAlign: 'left',
                fontWeight: 700,
                fontSize: 11,
              }}
            >
              {h}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row, i) => (
          <tr
            key={i}
            style={{
              background: i % 2 === 0 ? design.even_bg : '#fff',
              borderBottom: `1px solid ${design.border}`,
              height: rowH,
            }}
          >
            <td style={{ padding: '3px 8px', fontSize: 11 }}>{row.id}</td>
            <td style={{ padding: '3px 8px', fontSize: 11 }}>{row.qty}</td>
            <td style={{ padding: '3px 8px', fontSize: 11 }}>{row.desc}</td>
            <td style={{ padding: '3px 8px', fontSize: 11, fontWeight: 700 }}>{row.imp}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
