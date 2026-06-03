import ExtractWorkspacePagination from './extract-workspace/ExtractWorkspacePagination';
import ExtractWorkspaceTable from './extract-workspace/ExtractWorkspaceTable';
import ExtractWorkspaceToolbar from './extract-workspace/ExtractWorkspaceToolbar';
import type { ExtractGridController, ExtractMode } from './extract-workspace/types';

interface ExtractWorkspaceProps {
  embedded?: boolean;
  activeDatasetType: ExtractMode;
  grid: ExtractGridController;
}

export default function ExtractWorkspace({
  embedded = false,
  activeDatasetType,
  grid,
}: ExtractWorkspaceProps) {

  return (
    <section className={embedded ? 'flex-1 min-h-0 flex flex-col' : 'flex-1 flex flex-col overflow-hidden relative'}>
      {embedded ? null : (
        <div className="grid grid-cols-3 border-b border-[#141414]">
          <div className="p-4 border-r border-[#141414]">
            <p className="text-[10px] font-mono uppercase opacity-50">
              {activeDatasetType === 'ingresos' ? 'Unidad de lectura' : 'Unidad de extracción'}
            </p>
            <p className="text-xs font-bold mt-1">
              {activeDatasetType === 'ingresos' ? 'Una fila por concepto e impuesto' : 'Una fila por documento relacionado e impuesto DR'}
            </p>
          </div>
          <div className="p-4 border-r border-[#141414]">
            <p className="text-[10px] font-mono uppercase opacity-50">Origen</p>
            <p className="text-xs font-bold mt-1">
              {activeDatasetType === 'ingresos' ? 'Conceptos / Traslados / Retenciones' : 'Pago / DoctoRelacionado / DR'}
            </p>
          </div>
          <div className="p-4">
            <p className="text-[10px] font-mono uppercase opacity-50">Vista</p>
            <p className="text-xs font-bold mt-1">Grid paginada sobre dataset completo</p>
          </div>
        </div>
      )}

      <ExtractWorkspaceToolbar grid={grid} />

      <div className="flex-1 overflow-auto">
        <ExtractWorkspaceTable activeDatasetType={activeDatasetType} grid={grid} />
      </div>
      <ExtractWorkspacePagination grid={grid} />
    </section>
  );
}
