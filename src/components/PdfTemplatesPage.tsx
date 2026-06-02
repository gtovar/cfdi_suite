import clsx from 'clsx';
import { type ChangeEvent, useCallback, useEffect, useRef, useState } from 'react';
import { GripVertical, RefreshCw, Upload } from 'lucide-react';
import {
  DndContext,
  closestCenter,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core';
import {
  SortableContext,
  verticalListSortingStrategy,
  useSortable,
  arrayMove,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { type TemplateConfig, DEFAULT_TEMPLATE } from './PdfTemplateBuilder';
import type { ZoneConfig } from './PdfTemplateBuilder';

const ZONE_LABELS: Record<string, string> = {
  header:    'Encabezado',
  emisor:    'Emisor',
  receptor:  'Receptor',
  conceptos: 'Conceptos',
  impuestos: 'Impuestos',
  timbre:    'Timbre + QR',
  footer:    'Pie de página',
};

const ZONE_COLORS: Record<string, string> = {
  header:    'bg-blue-500',
  emisor:    'bg-indigo-400',
  receptor:  'bg-violet-400',
  conceptos: 'bg-emerald-500',
  impuestos: 'bg-amber-400',
  timbre:    'bg-rose-400',
  footer:    'bg-gray-400',
};

const ALL_COLUMNS = [
  { id: '#',                label: '#' },
  { id: 'ClaveProdServ',    label: 'Clave Prod/Serv' },
  { id: 'NoIdentificacion', label: 'No. Identificación' },
  { id: 'Descripcion',      label: 'Descripción' },
  { id: 'ClaveUnidad',      label: 'Unidad de Medida' },
  { id: 'Cantidad',         label: 'Cantidad' },
  { id: 'ValorUnitario',    label: 'Precio Unitario' },
  { id: 'Importe',          label: 'Importe' },
  { id: 'Descuento',        label: 'Descuento' },
];

// ── Merges saved template with defaults for new fields (localStorage compat) ──
function withDefaults(t: Partial<TemplateConfig>): TemplateConfig {
  return { ...DEFAULT_TEMPLATE, ...t };
}

interface Props {
  sourceFile: File | null;
  savedTemplate: TemplateConfig;
  onSave: (template: TemplateConfig) => void;
}

// ── Sortable zone row ──────────────────────────────────────────────────────────

interface SortableZoneProps {
  key?: string;  // React JSX key compat (no @types/react installed)
  zone: ZoneConfig;
  isSelected: boolean;
  onSelect: () => void;
  onToggleVisible: () => void;
  onHeaderResizeStart: (e: PointerEvent) => void;
}

function SortableZone({ zone, isSelected, onSelect, onToggleVisible, onHeaderResizeStart }: SortableZoneProps) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: zone.id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };

  const colorBar = ZONE_COLORS[zone.id] ?? 'bg-gray-400';

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={clsx(
        'group relative rounded-lg border transition-all cursor-pointer select-none',
        isSelected
          ? 'border-blue-400 bg-blue-50 shadow-sm'
          : 'border-gray-200 bg-white hover:border-gray-300',
        !zone.visible && 'opacity-50',
      )}
      onClick={onSelect}
    >
      <div className="flex items-center gap-1.5 px-2 py-2">
        {/* Drag handle */}
        <button
          className="shrink-0 cursor-grab touch-none text-gray-300 hover:text-gray-500 active:cursor-grabbing"
          {...attributes}
          {...listeners}
          onClick={(e) => e.stopPropagation()}
          aria-label="Arrastrar para reordenar"
        >
          <GripVertical size={13} />
        </button>

        {/* Color indicator */}
        <span className={clsx('h-2.5 w-1 shrink-0 rounded-full', colorBar)} />

        {/* Label */}
        <span className={clsx(
          'flex-1 text-xs font-medium leading-tight',
          zone.visible ? 'text-gray-800' : 'text-gray-400 line-through',
        )}>
          {ZONE_LABELS[zone.id] ?? zone.id}
        </span>

        {/* Height badge for header */}
        {zone.id === 'header' && (
          <span className="shrink-0 rounded bg-gray-100 px-1 py-0.5 font-mono text-[9px] text-gray-500">
            h
          </span>
        )}

        {/* Visibility toggle */}
        <button
          onClick={(e) => { e.stopPropagation(); onToggleVisible(); }}
          className={clsx(
            'relative h-3.5 w-6 shrink-0 rounded-full transition-colors',
            zone.visible ? 'bg-blue-500' : 'bg-gray-200',
          )}
          aria-label={zone.visible ? 'Ocultar sección' : 'Mostrar sección'}
        >
          <span className={clsx(
            'absolute top-0.5 h-2.5 w-2.5 rounded-full bg-white shadow transition-transform',
            zone.visible ? 'left-3' : 'left-0.5',
          )} />
        </button>
      </div>

      {/* Header resize handle */}
      {zone.id === 'header' && (
        <div
          className="absolute bottom-0 left-0 right-0 h-1.5 cursor-ns-resize rounded-b-lg bg-transparent hover:bg-blue-200/60 transition-colors"
          onPointerDown={(e) => { e.stopPropagation(); onHeaderResizeStart(e); }}
          title="Arrastrar para ajustar altura del encabezado"
        />
      )}
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────

export default function PdfTemplatesPage({ sourceFile, savedTemplate, onSave }: Props) {
  const [template, setTemplate] = useState<TemplateConfig>(() => withDefaults(savedTemplate));
  const [selectedZone, setSelectedZone] = useState<string | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Header resize state
  const resizingRef = useRef(false);
  const resizeStartY = useRef(0);
  const resizeStartH = useRef(0);

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }));

  const fetchPreview = useCallback(async (tpl: TemplateConfig) => {
    if (!sourceFile) return;
    if (abortRef.current) abortRef.current.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setPreviewLoading(true);
    setPreviewError(null);
    try {
      const form = new FormData();
      form.append('file', sourceFile);
      form.append('template', JSON.stringify(tpl));
      const res = await fetch('/api/cfdi/pdf/preview', { method: 'POST', body: form, signal: ctrl.signal });
      if (!res.ok) throw new Error(`Error del servidor: HTTP ${res.status}`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      setPreviewUrl((prev) => { if (prev) URL.revokeObjectURL(prev); return url; });
    } catch (err) {
      if ((err as Error).name === 'AbortError') return;
      setPreviewError(err instanceof Error ? err.message : 'Error generando preview');
    } finally {
      setPreviewLoading(false);
    }
  }, [sourceFile]);

  const schedulePreview = useCallback((tpl: TemplateConfig) => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => fetchPreview(tpl), 400);
  }, [fetchPreview]);

  useEffect(() => {
    if (sourceFile) fetchPreview(template);
    return () => {
      if (abortRef.current) abortRef.current.abort();
      if (debounceRef.current) clearTimeout(debounceRef.current);
      setPreviewUrl((prev) => { if (prev) URL.revokeObjectURL(prev); return null; });
    };
  }, [sourceFile]); // eslint-disable-line react-hooks/exhaustive-deps

  function updateTemplate(patch: Partial<TemplateConfig>) {
    setTemplate((prev) => {
      const next = { ...prev, ...patch };
      schedulePreview(next);
      return next;
    });
    setSaved(false);
  }

  function updateZone(id: string, patch: Partial<ZoneConfig>) {
    setTemplate((prev) => {
      const zones = prev.zones.map((z) => z.id === id ? { ...z, ...patch } : z);
      const next = { ...prev, zones };
      schedulePreview(next);
      return next;
    });
    setSaved(false);
  }

  function toggleColumn(col: string) {
    setTemplate((prev) => {
      const zones = prev.zones.map((z) => {
        if (z.id !== 'conceptos') return z;
        const cols = z.columns.includes(col)
          ? z.columns.filter((c) => c !== col)
          : [...z.columns, col];
        return { ...z, columns: cols };
      });
      const next = { ...prev, zones };
      schedulePreview(next);
      return next;
    });
    setSaved(false);
  }

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    setTemplate((prev) => {
      const sorted = [...prev.zones].sort((a, b) => a.order - b.order);
      const oldIdx = sorted.findIndex((z) => z.id === active.id);
      const newIdx = sorted.findIndex((z) => z.id === over.id);
      const reordered = arrayMove(sorted, oldIdx, newIdx);
      const zones = reordered.map((z, i) => ({ ...z, order: i + 1 }));
      const next = { ...prev, zones };
      schedulePreview(next);
      return next;
    });
    setSaved(false);
  }

  // Header height resize via pointer drag
  function handleHeaderResizeStart(e: PointerEvent) {
    e.preventDefault();
    resizingRef.current = true;
    resizeStartY.current = e.clientY;
    resizeStartH.current = template.header_height;

    function onMove(ev: PointerEvent) {
      if (!resizingRef.current) return;
      const delta = ev.clientY - resizeStartY.current;
      const newH = Math.max(32, Math.min(120, resizeStartH.current + delta));
      setTemplate((prev) => ({ ...prev, header_height: Math.round(newH) }));
      setSaved(false);
    }

    function onUp() {
      resizingRef.current = false;
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      setTemplate((prev) => { schedulePreview(prev); return prev; });
    }

    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  }

  function handleLogoUpload(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => updateTemplate({ logo_url: ev.target?.result as string });
    reader.readAsDataURL(file);
    e.target.value = '';
  }

  function handleSave() {
    localStorage.setItem('cfdi-pdf-template', JSON.stringify(template));
    onSave(template);
    setSaved(true);
  }

  function exportJson() {
    const blob = new Blob([JSON.stringify(template, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'template.json';
    a.click();
    URL.revokeObjectURL(url);
  }

  function importJson(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      try {
        const parsed = JSON.parse(ev.target?.result as string) as Partial<TemplateConfig>;
        const merged = withDefaults(parsed);
        setTemplate(merged);
        schedulePreview(merged);
        setSaved(false);
      } catch { /* invalid JSON */ }
    };
    reader.readAsText(file);
    e.target.value = '';
  }

  const sortedZones = [...template.zones].sort((a, b) => a.order - b.order);
  const conceptosZone = template.zones.find((z) => z.id === 'conceptos');
  const selectedZoneData = selectedZone ? template.zones.find((z) => z.id === selectedZone) : null;

  return (
    <div className="flex flex-1 min-h-0 overflow-hidden">
      {/* Left panel: config */}
      <div className="flex w-[280px] shrink-0 flex-col overflow-y-auto border-r border-gray-200 bg-gray-50">

        {/* Page title */}
        <div className="border-b border-gray-200 px-4 py-3">
          <h2 className="text-sm font-semibold text-gray-900">Templates PDF</h2>
          <p className="text-xs text-gray-400 mt-0.5">Configura una vez, descarga directo con ⚡ PDF Pro.</p>
        </div>

        {/* Brand */}
        <div className="border-b border-gray-200 p-4">
          <p className="mb-3 text-[10px] font-semibold uppercase tracking-wider text-gray-500">Marca</p>

          <label className="mb-1.5 block text-xs font-medium text-gray-700">Logo de empresa</label>
          {template.logo_url && (
            <div className="mb-2 flex items-center gap-2">
              <img
                src={template.logo_url}
                alt="Logo"
                className="h-10 max-w-[130px] rounded border border-gray-200 object-contain p-1"
              />
              <button
                onClick={() => updateTemplate({ logo_url: null })}
                className="text-xs text-red-500 hover:text-red-700"
              >quitar</button>
            </div>
          )}
          <label className="flex cursor-pointer items-center gap-1.5 rounded-lg border border-dashed border-gray-300 px-3 py-2 text-xs text-gray-500 transition-colors hover:border-blue-400 hover:text-blue-500">
            <Upload size={12} />
            Subir imagen (PNG, JPG, SVG)
            <input type="file" accept="image/*" onChange={handleLogoUpload} className="hidden" />
          </label>

          <label className="mb-1.5 mt-4 block text-xs font-medium text-gray-700">Pie de página</label>
          <input
            type="text"
            value={template.footer_note}
            onChange={(e) => updateTemplate({ footer_note: e.target.value })}
            placeholder="Texto opcional al final del documento..."
            className="w-full rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-xs text-gray-700 placeholder-gray-400 focus:outline-none focus:ring-1 focus:ring-blue-400"
          />
        </div>

        {/* Tipografía */}
        <div className="border-b border-gray-200 p-4">
          <p className="mb-3 text-[10px] font-semibold uppercase tracking-wider text-gray-500">Tipografía</p>
          <label className="mb-1.5 block text-xs font-medium text-gray-700">Fuente del documento</label>
          <div className="flex rounded-lg border border-gray-200 overflow-hidden">
            {([
              { value: 'helvetica', label: 'Helvetica', style: { fontFamily: 'Helvetica, Arial, sans-serif' } },
              { value: 'times',     label: 'Times',     style: { fontFamily: 'Times New Roman, serif' } },
              { value: 'courier',   label: 'Courier',   style: { fontFamily: 'Courier New, monospace' } },
            ] as const).map(opt => (
              <button
                key={opt.value}
                onClick={() => updateTemplate({ font_family: opt.value })}
                style={opt.style}
                className={clsx('flex-1 px-2 py-1.5 text-xs transition-colors',
                  template.font_family === opt.value
                    ? 'bg-blue-600 text-white font-semibold'
                    : 'text-gray-600 hover:bg-gray-50 bg-white')}
              >{opt.label}</button>
            ))}
          </div>

          <label className="mb-1.5 mt-4 block text-xs font-medium text-gray-700">Layout del encabezado</label>
          <div className="flex rounded-lg border border-gray-200 overflow-hidden">
            {([
              { value: 'logo-left',   label: 'Logo izq.' },
              { value: 'logo-center', label: 'Logo centro' },
              { value: 'text-only',   label: 'Sin logo' },
            ] as const).map(opt => (
              <button
                key={opt.value}
                onClick={() => updateTemplate({ header_layout: opt.value })}
                className={clsx('flex-1 px-2 py-1.5 text-xs transition-colors',
                  template.header_layout === opt.value
                    ? 'bg-blue-600 text-white font-medium'
                    : 'text-gray-600 hover:bg-gray-50 bg-white')}
              >{opt.label}</button>
            ))}
          </div>
        </div>

        {/* Colores */}
        <div className="border-b border-gray-200 p-4">
          <p className="mb-3 text-[10px] font-semibold uppercase tracking-wider text-gray-500">Colores</p>

          <label className="mb-1.5 block text-xs font-medium text-gray-700">Color principal</label>
          <p className="mb-1.5 text-[10px] text-gray-400">Header del documento y totales</p>
          <div className="flex items-center gap-2">
            <input type="color" value={template.primary_color}
              onChange={(e) => updateTemplate({ primary_color: e.target.value })}
              className="h-8 w-12 cursor-pointer rounded border border-gray-200 bg-white p-0.5" />
            <input type="text" value={template.primary_color}
              onChange={(e) => { if (/^#[0-9a-fA-F]{0,6}$/.test(e.target.value)) updateTemplate({ primary_color: e.target.value }); }}
              className="flex-1 rounded border border-gray-200 bg-white px-2 py-1 font-mono text-xs text-gray-700 focus:outline-none focus:ring-1 focus:ring-blue-400" />
          </div>

          <label className="mb-1.5 mt-4 block text-xs font-medium text-gray-700">Color de acento</label>
          <p className="mb-1.5 text-[10px] text-gray-400">Cabeceras de tabla y secciones</p>
          <div className="flex items-center gap-2">
            <input type="color" value={template.accent_color}
              onChange={(e) => updateTemplate({ accent_color: e.target.value })}
              className="h-8 w-12 cursor-pointer rounded border border-gray-200 bg-white p-0.5" />
            <input type="text" value={template.accent_color}
              onChange={(e) => { if (/^#[0-9a-fA-F]{0,6}$/.test(e.target.value)) updateTemplate({ accent_color: e.target.value }); }}
              className="flex-1 rounded border border-gray-200 bg-white px-2 py-1 font-mono text-xs text-gray-700 focus:outline-none focus:ring-1 focus:ring-blue-400" />
          </div>
          <button
            onClick={() => updateTemplate({ accent_color: template.primary_color })}
            className="mt-1.5 text-[10px] text-blue-500 hover:text-blue-700"
          >← Igualar al color principal</button>
        </div>

        {/* Tabla */}
        <div className="border-b border-gray-200 p-4">
          <p className="mb-3 text-[10px] font-semibold uppercase tracking-wider text-gray-500">Tabla de conceptos</p>

          <label className="mb-1.5 block text-xs font-medium text-gray-700">Densidad</label>
          <div className="flex rounded-lg border border-gray-200 overflow-hidden">
            {([
              { value: 'compact',  label: 'Compacta' },
              { value: 'normal',   label: 'Normal' },
              { value: 'spacious', label: 'Espaciada' },
            ] as const).map(opt => (
              <button key={opt.value}
                onClick={() => updateTemplate({ table_density: opt.value })}
                className={clsx('flex-1 px-2 py-1.5 text-xs transition-colors',
                  template.table_density === opt.value
                    ? 'bg-blue-600 text-white font-medium'
                    : 'text-gray-600 hover:bg-gray-50 bg-white')}
              >{opt.label}</button>
            ))}
          </div>

          <label className="mb-1.5 mt-3 block text-xs font-medium text-gray-700">Bordes</label>
          <div className="flex rounded-lg border border-gray-200 overflow-hidden">
            {([
              { value: 'full',       label: 'Completo' },
              { value: 'horizontal', label: 'Horizontal' },
              { value: 'none',       label: 'Sin bordes' },
            ] as const).map(opt => (
              <button key={opt.value}
                onClick={() => updateTemplate({ table_borders: opt.value })}
                className={clsx('flex-1 px-2 py-1.5 text-xs transition-colors',
                  template.table_borders === opt.value
                    ? 'bg-blue-600 text-white font-medium'
                    : 'text-gray-600 hover:bg-gray-50 bg-white')}
              >{opt.label}</button>
            ))}
          </div>

          <div className="mt-3 flex items-center justify-between">
            <span className="text-xs font-medium text-gray-700">Filas alternas</span>
            <button
              onClick={() => updateTemplate({ table_striping: !template.table_striping })}
              className={clsx('relative h-4 w-7 shrink-0 rounded-full transition-colors',
                template.table_striping ? 'bg-blue-500' : 'bg-gray-200')}
            >
              <span className={clsx('absolute top-0.5 h-3 w-3 rounded-full bg-white shadow transition-transform',
                template.table_striping ? 'left-3.5' : 'left-0.5')} />
            </button>
          </div>
        </div>

        {/* Página */}
        <div className="border-b border-gray-200 p-4">
          <p className="mb-3 text-[10px] font-semibold uppercase tracking-wider text-gray-500">Página</p>
          <label className="mb-1.5 block text-xs font-medium text-gray-700">Tamaño</label>
          <div className="flex rounded-lg border border-gray-200 overflow-hidden">
            {([
              { value: 'letter', label: 'Letter (US)' },
              { value: 'a4',     label: 'A4 (Internacional)' },
            ] as const).map(opt => (
              <button key={opt.value}
                onClick={() => updateTemplate({ page_size: opt.value })}
                className={clsx('flex-1 px-2 py-1.5 text-xs transition-colors',
                  template.page_size === opt.value
                    ? 'bg-blue-600 text-white font-medium'
                    : 'text-gray-600 hover:bg-gray-50 bg-white')}
              >{opt.label}</button>
            ))}
          </div>

          {/* Margins */}
          <p className="mb-2 mt-4 text-[10px] font-medium text-gray-500">Márgenes (cm)</p>
          <div className="grid grid-cols-2 gap-x-3 gap-y-2">
            {([
              { key: 'margin_top',    label: 'Superior' },
              { key: 'margin_bottom', label: 'Inferior' },
              { key: 'margin_left',   label: 'Izquierdo' },
              { key: 'margin_right',  label: 'Derecho' },
            ] as const).map(({ key, label }) => (
              <div key={key}>
                <label className="mb-0.5 block text-[10px] text-gray-500">{label}</label>
                <input
                  type="number"
                  min={0.5}
                  max={4}
                  step={0.1}
                  value={template[key]}
                  onChange={(e) => updateTemplate({ [key]: parseFloat(e.target.value) || 0.5 })}
                  className="w-full rounded border border-gray-200 bg-white px-2 py-1 text-xs text-gray-700 focus:outline-none focus:ring-1 focus:ring-blue-400"
                />
              </div>
            ))}
          </div>
        </div>

        {/* Visual page editor — zones */}
        <div className="flex-1 p-4">
          <div className="mb-3 flex items-center justify-between">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-gray-500">
              Secciones del documento
            </p>
            <span className="text-[9px] text-gray-400">arrastra para reordenar</span>
          </div>

          {/* Page representation */}
          <div className="rounded-lg border-2 border-gray-300 bg-white p-1.5 shadow-inner">
            <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
              <SortableContext items={sortedZones.map((z) => z.id)} strategy={verticalListSortingStrategy}>
                <div className="space-y-1">
                  {sortedZones.map((zone) => {
                    const zoneProps: SortableZoneProps = {
                      zone,
                      isSelected: selectedZone === zone.id,
                      onSelect: () => setSelectedZone(selectedZone === zone.id ? null : zone.id),
                      onToggleVisible: () => updateZone(zone.id, { visible: !zone.visible }),
                      onHeaderResizeStart: handleHeaderResizeStart,
                    };
                    return <SortableZone key={zone.id} {...zoneProps} />;
                  })}
                </div>
              </SortableContext>
            </DndContext>
          </div>

          {/* Header height control (visible when header zone is selected or always) */}
          <div className="mt-3 flex items-center justify-between rounded-lg border border-gray-200 bg-white px-3 py-2">
            <div>
              <p className="text-xs font-medium text-gray-700">Altura del encabezado</p>
              <p className="text-[10px] text-gray-400">Arrastra el borde inferior del bloque o usa el slider</p>
            </div>
            <div className="flex items-center gap-1.5">
              <input
                type="range"
                min={32}
                max={120}
                step={4}
                value={template.header_height}
                onChange={(e) => {
                  const v = parseInt(e.target.value);
                  setTemplate((prev) => { schedulePreview({ ...prev, header_height: v }); return { ...prev, header_height: v }; });
                  setSaved(false);
                }}
                className="w-20 accent-blue-500"
              />
              <span className="w-12 text-right font-mono text-xs text-gray-600">{template.header_height}pt</span>
            </div>
          </div>

          {/* Conceptos zone detail panel */}
          {selectedZoneData?.id === 'conceptos' && (
            <div className="mt-2 rounded-lg border border-blue-200 bg-blue-50 px-3 pb-3 pt-2">
              <p className="mb-2 text-[10px] font-medium text-blue-700">Columnas visibles</p>
              <div className="space-y-1">
                {ALL_COLUMNS.map((col) => (
                  <label key={col.id} className="flex cursor-pointer items-center gap-2">
                    <input
                      type="checkbox"
                      checked={conceptosZone?.columns.includes(col.id) ?? false}
                      onChange={() => toggleColumn(col.id)}
                      className="h-3.5 w-3.5 rounded border-gray-300 text-blue-500 focus:ring-blue-400"
                    />
                    <span className="text-xs text-gray-700">{col.label}</span>
                  </label>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="shrink-0 border-t border-gray-200 p-4 space-y-2">
          <button
            onClick={handleSave}
            className={clsx(
              'flex w-full items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-xs font-semibold text-white shadow-sm transition-colors',
              saved ? 'bg-emerald-500 hover:bg-emerald-600' : 'bg-blue-600 hover:bg-blue-700',
            )}
          >
            {saved ? '✓ Template guardado' : 'Guardar template'}
          </button>

          <div className="flex gap-2">
            <button
              onClick={exportJson}
              className="flex-1 rounded-lg border border-gray-200 bg-white px-2 py-1.5 text-xs text-gray-600 transition-colors hover:bg-gray-50"
            >
              Exportar JSON
            </button>
            <label className="flex-1 cursor-pointer rounded-lg border border-gray-200 bg-white px-2 py-1.5 text-center text-xs text-gray-600 transition-colors hover:bg-gray-50">
              Cargar JSON
              <input type="file" accept=".json" onChange={importJson} className="hidden" />
            </label>
          </div>
        </div>
      </div>

      {/* Right: preview */}
      <div className="flex flex-1 flex-col bg-gray-100 min-w-0">
        {sourceFile ? (
          <>
            <div className="flex shrink-0 items-center justify-between border-b border-gray-200 bg-white px-4 py-2">
              <span className="text-xs font-medium text-gray-600">
                Preview — primera página del documento
              </span>
              <div className="flex items-center gap-3">
                {previewLoading && (
                  <span className="flex items-center gap-1 text-xs text-blue-500">
                    <RefreshCw size={11} className="animate-spin" />
                    Actualizando...
                  </span>
                )}
                <button
                  onClick={() => fetchPreview(template)}
                  disabled={previewLoading}
                  className="flex items-center gap-1 rounded-lg px-2 py-1 text-xs text-gray-500 transition-colors hover:bg-gray-100 disabled:opacity-50"
                >
                  <RefreshCw size={11} />
                  Refrescar
                </button>
              </div>
            </div>
            <div className="relative flex-1">
              {previewUrl ? (
                <iframe
                  src={`${previewUrl}#toolbar=0&navpanes=0`}
                  className="absolute inset-0 h-full w-full border-0"
                  title="Preview PDF"
                />
              ) : (
                <div className="flex h-full items-center justify-center">
                  {previewError ? (
                    <div className="text-center">
                      <p className="text-sm font-medium text-red-500">No se pudo generar el preview</p>
                      <p className="mt-1 text-xs text-gray-400">{previewError}</p>
                      <button
                        onClick={() => fetchPreview(template)}
                        className="mt-3 rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-xs text-gray-600 hover:bg-gray-50"
                      >
                        Reintentar
                      </button>
                    </div>
                  ) : (
                    <p className="text-sm text-gray-400">
                      {previewLoading ? 'Generando preview...' : 'Preparando preview...'}
                    </p>
                  )}
                </div>
              )}
            </div>
          </>
        ) : (
          <div className="flex flex-1 items-center justify-center">
            <div className="text-center">
              <p className="text-sm font-medium text-gray-500">Sin preview disponible</p>
              <p className="mt-1 text-xs text-gray-400">Carga un XML en el Inspector para ver el preview en vivo.</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
