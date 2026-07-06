import React, { useState, useEffect, useRef, useMemo, useCallback } from 'react'

// ── Utilidades de color ────────────────────────────────────────────────────────

function hexToHsl(hex) {
  const r = parseInt(hex.slice(1, 3), 16) / 255
  const g = parseInt(hex.slice(3, 5), 16) / 255
  const b = parseInt(hex.slice(5, 7), 16) / 255
  const max = Math.max(r, g, b), min = Math.min(r, g, b)
  let h = 0, s = 0
  const l = (max + min) / 2
  if (max !== min) {
    const d = max - min
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min)
    switch (max) {
      case r: h = ((g - b) / d + (g < b ? 6 : 0)) / 6; break
      case g: h = ((b - r) / d + 2) / 6; break
      case b: h = ((r - g) / d + 4) / 6; break
    }
  }
  return [h * 360, s * 100, l * 100]
}

function hslToHex(h, s, l) {
  h /= 360; s /= 100; l /= 100
  let r, g, b
  if (s === 0) {
    r = g = b = l
  } else {
    const q = l < 0.5 ? l * (1 + s) : l + s - l * s
    const p = 2 * l - q
    const hue2rgb = (p, q, t) => {
      if (t < 0) t += 1; if (t > 1) t -= 1
      if (t < 1 / 6) return p + (q - p) * 6 * t
      if (t < 1 / 2) return q
      if (t < 2 / 3) return p + (q - p) * (2 / 3 - t) * 6
      return p
    }
    r = hue2rgb(p, q, h + 1 / 3)
    g = hue2rgb(p, q, h)
    b = hue2rgb(p, q, h - 1 / 3)
  }
  return '#' + [r, g, b].map(x => Math.round(x * 255).toString(16).padStart(2, '0')).join('')
}

function deriveColors(hex) {
  const safe = /^#[0-9a-fA-F]{6}$/.test(hex) ? hex : '#1A365D'
  try {
    const [h, s, l] = hexToHsl(safe)
    return {
      bg:      safe,
      accent:  hslToHex(h, Math.min(s + 5, 100), Math.min(l + 12, 65)),
      bgLight: hslToHex(h, Math.max(s * 0.12, 5), 97),
      border:  hslToHex(h, Math.max(s * 0.18, 5), 88),
    }
  } catch {
    return { bg: '#1A365D', accent: '#2B6CB0', bgLight: '#F8FAFC', border: '#E2E8F0' }
  }
}

// Estilo compartido de los botones del selector de plantillas (Fase 4).
function tplBtnStyle(disabled) {
  return {
    padding: '0.4rem 0.7rem',
    border: '1px solid hsl(var(--border))',
    borderRadius: 8,
    background: 'hsl(var(--card))',
    color: 'hsl(var(--foreground))',
    fontSize: '0.78rem',
    fontWeight: 600,
    cursor: disabled ? 'not-allowed' : 'pointer',
    opacity: disabled ? 0.55 : 1,
    whiteSpace: 'nowrap',
  }
}

// ── Datos de muestra para el preview ──────────────────────────────────────────

const SAMPLE = {
  // Emisor
  emisor_nombre:        'Empresa Ejemplo S.A. de C.V.',
  emisor_rfc:           'EEJ010101EEJ',
  emisor_regimen:       '601 - General de Ley Personas Morales',
  emisor_regimen_desc:  '601 - General de Ley Personas Morales',
  lugar_expedicion:     '64940',
  // Receptor
  receptor_nombre:          'Cliente Corporativo del Norte S.A.',
  receptor_rfc:             'CCN980101AAA',
  receptor_uso:             'G03 - Gastos en general',
  receptor_uso_desc:        'G03 - Gastos en general',
  receptor_regimen_desc:    '616 - Sin obligaciones fiscales',
  domicilio_fiscal_receptor: '06600',
  // Comprobante
  fecha:               '2025-01-15T10:00:00',
  serie:               'A',
  folio:               '12345',
  moneda:              'MXN',
  moneda_desc:         'MXN - Peso Mexicano',
  tipo_cambio_block:   '',
  forma_pago_desc:     '03 - Transferencia electrónica de fondos',
  metodo_pago_desc:    'PUE - Pago en una sola exhibición',
  // Totales
  total:               '11,600.00',
  subtotal:            '10,000.00',
  // Timbre
  uuid:                '550e8400-e29b-41d4-a716-446655440000',
  fecha_timbrado:      '2025-01-15T10:01:00',
  rfc_prov_certif:     'SAT970701NN3',
  sello_sat:           'abc123xyz789…',
}

function fillPreviewPlaceholders(html, data) {
  let result = html
  for (const [k, v] of Object.entries(data)) {
    result = result.split(`{{${k}}}`).join(v ?? '')
  }
  return result
}

// ── Constantes ─────────────────────────────────────────────────────────────────

const DEFAULT_DESIGN = {
  brand:  { color: '#1A365D', accent: '#2B6CB0', logo_url: '' },
  tabla:  { density: 'normal' },
  cierre: { show_uuid: true, show_fecha_timbrado: true, show_disclaimer: true },
}

const SECTIONS = [
  { id: 'header', label: 'Encabezado' },
  { id: 'table',  label: 'Tabla de productos' },
  { id: 'totals', label: 'Totales' },
]

// ── Catálogo de columnas y reglas ──────────────────────────────────────────────
//
// Nombres amigables por `field` (nunca se muestra el id técnico al usuario).
const FIELD_LABELS = {
  num_id:         'No. de identificación',
  cantidad:       'Cantidad',
  clave_unidad:   'Unidad',
  descripcion:    'Descripción',
  valor_unitario: 'Precio unitario',
  descuento:      'Descuento',
  importe:        'Importe',
}

// Catálogo canónico de las 7 columnas default. Solo se usa como FALLBACK si el
// fetch de GET /api/templates/design-defaults falla (la fuente de verdad es el
// backend — decisión D4 del contrato Fase 0).
const AVAILABLE_FIELDS = [
  { id: 'no_id',   label: 'No.Id',       field: 'num_id',         width: 60,  visible: true, order: 0, format: 'text',  color: '#4A5568', emphasis: false },
  { id: 'cant',    label: 'Cant',        field: 'cantidad',       width: 28,  visible: true, order: 1, format: 'text',  color: '#4A5568', emphasis: false },
  { id: 'unidad',  label: 'Unidad',      field: 'clave_unidad',   width: 36,  visible: true, order: 2, format: 'text',  color: '#4A5568', emphasis: false },
  { id: 'desc',    label: 'Descripcion', field: 'descripcion',    width: 175, visible: true, order: 3, format: 'text',  color: '#4A5568', emphasis: false },
  { id: 'punit',   label: 'P.Unit',      field: 'valor_unitario', width: 52,  visible: true, order: 4, format: 'money', color: '#4A5568', emphasis: false },
  { id: 'descto',  label: 'Desc',        field: 'descuento',      width: 42,  visible: true, order: 5, format: 'money', color: '#C53030', emphasis: false },
  { id: 'importe', label: 'Importe',     field: 'importe',        width: 54,  visible: true, order: 6, format: 'money', color: '#2D3748', emphasis: true  },
]

const PAGE_WIDTH_LIMIT = 523.28   // canvas_service.PW (A4 menos márgenes)
const WIDTH_WARN       = 470      // umbral ámbar del medidor
const MAX_REGLAS       = 3

const WIDTH_PRESETS = [
  { label: 'Angosta', value: 40 },
  { label: 'Media',   value: 90 },
  { label: 'Ancha',   value: 175 },
  { label: 'Extra',   value: 240 },
]

// Operadores en español. Columnas de dinero → solo comparadores; texto → +contiene.
const OPERATOR_LABELS = {
  eq:  'es igual a',
  neq: 'es distinto de',
  gt:  'es mayor que',
  lt:  'es menor que',
  gte: 'es mayor o igual que',
  lte: 'es menor o igual que',
  contains: 'contiene',
}
const NUMERIC_OPERATORS = ['eq', 'neq', 'gt', 'lt', 'gte', 'lte']
const TEXT_OPERATORS    = ['eq', 'neq', 'contains']

// Swatches rápidos de color de texto para reglas (hex que el motor ya usa).
const RULE_SWATCHES = [
  { color: '#C53030', label: 'Rojo' },
  { color: '#DD6B20', label: 'Ámbar' },
  { color: '#276749', label: 'Verde' },
  { color: '#A0AEC0', label: 'Gris' },
]

function reorder(arr, from, to) {
  if (to < 0 || to >= arr.length) return arr
  const next = arr.slice()
  const [item] = next.splice(from, 1)
  next.splice(to, 0, item)
  return next
}

function operatorsForFormat(format) {
  return format === 'money' ? NUMERIC_OPERATORS : TEXT_OPERATORS
}

function friendlyField(field, labels) {
  return (labels && labels[field]) || FIELD_LABELS[field] || field
}

// Validación en vivo de columnas (contrato Fase 0, §4.4). Espeja la validación
// server-side; "Guardar todo" y el preview se bloquean con hasError.
function computeTableValidation(columns) {
  const visible = columns.filter(c => c.visible)
  const widthSum = visible.reduce((s, c) => s + (Number(c.width) || 0), 0)
  const badWidth = columns.some(c => !(Number(c.width) > 0))
  const seen = new Set()
  const dupLabels = new Set()
  for (const c of columns) {
    const key = (c.label || '').trim().toLowerCase()
    if (!key) continue
    if (seen.has(key)) dupLabels.add(key)
    seen.add(key)
  }
  const overBy = widthSum - PAGE_WIDTH_LIMIT
  const errors = {
    over:      overBy > 1e-6,
    badWidth,
    noVisible: visible.length < 1,
    dupLabels: dupLabels.size > 0,
  }
  return {
    widthSum,
    overBy,
    visibleCount: visible.length,
    dupLabels,
    errors,
    hasError: errors.over || errors.badWidth || errors.noVisible || errors.dupLabels,
  }
}

// ── Componente principal ──────────────────────────────────────────────────────

export default function InvoiceDesigner({ templateId = 'default', onTemplateIdChange }) {
  const [activeSection,   setActiveSection]   = useState('header')
  const [brandColor,      setBrandColorRaw]   = useState('#1A365D')
  const [logoUrl,         setLogoUrlRaw]      = useState('')
  const [density,         setDensityRaw]      = useState('normal')
  const [cierre,          setCierreRaw]       = useState(DEFAULT_DESIGN.cierre)
  const [columns,         setColumnsRaw]      = useState([])
  const [reglas,          setReglasRaw]       = useState([])
  const [catalog,         setCatalog]         = useState(null)
  const [htmlTemplate,    setHtmlTemplateRaw] = useState('')
  const [showHtmlEditor,  setShowHtmlEditor]  = useState(false)
  const [dirty,           setDirty]           = useState(false)
  const [saving,          setSaving]          = useState(false)
  const [previewing,      setPreviewing]      = useState(false)
  const [previewingTable, setPreviewingTable] = useState(false)
  const [tablePdfUrl,     setTablePdfUrl]     = useState(null)
  const [tablePdfError,   setTablePdfError]   = useState(null)
  const [status,          setStatus]          = useState(null)
  const [loading,         setLoading]         = useState(true)

  // ── Fase 4: CRUD de plantillas ──────────────────────────────────────────────
  const [designs,   setDesigns]   = useState([])   // [{id, nombre, es_referencia}]
  const [nameModal, setNameModal] = useState(null)  // { mode:'new'|'duplicate', value } | null
  const [busyTpl,   setBusyTpl]   = useState(false)

  // dirty-tracking setters
  const mark = useCallback(setter => val => { setter(val); setDirty(true) }, [])
  const setBrandColor   = mark(setBrandColorRaw)
  const setLogoUrl      = mark(setLogoUrlRaw)
  const setDensity      = mark(setDensityRaw)
  const setColumns      = mark(setColumnsRaw)
  const setReglas       = mark(setReglasRaw)
  const setHtmlTemplate = mark(setHtmlTemplateRaw)
  const setCierre       = useCallback((key, val) => {
    setCierreRaw(c => ({ ...c, [key]: val }))
    setDirty(true)
  }, [])

  // Metadata Fase 4 (nombre, es_referencia) de la plantilla cargada. Se guarda en
  // un ref para reenviarla en cada PUT /design y NO perderla al guardar (el editor
  // no la muestra pero el backend la acepta como campo opcional del design config).
  const designMetaRef = useRef({})

  // Refs para debounce + descarte de respuestas viejas del preview de tabla.
  const tablePdfUrlRef    = useRef(null)
  const previewReqIdRef   = useRef(0)
  const runTablePreviewRef = useRef(null)

  // Cargar configuración al inicio
  useEffect(() => {
    Promise.all([
      fetch(`/api/templates/${templateId}/design`).then(r => r.json()),
      fetch(`/api/templates/${templateId}/html`).then(r => r.json()),
      fetch('/api/templates/design-defaults').then(r => r.ok ? r.json() : null).catch(() => null),
    ]).then(([design, htmlData, defaults]) => {
      designMetaRef.current = {
        nombre:        design.nombre,
        es_referencia: design.es_referencia,
      }
      const brand = design.brand || {}
      setBrandColorRaw(brand.color || '#1A365D')
      setLogoUrlRaw(brand.logo_url || '')
      const tabla = design.tabla || {}
      setDensityRaw(tabla.density || 'normal')
      setCierreRaw({
        show_uuid:           (design.cierre?.show_uuid           ?? true),
        show_fecha_timbrado: (design.cierre?.show_fecha_timbrado ?? true),
        show_disclaimer:     (design.cierre?.show_disclaimer     ?? true),
      })
      // Catálogo canónico del backend (fuente de verdad, D4); AVAILABLE_FIELDS es fallback.
      const defaultColumns = (defaults?.columns?.length ? defaults.columns : AVAILABLE_FIELDS)
      setCatalog(defaults || {
        columns: AVAILABLE_FIELDS, field_labels: FIELD_LABELS, page_width_limit: PAGE_WIDTH_LIMIT, max_reglas: MAX_REGLAS,
      })
      // Retrocompat (§4.2): sin tabla.columns → inicializar las 7 default → cero cambio percibido.
      setColumnsRaw(
        Array.isArray(tabla.columns) && tabla.columns.length
          ? tabla.columns.map(c => ({ ...c }))
          : defaultColumns.map(c => ({ ...c }))
      )
      setReglasRaw(Array.isArray(tabla.reglas) ? tabla.reglas.map(r => ({ ...r })) : [])
      setHtmlTemplateRaw(htmlData.html || '')
      setDirty(false)
    }).catch(() => {}).finally(() => setLoading(false))
  }, [templateId])

  const colors = useMemo(() => deriveColors(brandColor), [brandColor])

  const tableValidation = useMemo(() => computeTableValidation(columns), [columns])
  const fieldLabels = catalog?.field_labels || FIELD_LABELS

  // Arma el design_config v2 que consumen tanto handleSave como el preview real.
  // Regla clave: 0 reglas → OMITIR tabla.reglas (el backend rechaza reglas:[] con 400).
  const buildDesignConfig = useCallback(() => {
    const tabla = {
      header_bg: colors.bg,
      even_bg:   colors.bgLight,
      border:    colors.border,
      density,
      columns:   columns.map((c, i) => ({ ...c, order: i })),
    }
    // Solo reglas con valor no vacío: una regla vacía sería un borrador solo-UI.
    // (En particular "contiene" con valor "" matchearía TODAS las filas en el motor.)
    const reglasActivas = reglas.filter(r => String(r.valor ?? '').trim() !== '')
    if (reglasActivas.length) {
      tabla.reglas = reglasActivas.map(r => ({
        columna: r.columna,
        operador: r.operador,
        valor: r.valor ?? '',
        scope: r.scope || 'row',            // scope siempre explícito (D2)
        estilo: { color: r.estilo?.color || '#C53030' },
      }))
    }
    const meta = designMetaRef.current || {}
    return {
      schema_version: 2,
      // Preservar metadata Fase 4: sin esto, el PUT /design borraría el nombre.
      ...(typeof meta.nombre === 'string' && meta.nombre.trim() ? { nombre: meta.nombre } : {}),
      ...(typeof meta.es_referencia === 'boolean' ? { es_referencia: meta.es_referencia } : {}),
      brand:  { color: brandColor, accent: colors.accent, logo_url: logoUrl || null },
      tabla,
      cierre: { ...cierre },
    }
  }, [brandColor, colors, logoUrl, density, columns, reglas, cierre])

  // ── Operaciones sobre columnas ──────────────────────────────────────────────
  const moveColumn = (idx, dir) => setColumns(reorder(columns, idx, idx + dir))
  const toggleColumnVisible = idx =>
    setColumns(columns.map((c, i) => (i === idx ? { ...c, visible: !c.visible } : c)))
  const renameColumn = (idx, label) =>
    setColumns(columns.map((c, i) => (i === idx ? { ...c, label } : c)))
  const setColumnWidth = (idx, width) =>
    setColumns(columns.map((c, i) => (i === idx ? { ...c, width } : c)))
  const removeColumn = idx => {
    const col = columns[idx]
    const afectadas = reglas.filter(r => r.columna === col.field)
    if (afectadas.length) {
      const ok = window.confirm(
        `La columna "${col.label}" se usa en ${afectadas.length} ` +
        `regla${afectadas.length > 1 ? 's' : ''} de resaltado. Si la quitás, ` +
        `${afectadas.length > 1 ? 'esas reglas también se eliminan' : 'esa regla también se elimina'}. ¿Continuar?`
      )
      if (!ok) return
      setReglas(reglas.filter(r => r.columna !== col.field))
    }
    setColumns(columns.filter((_, i) => i !== idx))
  }
  const addColumn = field => {
    const src = (catalog?.columns || AVAILABLE_FIELDS).find(c => c.field === field)
    if (!src) return
    setColumns([...columns, { ...src, visible: true }])
  }

  // ── Operaciones sobre reglas ────────────────────────────────────────────────
  const addRule = () => {
    if (reglas.length >= MAX_REGLAS) return
    // Default a "importe" (caso típico del wireframe); si no existe, última columna
    // money visible; fallback a la primera columna.
    const importe = columns.find(c => c.field === 'importe')
    const lastMoney = [...columns].reverse().find(c => c.format === 'money' && c.visible)
    const target = importe || lastMoney || columns[0]
    setReglas([...reglas, {
      columna: target ? target.field : 'importe',
      operador: 'eq',
      valor: '',
      scope: 'row',                          // preselección UI (D2)
      estilo: { color: '#C53030' },
    }])
  }
  const updateRule = (idx, patch) =>
    setReglas(reglas.map((r, i) => (i === idx ? { ...r, ...patch } : r)))
  const changeRuleColumn = (idx, field) => {
    const col = columns.find(c => c.field === field)
    const patch = { columna: field }
    // money no admite 'contiene' → resetear a 'es igual a' (item 6 del contrato).
    if (col && col.format === 'money' && reglas[idx].operador === 'contains') {
      patch.operador = 'eq'
    }
    updateRule(idx, patch)
  }
  const moveRule = (idx, dir) => setReglas(reorder(reglas, idx, idx + dir))
  const removeRule = idx => setReglas(reglas.filter((_, i) => i !== idx))

  // ── Preview real de tabla: actualiza un blob URL embebido (reemplaza window.open) ──
  const runTablePreview = useCallback(async () => {
    if (!columns.length || tableValidation.hasError) return  // mantener último PDF bueno
    const reqId = ++previewReqIdRef.current
    setPreviewingTable(true)
    setTablePdfError(null)
    try {
      const res = await fetch(`/api/templates/${templateId}/table-preview`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ design_config: buildDesignConfig(), n_rows: 8, con_descuento: true }),
      })
      if (reqId !== previewReqIdRef.current) return          // llegó una respuesta más nueva
      if (!res.ok) {
        const err = await res.json().catch(() => null)
        throw new Error(err?.detail || 'Error generando la vista previa')
      }
      const blob = await res.blob()
      if (reqId !== previewReqIdRef.current) return
      const url = URL.createObjectURL(blob)
      if (tablePdfUrlRef.current) URL.revokeObjectURL(tablePdfUrlRef.current)
      tablePdfUrlRef.current = url
      setTablePdfUrl(url)
    } catch (e) {
      if (reqId === previewReqIdRef.current) setTablePdfError(String(e.message || e))
    } finally {
      if (reqId === previewReqIdRef.current) setPreviewingTable(false)
    }
  }, [templateId, columns.length, tableValidation.hasError, buildDesignConfig])
  runTablePreviewRef.current = runTablePreview

  // Debounce: regenera el preview real ante cambios de columns/reglas/density/color.
  // También dispara el preview inicial al entrar por primera vez a la sección tabla.
  useEffect(() => {
    if (loading || activeSection !== 'table' || !columns.length) return
    if (tableValidation.hasError) return
    const t = setTimeout(() => { runTablePreviewRef.current?.() }, 700)
    return () => clearTimeout(t)
  }, [loading, activeSection, columns, reglas, density, brandColor, tableValidation.hasError])

  // Revocar el blob URL al desmontar.
  useEffect(() => () => {
    if (tablePdfUrlRef.current) URL.revokeObjectURL(tablePdfUrlRef.current)
  }, [])

  // Preview HTML: mezcla datos de muestra + overrides de color en tiempo real
  const previewHtml = useMemo(() => {
    if (!htmlTemplate) return ''
    const logoBlock = logoUrl
      ? `<div class="logo-area"><img src="${logoUrl}" /></div>`
      : ''
    const filled = fillPreviewPlaceholders(htmlTemplate, {
      ...SAMPLE,
      brand_color:  colors.bg,
      brand_accent: colors.accent,
      logo_block:   logoBlock,
    })
    // Inyectar overrides CSS para que los colores de templates viejos (hardcoded)
    // también respondan al color picker sin necesidad de guardado previo
    const overrides = `
      .top-bar   { background: ${colors.bg}     !important; }
      .doc-title { color:      ${colors.bg}     !important; }
      .entity-name { color:    ${colors.bg}     !important; }
      .section-label { color:  ${colors.accent} !important; }
      .uuid-label    { color:  ${colors.accent} !important; }
    `
    return filled.replace('</style>', overrides + '\n</style>')
  }, [htmlTemplate, colors, logoUrl])

  // ── Fase 4: lista de plantillas + operaciones CRUD ──────────────────────────
  const loadDesigns = useCallback(async () => {
    try {
      const res = await fetch('/api/templates/designs')
      if (!res.ok) throw new Error('listado')
      const data = await res.json()
      setDesigns(Array.isArray(data) ? data : [])
    } catch {
      setStatus({ type: 'error', msg: 'No se pudieron cargar las plantillas.' })
    }
  }, [])

  useEffect(() => { loadDesigns() }, [loadDesigns])

  // Confirma descartar cambios sin guardar antes de navegar a otra plantilla.
  const confirmDiscardIfDirty = () =>
    !dirty || window.confirm(
      'Tenés cambios sin guardar en esta plantilla. Si continuás, se descartarán. ¿Continuar?'
    )

  const handleSelectTemplate = (id) => {
    if (id === templateId) return
    if (!confirmDiscardIfDirty()) return
    onTemplateIdChange?.(id)
  }

  const openNewModal = () => {
    if (!confirmDiscardIfDirty()) return
    setNameModal({ mode: 'new', value: '' })
  }

  const openDuplicateModal = () => {
    const active = designs.find(d => d.id === templateId)
    if (!confirmDiscardIfDirty()) return
    setNameModal({ mode: 'duplicate', value: `${active?.nombre || 'Plantilla'} (copia)` })
  }

  const submitNameModal = async () => {
    if (!nameModal) return
    const nombre = nameModal.value.trim()
    if (!nombre) return
    const isNew = nameModal.mode === 'new'
    setBusyTpl(true)
    setStatus(null)
    try {
      const res = isNew
        ? await fetch('/api/templates/designs', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ nombre, base_id: 'default' }),
          })
        : await fetch(`/api/templates/${templateId}/duplicate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ nombre }),
          })
      if (!res.ok) throw new Error('No se pudo crear la plantilla.')
      const created = await res.json()
      setNameModal(null)
      await loadDesigns()
      onTemplateIdChange?.(created.id)   // el useEffect recarga y limpia dirty
      setStatus({ type: 'success', msg: isNew ? 'Plantilla creada.' : 'Plantilla duplicada.' })
    } catch (e) {
      setStatus({ type: 'error', msg: String(e.message || e) })
    } finally {
      setBusyTpl(false)
    }
  }

  const handleDeleteTemplate = async () => {
    const active = designs.find(d => d.id === templateId)
    if (!active || templateId === 'default' || active.es_referencia) return
    const ok = window.confirm(
      `¿Eliminar la plantilla «${active.nombre}»? Esta acción no se puede deshacer.`
    )
    if (!ok) return
    setBusyTpl(true)
    setStatus(null)
    try {
      const res = await fetch(`/api/templates/${templateId}`, { method: 'DELETE' })
      if (!res.ok) throw new Error('No se pudo eliminar la plantilla.')
      onTemplateIdChange?.('default')   // volver a la predeterminada; useEffect recarga
      await loadDesigns()
      setStatus({ type: 'success', msg: 'Plantilla eliminada.' })
    } catch (e) {
      setStatus({ type: 'error', msg: String(e.message || e) })
    } finally {
      setBusyTpl(false)
    }
  }

  const handleSave = async () => {
    if (tableValidation.hasError) return   // el botón ya está deshabilitado; guarda de seguridad
    setSaving(true)
    setStatus(null)
    try {
      const designConfig = buildDesignConfig()
      const [dr, hr] = await Promise.all([
        fetch(`/api/templates/${templateId}/design`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(designConfig),
        }),
        fetch(`/api/templates/${templateId}/html`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ html: htmlTemplate }),
        }),
      ])
      if (!dr.ok || !hr.ok) throw new Error('Error al guardar')
      setDirty(false)
      setStatus({ type: 'success', msg: 'Diseño guardado. Los próximos PDFs usarán estos colores.' })
    } catch (e) {
      setStatus({ type: 'error', msg: String(e) })
    } finally {
      setSaving(false)
    }
  }

  const handlePreviewPdf = async () => {
    setPreviewing(true)
    setStatus(null)
    try {
      const logoBlock = logoUrl
        ? `<div class="logo-area"><img src="${logoUrl}" /></div>`
        : ''
      const filledForPdf = fillPreviewPlaceholders(htmlTemplate, {
        ...SAMPLE,
        brand_color:  colors.bg,
        brand_accent: colors.accent,
        logo_block:   logoBlock,
      })
      const res = await fetch(`/api/templates/${templateId}/shell-preview`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ html: filledForPdf }),
      })
      if (!res.ok) throw new Error('Error generando preview PDF')
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      window.open(url, '_blank')
      setTimeout(() => URL.revokeObjectURL(url), 60_000)
    } catch (e) {
      setStatus({ type: 'error', msg: String(e) })
    } finally {
      setPreviewing(false)
    }
  }

  // Abre el PDF de preview de tabla ya generado en una pestaña nueva (barato:
  // reusa el blob URL que mantiene runTablePreview).
  const openTablePreviewInNewTab = () => {
    if (tablePdfUrlRef.current) window.open(tablePdfUrlRef.current, '_blank')
  }

  // ── Fase 4: derivados para la UI del selector ───────────────────────────────
  const activeDesign = designs.find(d => d.id === templateId) || null
  const isReference  = !!activeDesign?.es_referencia
  const canDeleteActive = !!activeDesign && templateId !== 'default' && !isReference
  const deleteReason = templateId === 'default'
    ? 'No se puede eliminar la plantilla predeterminada.'
    : isReference
      ? 'Las plantillas de referencia no se pueden eliminar.'
      : 'Eliminar la plantilla actual.'
  // El backend devuelve nombre="default" (fallback al id) para la predeterminada;
  // la mostramos con una etiqueta amable en vez del slug.
  const displayName = d => (d.id === 'default' && d.nombre === 'default' ? 'Predeterminada' : d.nombre)

  if (loading) return (
    <div style={{ padding: '2rem', color: 'hsl(var(--muted-foreground))' }}>
      Cargando diseño...
    </div>
  )

  return (
    <div style={{
      display: 'flex', flexDirection: 'column', height: '100%',
      // Tokens locales: este componente usa hsl(var(--x)) pero cfdi_suite no
      // define esos custom properties (su index.css usa otra nomenclatura).
      // Se declaran acá y heredan a todo el subárbol (scoped, sin tocar index.css).
      '--primary':          '222 47% 24%',
      '--border':           '214 32% 91%',
      '--card':             '0 0% 100%',
      '--muted':            '210 40% 96%',
      '--foreground':       '222 47% 11%',
      '--muted-foreground': '215 16% 47%',
      '--background':       '210 40% 98%',
      background: 'hsl(var(--background))',
    }}>
      {/* Toolbar */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: '0.25rem',
        padding: '0.5rem 0.75rem',
        borderBottom: '1px solid hsl(var(--border))',
        background: 'hsl(var(--card))',
        flexShrink: 0,
      }}>
        {/* Fase 4: selector + CRUD de plantillas */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
          <select
            aria-label="Plantilla activa"
            value={templateId}
            onChange={e => handleSelectTemplate(e.target.value)}
            disabled={busyTpl}
            style={{
              padding: '0.4rem 0.6rem',
              border: '1px solid hsl(var(--border))',
              borderRadius: 8,
              background: 'hsl(var(--card))',
              color: 'hsl(var(--foreground))',
              fontSize: '0.8rem',
              fontWeight: 600,
              maxWidth: 200,
              cursor: busyTpl ? 'not-allowed' : 'pointer',
            }}
          >
            {designs.length === 0 && <option value={templateId}>{displayName({ id: templateId, nombre: templateId })}</option>}
            {designs.map(d => (
              <option key={d.id} value={d.id}>
                {displayName(d)}{d.es_referencia ? ' · Referencia' : ''}
              </option>
            ))}
          </select>

          {isReference && (
            <span
              title="Plantilla de referencia (no editable como base propia; duplicala para modificarla)."
              style={{
                fontSize: '0.66rem', fontWeight: 700, letterSpacing: '0.03em',
                textTransform: 'uppercase', padding: '0.15rem 0.4rem', borderRadius: 6,
                background: 'hsl(var(--muted))', color: 'hsl(var(--muted-foreground))',
              }}
            >
              Referencia
            </span>
          )}

          <button
            onClick={openNewModal}
            disabled={busyTpl}
            title="Crear una plantilla nueva a partir de la predeterminada."
            style={tplBtnStyle(busyTpl)}
          >
            + Nueva
          </button>
          <button
            onClick={openDuplicateModal}
            disabled={busyTpl || !activeDesign}
            title="Duplicar la plantilla actual."
            style={tplBtnStyle(busyTpl || !activeDesign)}
          >
            Duplicar
          </button>
          <button
            onClick={handleDeleteTemplate}
            disabled={busyTpl || !canDeleteActive}
            title={deleteReason}
            style={{
              ...tplBtnStyle(busyTpl || !canDeleteActive),
              color: canDeleteActive ? '#C53030' : 'hsl(var(--muted-foreground))',
            }}
          >
            Eliminar
          </button>
        </div>

        <div style={{ width: 1, height: 22, background: 'hsl(var(--border))', margin: '0 0.35rem' }} />

        {/* Section buttons */}
        {SECTIONS.map(s => (
          <button
            key={s.id}
            onClick={() => setActiveSection(s.id)}
            style={{
              padding: '0.4rem 0.9rem',
              border: 'none',
              borderRadius: 20,
              cursor: 'pointer',
              fontSize: '0.8rem',
              fontWeight: activeSection === s.id ? 700 : 500,
              background: activeSection === s.id ? colors.bg : 'hsl(var(--muted))',
              color: activeSection === s.id ? '#fff' : 'hsl(var(--foreground))',
              transition: 'all 0.15s',
            }}
          >
            {s.label}
          </button>
        ))}

        <div style={{ flex: 1 }} />

        {/* Status message */}
        {status && (
          <span style={{
            fontSize: '0.78rem',
            padding: '0.2rem 0.6rem',
            borderRadius: 6,
            background: status.type === 'success' ? '#F0FFF4' : '#FFF5F5',
            color: status.type === 'success' ? '#276749' : '#C53030',
          }}>
            {status.msg}
          </span>
        )}

        <button
          onClick={handlePreviewPdf}
          disabled={previewing}
          style={{
            padding: '0.4rem 1rem',
            border: '1px solid hsl(var(--border))',
            borderRadius: 8,
            cursor: previewing ? 'not-allowed' : 'pointer',
            fontSize: '0.8rem',
            fontWeight: 600,
            background: 'hsl(var(--card))',
            color: 'hsl(var(--foreground))',
            opacity: previewing ? 0.6 : 1,
          }}
        >
          {previewing ? 'Generando...' : 'Vista previa PDF'}
        </button>

        {tableValidation.hasError && (
          <span
            title="Corregí los errores de la tabla para poder guardar."
            style={{ fontSize: '0.72rem', color: '#C53030', maxWidth: 200, lineHeight: 1.2 }}
          >
            Hay un problema en la tabla que impide guardar.
          </span>
        )}

        <button
          onClick={handleSave}
          disabled={saving || !dirty || tableValidation.hasError}
          title={tableValidation.hasError ? 'Corregí los errores de la tabla para poder guardar.' : undefined}
          style={{
            padding: '0.4rem 1.1rem',
            border: 'none',
            borderRadius: 8,
            cursor: (saving || !dirty || tableValidation.hasError) ? 'not-allowed' : 'pointer',
            fontSize: '0.8rem',
            fontWeight: 700,
            background: (dirty && !tableValidation.hasError) ? colors.bg : 'hsl(var(--muted))',
            color: (dirty && !tableValidation.hasError) ? '#fff' : 'hsl(var(--muted-foreground))',
            opacity: saving ? 0.7 : 1,
            transition: 'all 0.15s',
          }}
        >
          {saving ? 'Guardando...' : 'Guardar todo'}
        </button>
      </div>

      {/* Main: preview (izq) + controles (der) */}
      <div style={{ display: 'grid', gridTemplateColumns: '55fr 45fr', flex: 1, minHeight: 0, overflow: 'hidden' }}>
        {/* Panel izquierdo: factura */}
        <InvoicePreview
          activeSection={activeSection}
          onSectionClick={setActiveSection}
          previewHtml={previewHtml}
          colors={colors}
          cierre={cierre}
          tablePdfUrl={tablePdfUrl}
          tablePdfError={tablePdfError}
          previewingTable={previewingTable}
          tableHasError={tableValidation.hasError}
          onOpenTableNewTab={openTablePreviewInNewTab}
        />

        {/* Panel derecho: controles */}
        <ControlsPanel
          activeSection={activeSection}
          colors={colors}
          brandColor={brandColor}
          onBrandColor={setBrandColor}
          logoUrl={logoUrl}
          onLogoUrl={setLogoUrl}
          density={density}
          onDensity={setDensity}
          cierre={cierre}
          onCierre={setCierre}
          htmlTemplate={htmlTemplate}
          onHtmlTemplate={setHtmlTemplate}
          showHtmlEditor={showHtmlEditor}
          onToggleHtmlEditor={() => setShowHtmlEditor(v => !v)}
          tableProps={{
            columns, reglas, fieldLabels, catalog,
            validation: tableValidation,
            moveColumn, toggleColumnVisible, renameColumn, setColumnWidth, removeColumn, addColumn,
            addRule, updateRule, changeRuleColumn, moveRule, removeRule,
          }}
        />
      </div>

      {/* Fase 4: mini-modal para nombrar plantilla (nueva / duplicado) */}
      {nameModal && (
        <div
          onClick={() => !busyTpl && setNameModal(null)}
          style={{
            position: 'fixed', inset: 0, zIndex: 50,
            background: 'rgba(15, 23, 42, 0.45)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}
        >
          <div
            onClick={e => e.stopPropagation()}
            style={{
              width: 380, maxWidth: '90vw',
              background: 'hsl(var(--card))',
              border: '1px solid hsl(var(--border))',
              borderRadius: 12, padding: '1.25rem',
              boxShadow: '0 10px 40px rgba(0,0,0,0.2)',
            }}
          >
            <h3 style={{ margin: '0 0 0.25rem', fontSize: '0.95rem', fontWeight: 700, color: 'hsl(var(--foreground))' }}>
              {nameModal.mode === 'new' ? 'Nueva plantilla' : 'Duplicar plantilla'}
            </h3>
            <p style={{ margin: '0 0 0.9rem', fontSize: '0.78rem', color: 'hsl(var(--muted-foreground))' }}>
              {nameModal.mode === 'new'
                ? 'Se creará a partir de la plantilla predeterminada.'
                : 'Se creará una copia de la plantilla actual.'}
            </p>
            <input
              autoFocus
              value={nameModal.value}
              onChange={e => setNameModal(m => ({ ...m, value: e.target.value }))}
              onKeyDown={e => {
                if (e.key === 'Enter') submitNameModal()
                if (e.key === 'Escape' && !busyTpl) setNameModal(null)
              }}
              placeholder="Nombre de la plantilla"
              style={{
                width: '100%', boxSizing: 'border-box',
                padding: '0.5rem 0.7rem',
                border: '1px solid hsl(var(--border))', borderRadius: 8,
                fontSize: '0.85rem', color: 'hsl(var(--foreground))',
                background: 'hsl(var(--background))',
              }}
            />
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem', marginTop: '1rem' }}>
              <button
                onClick={() => setNameModal(null)}
                disabled={busyTpl}
                style={tplBtnStyle(busyTpl)}
              >
                Cancelar
              </button>
              <button
                onClick={submitNameModal}
                disabled={busyTpl || !nameModal.value.trim()}
                style={{
                  ...tplBtnStyle(busyTpl || !nameModal.value.trim()),
                  border: 'none',
                  background: (busyTpl || !nameModal.value.trim()) ? 'hsl(var(--muted))' : colors.bg,
                  color: (busyTpl || !nameModal.value.trim()) ? 'hsl(var(--muted-foreground))' : '#fff',
                }}
              >
                {busyTpl ? 'Guardando...' : (nameModal.mode === 'new' ? 'Crear' : 'Duplicar')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Panel izquierdo: preview de factura completa ──────────────────────────────

function InvoicePreview({
  activeSection, onSectionClick, previewHtml, colors, cierre,
  tablePdfUrl, tablePdfError, previewingTable, tableHasError, onOpenTableNewTab,
}) {
  return (
    <div style={{
      overflow: 'auto',
      borderRight: '1px solid hsl(var(--border))',
      background: '#E8ECF0',
      padding: '20px',
    }}>
      {/* Sombra de "hoja de papel" */}
      <div style={{
        background: '#fff',
        borderRadius: 4,
        boxShadow: '0 2px 20px rgba(0,0,0,0.15)',
        overflow: 'hidden',
      }}>
        {/* Zona 1: Encabezado */}
        <SectionZone
          id="header"
          label="Encabezado de la factura"
          active={activeSection}
          onSelect={onSectionClick}
          accentColor={colors.bg}
        >
          <HeaderPreview html={previewHtml} />
        </SectionZone>

        {/* Zona 2: Tabla */}
        <SectionZone
          id="table"
          label="Tabla de productos"
          active={activeSection}
          onSelect={onSectionClick}
          accentColor={colors.bg}
        >
          <TablePdfPreview
            pdfUrl={tablePdfUrl}
            error={tablePdfError}
            loading={previewingTable}
            hasValidationError={tableHasError}
            onOpenNewTab={onOpenTableNewTab}
          />
        </SectionZone>

        {/* Zona 3: Totales */}
        <SectionZone
          id="totals"
          label="Totales y datos fiscales"
          active={activeSection}
          onSelect={onSectionClick}
          accentColor={colors.bg}
        >
          <TotalsPreview colors={colors} cierre={cierre} />
        </SectionZone>
      </div>
    </div>
  )
}

function SectionZone({ id, label, active, onSelect, accentColor, children }) {
  const isActive = active === id
  const [hovered, setHovered] = useState(false)

  return (
    <div
      style={{
        position: 'relative',
        cursor: 'pointer',
        outline: isActive
          ? `2px solid ${accentColor}`
          : hovered ? '2px solid rgba(0,0,0,0.15)' : '2px solid transparent',
        transition: 'outline 0.12s',
      }}
      onClick={() => onSelect(id)}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      {/* Label chip */}
      {(isActive || hovered) && (
        <div style={{
          position: 'absolute',
          top: 6,
          right: 6,
          background: isActive ? accentColor : 'rgba(0,0,0,0.45)',
          color: '#fff',
          fontSize: '10px',
          fontWeight: 700,
          padding: '2px 10px',
          borderRadius: 20,
          zIndex: 10,
          pointerEvents: 'none',
          letterSpacing: '0.02em',
          whiteSpace: 'nowrap',
        }}>
          {label}
        </div>
      )}
      {children}
    </div>
  )
}

function HeaderPreview({ html }) {
  const containerRef = useRef(null)
  const [scale, setScale] = useState(0.8)

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const update = () => setScale(Math.min((el.clientWidth - 2) / 794, 1))
    update()
    const obs = new ResizeObserver(update)
    obs.observe(el)
    return () => obs.disconnect()
  }, [])

  const iframeH = 290
  return (
    <div
      ref={containerRef}
      style={{ width: '100%', height: `${Math.round(iframeH * scale)}px`, overflow: 'hidden', lineHeight: 0 }}
    >
      <iframe
        srcDoc={html}
        title="Encabezado de factura"
        sandbox="allow-same-origin"
        style={{
          width: 794,
          height: iframeH,
          border: 'none',
          transform: `scale(${scale})`,
          transformOrigin: 'top left',
          pointerEvents: 'none',
        }}
      />
    </div>
  )
}

// Preview REAL: PDF del motor de producción embebido en un iframe (blob URL).
function TablePdfPreview({ pdfUrl, error, loading, hasValidationError, onOpenNewTab }) {
  return (
    <div style={{ position: 'relative', background: '#525659', minHeight: 640 }}>
      {pdfUrl ? (
        <iframe
          src={pdfUrl + '#toolbar=0&navpanes=0&scrollbar=0'}
          title="Vista previa real de la tabla"
          style={{ width: '100%', height: 640, border: 'none', display: 'block' }}
        />
      ) : (
        <div style={{
          height: 640, display: 'flex', alignItems: 'center', justifyContent: 'center',
          color: '#CBD5E0', fontSize: 13, textAlign: 'center', padding: 24,
        }}>
          {error
            ? <span style={{ color: '#FEB2B2' }}>No se pudo generar la vista previa: {error}</span>
            : loading
              ? 'Generando vista previa…'
              : 'La vista previa aparecerá aquí.'}
        </div>
      )}

      {/* Nota: con error de validación se conserva el último PDF bueno */}
      {hasValidationError && pdfUrl && (
        <div style={{
          position: 'absolute', top: 8, left: 8, right: 8,
          background: 'rgba(197,48,48,0.92)', color: '#fff',
          fontSize: 11, fontWeight: 600, padding: '6px 10px', borderRadius: 6,
          textAlign: 'center', pointerEvents: 'none',
        }}>
          Corregí los errores de la tabla; se muestra la última vista válida.
        </div>
      )}

      {/* Indicador de carga sobre el PDF anterior */}
      {loading && pdfUrl && (
        <div style={{
          position: 'absolute', top: 8, right: 8,
          background: 'rgba(0,0,0,0.6)', color: '#fff',
          fontSize: 10, fontWeight: 600, padding: '3px 8px', borderRadius: 12,
        }}>
          Actualizando…
        </div>
      )}

      {pdfUrl && (
        <button
          onClick={onOpenNewTab}
          style={{
            position: 'absolute', bottom: 8, right: 8,
            background: 'rgba(255,255,255,0.92)', color: '#2D3748',
            border: 'none', borderRadius: 6, padding: '4px 10px',
            fontSize: 11, fontWeight: 600, cursor: 'pointer',
          }}
        >
          Abrir en pestaña nueva
        </button>
      )}
    </div>
  )
}

function TotalsPreview({ colors, cierre }) {
  return (
    <div style={{ padding: '16px 20px', background: '#fff', fontSize: 11 }}>
      <div style={{ borderTop: `1px solid ${colors.border}`, marginBottom: 14 }} />

      {/* Totales a la derecha */}
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 5, marginBottom: 14 }}>
        <div style={{ color: '#4A5568', fontSize: 10 }}>Moneda: MXN</div>
        <div style={{ display: 'flex', gap: 60 }}>
          <span style={{ color: '#4A5568', fontSize: 11 }}>Subtotal:</span>
          <span style={{ color: '#2D3748', fontSize: 11, minWidth: 80, textAlign: 'right' }}>$10,000.00</span>
        </div>
        <div style={{ display: 'flex', gap: 60 }}>
          <span style={{ color: '#4A5568', fontSize: 11 }}>IVA 16%:</span>
          <span style={{ color: '#2D3748', fontSize: 11, minWidth: 80, textAlign: 'right' }}>$1,600.00</span>
        </div>
        {/* Total box */}
        <div style={{
          background: colors.bg,
          padding: '6px 16px',
          display: 'flex',
          gap: 40,
          alignItems: 'center',
          borderRadius: 3,
          marginTop: 4,
          minWidth: 200,
          justifyContent: 'space-between',
        }}>
          <span style={{ color: '#fff', fontWeight: 700, fontSize: 12 }}>TOTAL:</span>
          <span style={{ color: '#fff', fontWeight: 700, fontSize: 12 }}>$11,600.00</span>
        </div>
      </div>

      <div style={{ borderTop: `1px solid ${colors.border}`, marginBottom: 12 }} />

      {/* UUID */}
      {cierre.show_uuid && (
        <div style={{ marginBottom: 10 }}>
          <div style={{ fontSize: 8, fontWeight: 700, color: colors.accent, textTransform: 'uppercase', marginBottom: 3, letterSpacing: '0.05em' }}>
            Folio Fiscal (UUID)
          </div>
          <div style={{ fontFamily: 'monospace', fontSize: 9, color: '#4A5568' }}>
            550e8400-e29b-41d4-a716-446655440000
          </div>
          {cierre.show_fecha_timbrado && (
            <div style={{ fontSize: 9, color: '#718096', marginTop: 3 }}>
              Fecha Timbrado: 2025-01-15T10:01:00 &nbsp;&nbsp; No. Cert. SAT: 20001000000300022815
            </div>
          )}
        </div>
      )}

      {/* Disclaimer */}
      {cierre.show_disclaimer && (
        <div style={{
          borderTop: `1px solid ${colors.border}`,
          paddingTop: 8,
          textAlign: 'center',
          fontSize: 9,
          color: '#A0AEC0',
          fontStyle: 'italic',
        }}>
          Este documento es una representación impresa de un CFDI.
        </div>
      )}
    </div>
  )
}

// ── Panel derecho: controles contextuales ─────────────────────────────────────

function ControlsPanel({
  activeSection, colors, brandColor, onBrandColor,
  logoUrl, onLogoUrl, density, onDensity,
  cierre, onCierre, htmlTemplate, onHtmlTemplate,
  showHtmlEditor, onToggleHtmlEditor, tableProps,
}) {
  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      height: '100%',
      overflow: 'hidden',
      background: 'hsl(var(--card))',
    }}>
      {/* Header del panel */}
      <div style={{
        padding: '0.9rem 1.25rem 0.6rem',
        borderBottom: '1px solid hsl(var(--border))',
        flexShrink: 0,
      }}>
        <div style={{ fontSize: '0.72rem', fontWeight: 700, color: 'hsl(var(--muted-foreground))', textTransform: 'uppercase', letterSpacing: '0.07em' }}>
          {activeSection === 'header' && 'Encabezado de la factura'}
          {activeSection === 'table'  && 'Tabla de productos'}
          {activeSection === 'totals' && 'Totales y datos fiscales'}
        </div>
        <div style={{ fontSize: '0.78rem', color: 'hsl(var(--muted-foreground))', marginTop: 2 }}>
          {activeSection === 'header' && 'Logo, colores y datos de la empresa'}
          {activeSection === 'table'  && 'Densidad y estilo de las filas'}
          {activeSection === 'totals' && 'Qué información mostrar al pie'}
        </div>
      </div>

      {/* Controles */}
      <div style={{ flex: 1, overflow: 'auto', padding: '1.1rem 1.25rem' }}>
        {activeSection === 'header' && (
          <HeaderControls
            brandColor={brandColor}
            onBrandColor={onBrandColor}
            logoUrl={logoUrl}
            onLogoUrl={onLogoUrl}
            htmlTemplate={htmlTemplate}
            onHtmlTemplate={onHtmlTemplate}
            showHtmlEditor={showHtmlEditor}
            onToggleHtmlEditor={onToggleHtmlEditor}
          />
        )}
        {activeSection === 'table' && (
          <TableControls density={density} onDensity={onDensity} tableProps={tableProps} />
        )}
        {activeSection === 'totals' && (
          <TotalsControls cierre={cierre} onCierre={onCierre} />
        )}
      </div>
    </div>
  )
}

function HeaderControls({ brandColor, onBrandColor, logoUrl, onLogoUrl, htmlTemplate, onHtmlTemplate, showHtmlEditor, onToggleHtmlEditor }) {
  const [logoError, setLogoError] = useState(false)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.4rem' }}>
      {/* Color de marca */}
      <ControlGroup label="Color de tu empresa">
        <p style={{ fontSize: '0.75rem', color: 'hsl(var(--muted-foreground))', margin: '0 0 0.75rem' }}>
          Un solo color del que se deriva toda la paleta — encabezado, filas alternas y bordes.
        </p>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
          <input
            type="color"
            value={brandColor}
            onChange={e => onBrandColor(e.target.value)}
            style={{ width: 44, height: 38, border: '1px solid hsl(var(--border))', borderRadius: 6, cursor: 'pointer', padding: 2, background: 'none' }}
          />
          <input
            type="text"
            value={brandColor}
            onChange={e => onBrandColor(e.target.value)}
            style={{
              flex: 1,
              padding: '0.4rem 0.6rem',
              fontFamily: 'monospace',
              fontSize: '0.9rem',
              border: '1px solid hsl(var(--border))',
              borderRadius: 6,
              background: 'hsl(var(--card))',
              color: 'hsl(var(--foreground))',
              outline: 'none',
            }}
          />
          <div style={{ width: 38, height: 38, borderRadius: 6, background: brandColor, border: '1px solid hsl(var(--border))' }} />
        </div>
        {/* Paleta derivada */}
        <PaletteSwatch brandColor={brandColor} />
      </ControlGroup>

      {/* Logo */}
      <ControlGroup label="Logo de la empresa">
        <p style={{ fontSize: '0.75rem', color: 'hsl(var(--muted-foreground))', margin: '0 0 0.75rem' }}>
          URL pública de tu logo (PNG o SVG recomendado, fondo transparente).
        </p>
        <input
          type="url"
          value={logoUrl}
          onChange={e => { onLogoUrl(e.target.value); setLogoError(false) }}
          placeholder="https://tu-empresa.com/logo.png"
          style={{
            width: '100%',
            padding: '0.4rem 0.6rem',
            fontSize: '0.82rem',
            border: '1px solid hsl(var(--border))',
            borderRadius: 6,
            background: 'hsl(var(--card))',
            color: 'hsl(var(--foreground))',
            outline: 'none',
            boxSizing: 'border-box',
          }}
        />
        {logoUrl && !logoError && (
          <div style={{
            marginTop: 10,
            padding: 12,
            background: 'hsl(var(--muted))',
            borderRadius: 6,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            minHeight: 60,
          }}>
            <img
              src={logoUrl}
              alt="Logo preview"
              style={{ maxHeight: 52, maxWidth: 160, objectFit: 'contain' }}
              onError={() => setLogoError(true)}
            />
          </div>
        )}
        {logoError && (
          <p style={{ fontSize: '0.75rem', color: '#C53030', margin: '6px 0 0' }}>
            No se pudo cargar la imagen. Verifica que la URL sea pública.
          </p>
        )}
      </ControlGroup>

      {/* HTML avanzado (colapsible) */}
      <div style={{ borderTop: '1px solid hsl(var(--border))', paddingTop: '1rem' }}>
        <button
          onClick={onToggleHtmlEditor}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.4rem',
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            fontSize: '0.82rem',
            fontWeight: 600,
            color: 'hsl(var(--muted-foreground))',
            padding: 0,
            marginBottom: showHtmlEditor ? '0.75rem' : 0,
          }}
        >
          <span style={{ transform: showHtmlEditor ? 'rotate(90deg)' : 'none', display: 'inline-block', transition: 'transform 0.15s', fontSize: 11 }}>▶</span>
          {showHtmlEditor ? 'Ocultar editor HTML avanzado' : 'Editar HTML avanzado'}
        </button>
        {showHtmlEditor && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            <p style={{ fontSize: '0.72rem', color: 'hsl(var(--muted-foreground))', margin: 0 }}>
              Control total del diseño. Usa <code style={{ fontSize: '0.7rem' }}>{'{{brand_color}}'}</code> y <code style={{ fontSize: '0.7rem' }}>{'{{logo_block}}'}</code> como placeholders.
            </p>
            <textarea
              value={htmlTemplate}
              onChange={e => onHtmlTemplate(e.target.value)}
              spellCheck={false}
              style={{
                width: '100%',
                height: 320,
                resize: 'vertical',
                fontFamily: 'monospace',
                fontSize: '11px',
                lineHeight: 1.5,
                border: '1px solid hsl(var(--border))',
                borderRadius: 6,
                padding: '0.6rem',
                background: 'hsl(var(--card))',
                color: 'hsl(var(--foreground))',
                outline: 'none',
                boxSizing: 'border-box',
              }}
            />
          </div>
        )}
      </div>
    </div>
  )
}

function PaletteSwatch({ brandColor }) {
  const c = deriveColors(brandColor)
  const swatches = [
    { color: c.bg,      label: 'Principal' },
    { color: c.accent,  label: 'Acento' },
    { color: c.bgLight, label: 'Filas' },
    { color: c.border,  label: 'Bordes' },
  ]
  return (
    <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
      {swatches.map(({ color, label }) => (
        <div key={label} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
          <div style={{
            width: 32, height: 32, borderRadius: 6,
            background: color,
            border: '1px solid hsl(var(--border))',
          }} />
          <span style={{ fontSize: 9, color: 'hsl(var(--muted-foreground))', textAlign: 'center' }}>{label}</span>
        </div>
      ))}
    </div>
  )
}

function TableControls({ density, onDensity, tableProps }) {
  const opts = [
    { value: 'compact',     label: 'Compacto',  desc: 'Más filas por página (mejor para facturas largas)' },
    { value: 'normal',      label: 'Normal',    desc: 'Tamaño estándar, equilibrado' },
    { value: 'comfortable', label: 'Cómodo',    desc: 'Más espacio entre líneas, fácil de leer' },
  ]
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.4rem' }}>
      <ControlGroup label="Densidad de filas">
        <p style={{ fontSize: '0.75rem', color: 'hsl(var(--muted-foreground))', margin: '0 0 0.75rem' }}>
          Controla el espaciado de cada fila en la tabla de productos.
        </p>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
          {opts.map(({ value, label, desc }) => (
            <label
              key={value}
              style={{
                display: 'flex',
                alignItems: 'flex-start',
                gap: '0.65rem',
                cursor: 'pointer',
                padding: '0.65rem 0.8rem',
                borderRadius: 8,
                border: `1.5px solid ${density === value ? 'hsl(var(--primary))' : 'hsl(var(--border))'}`,
                background: density === value ? 'hsl(var(--primary) / 0.06)' : 'hsl(var(--card))',
                transition: 'all 0.12s',
              }}
            >
              <input
                type="radio"
                name="density"
                value={value}
                checked={density === value}
                onChange={() => onDensity(value)}
                style={{ marginTop: 2 }}
              />
              <div>
                <div style={{ fontSize: '0.85rem', fontWeight: 600, color: density === value ? 'hsl(var(--primary))' : 'hsl(var(--foreground))' }}>{label}</div>
                <div style={{ fontSize: '0.73rem', color: 'hsl(var(--muted-foreground))', marginTop: 2 }}>{desc}</div>
              </div>
            </label>
          ))}
        </div>
      </ControlGroup>

      <ColumnsEditor {...tableProps} />
      <RulesEditor {...tableProps} />
    </div>
  )
}

// ── Editor de columnas ──────────────────────────────────────────────────────────

function ColumnsEditor({
  columns, reglas, fieldLabels, catalog, validation,
  moveColumn, toggleColumnVisible, renameColumn, setColumnWidth, removeColumn, addColumn,
}) {
  const [expanded, setExpanded] = useState(null)   // índice de la columna con detalle abierto
  const [picking, setPicking]   = useState(false)

  const usedFields = new Set(columns.map(c => c.field))
  const catalogCols = catalog?.columns || AVAILABLE_FIELDS
  const availableToAdd = catalogCols.filter(c => !usedFields.has(c.field))
  const allUsed = availableToAdd.length === 0
  const onlyOneVisible = validation.visibleCount === 1

  return (
    <ControlGroup label="Columnas de la tabla">
      <p style={{ fontSize: '0.75rem', color: 'hsl(var(--muted-foreground))', margin: '0 0 0.75rem' }}>
        Mostrá, ocultá, reordená o renombrá las columnas de conceptos.
      </p>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
        {columns.map((col, idx) => (
          <ColumnRow
            key={col.id}
            col={col}
            idx={idx}
            isFirst={idx === 0}
            isLast={idx === columns.length - 1}
            expanded={expanded === idx}
            fieldLabels={fieldLabels}
            lockVisible={onlyOneVisible && col.visible}
            badWidth={!(Number(col.width) > 0)}
            dupLabel={validation.dupLabels.has((col.label || '').trim().toLowerCase())}
            onToggleExpand={() => setExpanded(expanded === idx ? null : idx)}
            onMove={dir => moveColumn(idx, dir)}
            onToggleVisible={() => toggleColumnVisible(idx)}
            onRename={label => renameColumn(idx, label)}
            onWidth={w => setColumnWidth(idx, w)}
            onRemove={() => removeColumn(idx)}
          />
        ))}
      </div>

      <SpaceMeter validation={validation} />

      {/* Agregar columna */}
      <div style={{ marginTop: '0.75rem' }}>
        {!picking ? (
          <button
            onClick={() => setPicking(true)}
            disabled={allUsed}
            title={allUsed ? 'Ya están todas las columnas disponibles.' : undefined}
            style={{
              width: '100%', padding: '0.45rem', borderRadius: 8,
              border: '1px dashed hsl(var(--border))',
              background: 'hsl(var(--card))',
              color: allUsed ? 'hsl(var(--muted-foreground))' : 'hsl(var(--foreground))',
              fontSize: '0.8rem', fontWeight: 600,
              cursor: allUsed ? 'not-allowed' : 'pointer', opacity: allUsed ? 0.6 : 1,
            }}
          >
            + Agregar columna
          </button>
        ) : (
          <div style={{
            border: '1px solid hsl(var(--border))', borderRadius: 8, padding: '0.5rem',
            display: 'flex', flexDirection: 'column', gap: '0.3rem',
          }}>
            <div style={{ fontSize: '0.72rem', color: 'hsl(var(--muted-foreground))', marginBottom: 2 }}>
              Elegí un campo para agregar:
            </div>
            {availableToAdd.map(c => (
              <button
                key={c.field}
                onClick={() => { addColumn(c.field); setPicking(false) }}
                style={{
                  textAlign: 'left', padding: '0.4rem 0.6rem', borderRadius: 6,
                  border: '1px solid hsl(var(--border))', background: 'hsl(var(--card))',
                  color: 'hsl(var(--foreground))', fontSize: '0.8rem', cursor: 'pointer',
                }}
              >
                {friendlyField(c.field, fieldLabels)}
              </button>
            ))}
            <button
              onClick={() => setPicking(false)}
              style={{
                marginTop: 2, padding: '0.3rem', border: 'none', background: 'none',
                color: 'hsl(var(--muted-foreground))', fontSize: '0.75rem', cursor: 'pointer',
              }}
            >
              Cancelar
            </button>
          </div>
        )}
      </div>
    </ControlGroup>
  )
}

function ColumnRow({
  col, isFirst, isLast, expanded, fieldLabels, lockVisible, badWidth, dupLabel,
  onToggleExpand, onMove, onToggleVisible, onRename, onWidth, onRemove,
}) {
  const chevBtn = (dir, disabled, glyph) => (
    <button
      onClick={() => !disabled && onMove(dir)}
      disabled={disabled}
      style={{
        border: 'none', background: 'none', padding: 0, lineHeight: 1,
        cursor: disabled ? 'default' : 'pointer', fontSize: 11,
        color: disabled ? 'hsl(var(--border))' : 'hsl(var(--muted-foreground))',
      }}
    >
      {glyph}
    </button>
  )

  const activePreset = WIDTH_PRESETS.find(p => p.value === Number(col.width))

  return (
    <div style={{
      border: `1px solid ${dupLabel || badWidth ? '#DD6B20' : 'hsl(var(--border))'}`,
      borderRadius: 8, background: 'hsl(var(--card))',
      opacity: col.visible ? 1 : 0.6,
    }}>
      {/* Fila compacta */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', padding: '0.4rem 0.5rem' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
          {chevBtn(-1, isFirst, '▲')}
          {chevBtn(1, isLast, '▼')}
        </div>

        {/* Pill de visibilidad */}
        <button
          onClick={() => !lockVisible && onToggleVisible()}
          disabled={lockVisible}
          title={lockVisible ? 'Debe quedar al menos una columna visible.' : (col.visible ? 'Ocultar columna' : 'Mostrar columna')}
          style={{
            width: 34, height: 19, borderRadius: 10, flexShrink: 0, position: 'relative',
            border: '1px solid hsl(var(--border))',
            background: col.visible ? 'hsl(var(--primary))' : 'hsl(var(--muted))',
            cursor: lockVisible ? 'not-allowed' : 'pointer', opacity: lockVisible ? 0.5 : 1,
          }}
        >
          <span style={{
            position: 'absolute', top: 1, left: col.visible ? 16 : 1,
            width: 15, height: 15, borderRadius: '50%', background: '#fff',
            boxShadow: '0 1px 2px rgba(0,0,0,0.25)', transition: 'left 0.15s',
          }} />
        </button>

        {/* Renombrar label */}
        <input
          type="text"
          value={col.label}
          onChange={e => onRename(e.target.value)}
          style={{
            flex: 1, minWidth: 0, padding: '0.25rem 0.4rem', fontSize: '0.8rem',
            border: '1px solid hsl(var(--border))', borderRadius: 6,
            background: 'hsl(var(--card))', color: 'hsl(var(--foreground))', outline: 'none',
          }}
        />

        {/* Nombre amigable del campo (desambigua labels cortos como "Desc") */}
        <span
          title={`Campo: ${friendlyField(col.field, fieldLabels)}`}
          style={{
            flexShrink: 0, maxWidth: 96, overflow: 'hidden', textOverflow: 'ellipsis',
            whiteSpace: 'nowrap', fontSize: '0.68rem', color: 'hsl(var(--muted-foreground))',
          }}
        >
          {friendlyField(col.field, fieldLabels)}
        </span>

        <button
          onClick={onToggleExpand}
          title="Ajustar ancho"
          style={{
            border: 'none', background: 'none', cursor: 'pointer', fontSize: 12,
            color: 'hsl(var(--muted-foreground))',
            transform: expanded ? 'rotate(90deg)' : 'none', transition: 'transform 0.15s',
          }}
        >
          ▶
        </button>

        <button
          onClick={() => !lockVisible && onRemove()}
          disabled={lockVisible}
          title={lockVisible ? 'No podés quitar la última columna visible.' : 'Quitar columna'}
          style={{
            border: 'none', background: 'none', fontSize: 14, lineHeight: 1,
            color: lockVisible ? 'hsl(var(--border))' : '#C53030',
            cursor: lockVisible ? 'not-allowed' : 'pointer',
          }}
        >
          ✕
        </button>
      </div>

      {/* Avisos por columna */}
      {(dupLabel || badWidth) && (
        <div style={{ padding: '0 0.5rem 0.35rem', fontSize: '0.7rem', color: '#DD6B20' }}>
          {badWidth ? 'El ancho debe ser mayor a 0.' : 'Hay otra columna con este mismo nombre.'}
        </div>
      )}

      {/* Detalle expandido: ancho */}
      {expanded && (
        <div style={{ padding: '0 0.5rem 0.55rem', display: 'flex', flexDirection: 'column', gap: '0.45rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', flexWrap: 'wrap' }}>
            <span style={{ fontSize: '0.72rem', color: 'hsl(var(--muted-foreground))' }}>Ancho:</span>
            {WIDTH_PRESETS.map(p => (
              <button
                key={p.label}
                onClick={() => onWidth(p.value)}
                style={{
                  padding: '0.2rem 0.5rem', borderRadius: 6, fontSize: '0.72rem', cursor: 'pointer',
                  border: `1px solid ${activePreset?.value === p.value ? 'hsl(var(--primary))' : 'hsl(var(--border))'}`,
                  background: activePreset?.value === p.value ? 'hsl(var(--primary) / 0.08)' : 'hsl(var(--card))',
                  color: activePreset?.value === p.value ? 'hsl(var(--primary))' : 'hsl(var(--foreground))',
                  fontWeight: activePreset?.value === p.value ? 700 : 500,
                }}
              >
                {p.label}
              </button>
            ))}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
            <span style={{
              fontSize: '0.72rem',
              color: activePreset ? 'hsl(var(--muted-foreground))' : 'hsl(var(--primary))',
              fontWeight: activePreset ? 500 : 700,
            }}>
              Personalizado:
            </span>
            <input
              type="number"
              min={1}
              value={col.width}
              onChange={e => onWidth(e.target.value === '' ? '' : Number(e.target.value))}
              style={{
                width: 70, padding: '0.2rem 0.4rem', fontSize: '0.78rem',
                border: `1px solid ${badWidth ? '#C53030' : 'hsl(var(--border))'}`,
                borderRadius: 6, background: 'hsl(var(--card))', color: 'hsl(var(--foreground))', outline: 'none',
              }}
            />
            <span style={{ fontSize: '0.72rem', color: 'hsl(var(--muted-foreground))' }}>pt</span>
          </div>
          <div style={{ fontSize: '0.7rem', color: 'hsl(var(--muted-foreground))' }}>
            Campo: <strong>{friendlyField(col.field, fieldLabels)}</strong>
          </div>
        </div>
      )}
    </div>
  )
}

function SpaceMeter({ validation }) {
  const { widthSum, overBy, errors } = validation
  const pct = Math.min(widthSum / PAGE_WIDTH_LIMIT, 1) * 100
  const color = errors.over ? '#C53030' : widthSum > WIDTH_WARN ? '#DD6B20' : '#38A169'
  return (
    <div style={{ marginTop: '0.65rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.72rem', marginBottom: 3 }}>
        <span style={{ color: 'hsl(var(--muted-foreground))' }}>Espacio usado</span>
        <span style={{ color, fontWeight: 600 }}>{widthSum.toFixed(0)} / {PAGE_WIDTH_LIMIT.toFixed(0)} pt</span>
      </div>
      <div style={{ height: 6, borderRadius: 3, background: 'hsl(var(--muted))', overflow: 'hidden' }}>
        <div style={{ width: `${pct}%`, height: '100%', background: color, transition: 'width 0.15s' }} />
      </div>
      {errors.over && (
        <div style={{ fontSize: '0.72rem', color: '#C53030', marginTop: 4 }}>
          Las columnas superan el ancho de página por {overBy.toFixed(0)}pt. Reducí algún ancho o escondé una columna.
        </div>
      )}
    </div>
  )
}

// ── Editor de reglas de resaltado ───────────────────────────────────────────────

function RulesEditor({
  columns, reglas, fieldLabels,
  addRule, updateRule, changeRuleColumn, moveRule, removeRule,
}) {
  const noColumns = columns.length === 0
  const atMax = reglas.length >= MAX_REGLAS

  return (
    <ControlGroup label="Reglas de resaltado">
      <p style={{ fontSize: '0.75rem', color: 'hsl(var(--muted-foreground))', margin: '0 0 0.75rem' }}>
        Pintá de un color los datos que cumplan una condición (por ejemplo, resaltar los descuentos).
      </p>

      {noColumns ? (
        <div style={{
          padding: '0.7rem', borderRadius: 8, border: '1px dashed hsl(var(--border))',
          fontSize: '0.78rem', color: 'hsl(var(--muted-foreground))', textAlign: 'center',
        }}>
          Agregá columnas primero.
        </div>
      ) : (
        <>
          {reglas.length > 1 && (
            <div style={{ fontSize: '0.72rem', color: 'hsl(var(--muted-foreground))', marginBottom: '0.5rem' }}>
              Si dos reglas afectan la misma celda, gana la de más arriba.
            </div>
          )}

          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
            {reglas.map((rule, idx) => (
              <RuleRow
                key={idx}
                rule={rule}
                idx={idx}
                isFirst={idx === 0}
                isLast={idx === reglas.length - 1}
                columns={columns}
                fieldLabels={fieldLabels}
                onMove={dir => moveRule(idx, dir)}
                onColumn={field => changeRuleColumn(idx, field)}
                onUpdate={patch => updateRule(idx, patch)}
                onRemove={() => removeRule(idx)}
              />
            ))}
          </div>

          <button
            onClick={addRule}
            disabled={atMax}
            title={atMax ? 'Máximo 3 reglas' : undefined}
            style={{
              marginTop: '0.75rem', width: '100%', padding: '0.45rem', borderRadius: 8,
              border: '1px dashed hsl(var(--border))', background: 'hsl(var(--card))',
              color: atMax ? 'hsl(var(--muted-foreground))' : 'hsl(var(--foreground))',
              fontSize: '0.8rem', fontWeight: 600,
              cursor: atMax ? 'not-allowed' : 'pointer', opacity: atMax ? 0.6 : 1,
            }}
          >
            {atMax ? 'Máximo 3 reglas' : '+ Agregar regla'}
          </button>
        </>
      )}
    </ControlGroup>
  )
}

function RuleRow({ rule, idx, isFirst, isLast, columns, fieldLabels, onMove, onColumn, onUpdate, onRemove }) {
  const refCol = columns.find(c => c.field === rule.columna)
  const ops = operatorsForFormat(refCol?.format)
  const hiddenCellWarning = rule.scope === 'cell' && refCol && !refCol.visible
  const valueEmpty = !String(rule.valor ?? '').trim()

  const selStyle = {
    padding: '0.25rem 0.4rem', fontSize: '0.78rem', borderRadius: 6,
    border: '1px solid hsl(var(--border))', background: 'hsl(var(--card))',
    color: 'hsl(var(--foreground))', outline: 'none',
  }

  const chevBtn = (dir, disabled, glyph) => (
    <button
      onClick={() => !disabled && onMove(dir)}
      disabled={disabled}
      style={{
        border: 'none', background: 'none', padding: 0, lineHeight: 1,
        cursor: disabled ? 'default' : 'pointer', fontSize: 11,
        color: disabled ? 'hsl(var(--border))' : 'hsl(var(--muted-foreground))',
      }}
    >
      {glyph}
    </button>
  )

  return (
    <div style={{ border: '1px solid hsl(var(--border))', borderRadius: 8, padding: '0.5rem', background: 'hsl(var(--card))' }}>
      {/* Renglón 1: número + condición */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
          {chevBtn(-1, isFirst, '▲')}
          {chevBtn(1, isLast, '▼')}
        </div>
        <span style={{
          width: 18, height: 18, borderRadius: '50%', flexShrink: 0,
          background: 'hsl(var(--muted))', color: 'hsl(var(--foreground))',
          fontSize: 10, fontWeight: 700, display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          {idx + 1}
        </span>
        <span style={{ fontSize: '0.78rem', color: 'hsl(var(--muted-foreground))' }}>Si</span>
        <select value={rule.columna} onChange={e => onColumn(e.target.value)} style={selStyle}>
          {columns.map(c => (
            <option key={c.id} value={c.field}>{c.label || friendlyField(c.field, fieldLabels)}</option>
          ))}
        </select>
        <select value={rule.operador} onChange={e => onUpdate({ operador: e.target.value })} style={selStyle}>
          {ops.map(op => <option key={op} value={op}>{OPERATOR_LABELS[op]}</option>)}
        </select>
        <input
          type="text"
          value={rule.valor ?? ''}
          onChange={e => onUpdate({ valor: e.target.value })}
          placeholder="valor"
          style={{ ...selStyle, width: 72 }}
        />
        <div style={{ flex: 1 }} />
        <button
          onClick={onRemove}
          title="Quitar regla"
          style={{ border: 'none', background: 'none', fontSize: 14, color: '#C53030', cursor: 'pointer' }}
        >
          ✕
        </button>
      </div>

      {valueEmpty && (
        <div style={{ fontSize: '0.7rem', color: 'hsl(var(--muted-foreground))', margin: '0.3rem 0 0 1.5rem' }}>
          Escribí un valor para que la regla se aplique.
        </div>
      )}
      {hiddenCellWarning && (
        <div style={{ fontSize: '0.7rem', color: '#DD6B20', margin: '0.3rem 0 0 1.5rem' }}>
          La columna de esta regla está oculta.
        </div>
      )}

      {/* Renglón 2: alcance */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', margin: '0.5rem 0 0 1.5rem', flexWrap: 'wrap' }}>
        <span style={{ fontSize: '0.75rem', color: 'hsl(var(--muted-foreground))' }}>Resaltar:</span>
        <label style={{ display: 'flex', alignItems: 'center', gap: '0.3rem', fontSize: '0.76rem', cursor: 'pointer' }}>
          <input type="radio" checked={rule.scope === 'cell'} onChange={() => onUpdate({ scope: 'cell' })} />
          solo esa celda
        </label>
        <label style={{ display: 'flex', alignItems: 'center', gap: '0.3rem', fontSize: '0.76rem', cursor: 'pointer' }}>
          <input type="radio" checked={rule.scope === 'row'} onChange={() => onUpdate({ scope: 'row' })} />
          todo el renglón
        </label>
      </div>
      <div style={{ fontSize: '0.68rem', color: 'hsl(var(--muted-foreground))', margin: '0.2rem 0 0 1.5rem' }}>
        “Todo el renglón” pinta la fila completa; “solo esa celda” pinta únicamente el dato de la columna elegida.
      </div>

      {/* Renglón 3: color */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', margin: '0.5rem 0 0 1.5rem', flexWrap: 'wrap' }}>
        <span style={{ fontSize: '0.75rem', color: 'hsl(var(--muted-foreground))' }}>Color:</span>
        <input
          type="color"
          value={rule.estilo?.color || '#C53030'}
          onChange={e => onUpdate({ estilo: { color: e.target.value } })}
          style={{ width: 30, height: 26, border: '1px solid hsl(var(--border))', borderRadius: 5, cursor: 'pointer', padding: 1, background: 'none' }}
        />
        {RULE_SWATCHES.map(s => (
          <button
            key={s.color}
            onClick={() => onUpdate({ estilo: { color: s.color } })}
            title={s.label}
            style={{
              width: 22, height: 22, borderRadius: '50%', cursor: 'pointer',
              background: s.color,
              border: (rule.estilo?.color || '').toLowerCase() === s.color.toLowerCase()
                ? '2px solid hsl(var(--foreground))' : '1px solid hsl(var(--border))',
            }}
          />
        ))}
      </div>
    </div>
  )
}

function TotalsControls({ cierre, onCierre }) {
  const items = [
    {
      key: 'show_uuid',
      label: 'Folio Fiscal (UUID)',
      desc: 'Imprime el identificador único del timbre fiscal digital',
    },
    {
      key: 'show_fecha_timbrado',
      label: 'Fecha de timbrado',
      desc: 'Muestra la fecha y el número de certificado SAT',
    },
    {
      key: 'show_disclaimer',
      label: 'Leyenda de representación impresa',
      desc: '"Este documento es una representación impresa de un CFDI"',
    },
  ]

  return (
    <ControlGroup label="Elementos del pie">
      <p style={{ fontSize: '0.75rem', color: 'hsl(var(--muted-foreground))', margin: '0 0 0.75rem' }}>
        Selecciona qué información aparece al final de la última página del PDF.
      </p>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
        {items.map(({ key, label, desc }) => (
          <ToggleRow
            key={key}
            label={label}
            desc={desc}
            value={cierre[key]}
            onChange={v => onCierre(key, v)}
          />
        ))}
      </div>
    </ControlGroup>
  )
}

// ── Micro-componentes ─────────────────────────────────────────────────────────

function ControlGroup({ label, children }) {
  return (
    <div>
      <div style={{
        fontSize: '0.72rem',
        fontWeight: 700,
        color: 'hsl(var(--muted-foreground))',
        textTransform: 'uppercase',
        letterSpacing: '0.07em',
        marginBottom: '0.65rem',
        paddingBottom: '0.35rem',
        borderBottom: '1px solid hsl(var(--border))',
      }}>
        {label}
      </div>
      {children}
    </div>
  )
}

function ToggleRow({ label, desc, value, onChange }) {
  return (
    <div
      style={{ display: 'flex', alignItems: 'flex-start', gap: '0.75rem', cursor: 'pointer' }}
      onClick={() => onChange(!value)}
    >
      {/* Toggle pill */}
      <div style={{
        width: 38,
        height: 21,
        borderRadius: 11,
        background: value ? 'hsl(var(--primary))' : 'hsl(var(--muted))',
        position: 'relative',
        flexShrink: 0,
        marginTop: 1,
        transition: 'background 0.15s',
        border: '1px solid hsl(var(--border))',
      }}>
        <div style={{
          position: 'absolute',
          top: 2,
          left: value ? 18 : 2,
          width: 15,
          height: 15,
          borderRadius: '50%',
          background: '#fff',
          boxShadow: '0 1px 3px rgba(0,0,0,0.25)',
          transition: 'left 0.15s',
        }} />
      </div>
      <div>
        <div style={{ fontSize: '0.85rem', fontWeight: 500, color: 'hsl(var(--foreground))' }}>{label}</div>
        {desc && <div style={{ fontSize: '0.73rem', color: 'hsl(var(--muted-foreground))', marginTop: 2 }}>{desc}</div>}
      </div>
    </div>
  )
}
