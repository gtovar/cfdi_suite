import clsx from 'clsx';
import { type ChangeEvent, useCallback, useEffect, useRef, useState } from 'react';
import { ChevronDown, ChevronUp, Download, RefreshCw, Upload, X } from 'lucide-react';

const ZONE_LABELS: Record<string, string> = {
  header:    'Encabezado (logo + color)',
  emisor:    'Emisor / Datos del comprobante',
  receptor:  'Receptor',
  conceptos: 'Conceptos (tabla)',
  impuestos: 'Impuestos y Totales',
  timbre:    'Timbre Fiscal Digital + QR',
  footer:    'Pie de página',
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

export interface ZoneConfig {
  id: string;
  visible: boolean;
  order: number;
  columns: string[];
}

export interface TemplateConfig {
  primary_color: string;
  logo_url: string | null;
  footer_note: string;
  zones: ZoneConfig[];
  font_family: 'helvetica' | 'times' | 'courier';
  accent_color: string;
  table_density: 'compact' | 'normal' | 'spacious';
  table_borders: 'full' | 'horizontal' | 'none';
  table_striping: boolean;
  header_layout: 'logo-left' | 'logo-center' | 'text-only';
  page_size: 'letter' | 'a4';
  // Frente F layout controls
  header_height: number;             // pt — height of header zone
  column_widths: Record<string, number>; // relative weight overrides per column
  margin_top: number;                // cm
  margin_bottom: number;             // cm
  margin_left: number;               // cm
  margin_right: number;              // cm
}

export const DEFAULT_TEMPLATE: TemplateConfig = {
  primary_color: '#1a56db',
  logo_url: null,
  footer_note: '',
  zones: [
    { id: 'header',    visible: true, order: 1, columns: [] },
    { id: 'emisor',    visible: true, order: 2, columns: [] },
    { id: 'receptor',  visible: true, order: 3, columns: [] },
    { id: 'conceptos', visible: true, order: 4,
      columns: ['#', 'ClaveProdServ', 'Descripcion', 'ClaveUnidad', 'Cantidad', 'ValorUnitario', 'Importe'] },
    { id: 'impuestos', visible: true, order: 5, columns: [] },
    { id: 'timbre',    visible: true, order: 6, columns: [] },
    { id: 'footer',    visible: true, order: 7, columns: [] },
  ],
  font_family: 'helvetica',
  accent_color: '#1a56db',
  table_density: 'normal',
  table_borders: 'horizontal',
  table_striping: true,
  header_layout: 'logo-left',
  page_size: 'letter',
  header_height: 56,
  column_widths: {},
  margin_top: 1.2,
  margin_bottom: 1.5,
  margin_left: 1.5,
  margin_right: 1.5,
};

interface Props {
  sourceFile: File;
  onDownload: (template: TemplateConfig) => void;
  onClose: () => void;
  pdfPhase: string;
  pdfError?: string;
}

export default function PdfTemplateBuilder({ sourceFile, onDownload, onClose, pdfPhase, pdfError }: Props) {
  const [template, setTemplate] = useState<TemplateConfig>(DEFAULT_TEMPLATE);
  const [expandedZone, setExpandedZone] = useState<string | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const fetchPreview = useCallback(async (tpl: TemplateConfig) => {
    if (abortRef.current) abortRef.current.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setPreviewLoading(true);
    try {
      const form = new FormData();
      form.append('file', sourceFile);
      form.append('template', JSON.stringify(tpl));
      const res = await fetch('/api/cfdi/pdf/preview', { method: 'POST', body: form, signal: ctrl.signal });
      if (!res.ok) throw new Error('preview error');
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      setPreviewUrl((prev) => { if (prev) URL.revokeObjectURL(prev); return url; });
    } catch {
      // aborted or network error — silently ignore
    } finally {
      setPreviewLoading(false);
    }
  }, [sourceFile]);

  const schedulePreview = useCallback((tpl: TemplateConfig) => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => fetchPreview(tpl), 400);
  }, [fetchPreview]);

  useEffect(() => {
    fetchPreview(DEFAULT_TEMPLATE);
    return () => {
      if (abortRef.current) abortRef.current.abort();
      if (debounceRef.current) clearTimeout(debounceRef.current);
      setPreviewUrl((prev) => { if (prev) URL.revokeObjectURL(prev); return null; });
    };
  }, [fetchPreview]);

  function updateTemplate(patch: Partial<TemplateConfig>) {
    setTemplate((prev) => {
      const next = { ...prev, ...patch };
      schedulePreview(next);
      return next;
    });
  }

  function updateZone(id: string, patch: Partial<ZoneConfig>) {
    setTemplate((prev) => {
      const zones = prev.zones.map((z) => z.id === id ? { ...z, ...patch } : z);
      const next = { ...prev, zones };
      schedulePreview(next);
      return next;
    });
  }

  function moveZone(id: string, dir: -1 | 1) {
    setTemplate((prev) => {
      const sorted = [...prev.zones].sort((a, b) => a.order - b.order);
      const idx = sorted.findIndex((z) => z.id === id);
      const target = idx + dir;
      if (target < 0 || target >= sorted.length) return prev;
      const zones = prev.zones.map((z) => {
        if (z.id === sorted[idx].id)     return { ...z, order: sorted[target].order };
        if (z.id === sorted[target].id)  return { ...z, order: sorted[idx].order };
        return z;
      });
      const next = { ...prev, zones };
      schedulePreview(next);
      return next;
    });
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
  }

  function handleLogoUpload(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => updateTemplate({ logo_url: ev.target?.result as string });
    reader.readAsDataURL(file);
    e.target.value = '';
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
        const parsed = JSON.parse(ev.target?.result as string) as TemplateConfig;
        setTemplate(parsed);
        schedulePreview(parsed);
      } catch { /* invalid JSON */ }
    };
    reader.readAsText(file);
    e.target.value = '';
  }

  const sortedZones = [...template.zones].sort((a, b) => a.order - b.order);
  const conceptosZone = template.zones.find((z) => z.id === 'conceptos');
  const isDownloading = pdfPhase !== 'idle';

  return (
    <div
      className="fixed inset-0 z-50 flex bg-black/50"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="ml-auto flex h-full w-full max-w-5xl flex-col bg-white shadow-2xl">

        {/* Header */}
        <div className="flex shrink-0 items-center justify-between border-b border-gray-200 px-5 py-3">
          <div>
            <h2 className="text-sm font-semibold text-gray-900">⚡ PDF Pro — Constructor de Template</h2>
            <p className="text-xs text-gray-500">El preview se actualiza automáticamente al cambiar la configuración.</p>
          </div>
          <button onClick={onClose} className="rounded-lg p-1.5 text-gray-400 hover:bg-gray-100 hover:text-gray-700 transition-colors">
            <X size={16} />
          </button>
        </div>

        {/* Body */}
        <div className="flex flex-1 min-h-0">

          {/* Left panel */}
          <div className="flex w-72 shrink-0 flex-col overflow-y-auto border-r border-gray-200 bg-gray-50">

            {/* Brand */}
            <div className="border-b border-gray-200 p-4">
              <p className="mb-3 text-[10px] font-semibold uppercase tracking-wider text-gray-500">Marca</p>

              <label className="mb-1.5 block text-xs font-medium text-gray-700">Color primario</label>
              <div className="flex items-center gap-2">
                <input
                  type="color"
                  value={template.primary_color}
                  onChange={(e) => updateTemplate({ primary_color: e.target.value })}
                  className="h-8 w-12 cursor-pointer rounded border border-gray-200 bg-white p-0.5"
                />
                <input
                  type="text"
                  value={template.primary_color}
                  onChange={(e) => {
                    if (/^#[0-9a-fA-F]{0,6}$/.test(e.target.value))
                      updateTemplate({ primary_color: e.target.value });
                  }}
                  className="flex-1 rounded border border-gray-200 bg-white px-2 py-1 font-mono text-xs text-gray-700 focus:outline-none focus:ring-1 focus:ring-blue-400"
                />
              </div>

              <label className="mb-1.5 mt-4 block text-xs font-medium text-gray-700">Logo de empresa</label>
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

            {/* Zones */}
            <div className="flex-1 p-4">
              <p className="mb-3 text-[10px] font-semibold uppercase tracking-wider text-gray-500">Secciones del documento</p>
              <div className="space-y-1.5">
                {sortedZones.map((zone, idx) => (
                  <div key={zone.id} className="rounded-xl border border-gray-200 bg-white overflow-hidden">
                    <div className="flex items-center gap-2 px-3 py-2">
                      {/* Reorder */}
                      <div className="flex shrink-0 flex-col gap-0">
                        <button
                          onClick={() => moveZone(zone.id, -1)}
                          disabled={idx === 0}
                          className="text-gray-300 transition-colors hover:text-gray-600 disabled:opacity-20"
                        ><ChevronUp size={11} /></button>
                        <button
                          onClick={() => moveZone(zone.id, 1)}
                          disabled={idx === sortedZones.length - 1}
                          className="text-gray-300 transition-colors hover:text-gray-600 disabled:opacity-20"
                        ><ChevronDown size={11} /></button>
                      </div>

                      {/* Toggle */}
                      <button
                        onClick={() => updateZone(zone.id, { visible: !zone.visible })}
                        className={clsx(
                          'relative h-4 w-7 shrink-0 rounded-full transition-colors',
                          zone.visible ? 'bg-blue-500' : 'bg-gray-200',
                        )}
                        aria-label={zone.visible ? 'Ocultar sección' : 'Mostrar sección'}
                      >
                        <span className={clsx(
                          'absolute top-0.5 h-3 w-3 rounded-full bg-white shadow transition-transform',
                          zone.visible ? 'left-3.5' : 'left-0.5',
                        )} />
                      </button>

                      <span className={clsx(
                        'flex-1 text-xs leading-tight',
                        zone.visible ? 'text-gray-800' : 'text-gray-400 line-through',
                      )}>
                        {ZONE_LABELS[zone.id] ?? zone.id}
                      </span>

                      {zone.id === 'conceptos' && (
                        <button
                          onClick={() => setExpandedZone(expandedZone === 'conceptos' ? null : 'conceptos')}
                          className="shrink-0 text-[10px] font-medium text-blue-500 hover:text-blue-700"
                        >
                          {expandedZone === 'conceptos' ? 'cerrar' : 'columnas'}
                        </button>
                      )}
                    </div>

                    {/* Conceptos columns */}
                    {zone.id === 'conceptos' && expandedZone === 'conceptos' && (
                      <div className="border-t border-gray-100 bg-gray-50 px-4 pb-3 pt-2">
                        <p className="mb-2 text-[10px] font-medium text-gray-500">Columnas visibles en la tabla</p>
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
                ))}
              </div>
            </div>

            {/* Actions */}
            <div className="shrink-0 border-t border-gray-200 p-4 space-y-2">
              <button
                onClick={() => onDownload(template)}
                disabled={isDownloading}
                className="flex w-full items-center justify-center gap-2 rounded-xl bg-blue-600 px-4 py-2.5 text-xs font-semibold text-white shadow-sm transition-colors hover:bg-blue-700 disabled:opacity-60"
              >
                <Download size={13} />
                {isDownloading ? 'Generando PDF...' : 'Descargar PDF completo'}
              </button>

              {pdfError && (
                <p className="text-center text-xs text-red-500">{pdfError}</p>
              )}

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
          <div className="flex flex-1 flex-col bg-gray-100">
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
                <div className="flex h-full items-center justify-center text-sm text-gray-400">
                  {previewLoading ? 'Generando preview...' : 'Cargando...'}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
