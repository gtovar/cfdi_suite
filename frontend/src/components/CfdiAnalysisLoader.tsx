import { LoaderCircle } from 'lucide-react';

interface CfdiAnalysisLoaderProps {
  fileName: string | null;
  analysisLabel?: string;
  analysisProgress?: number;
  analysisDetail?: string;
}

export default function CfdiAnalysisLoader({
  fileName,
  analysisLabel,
  analysisProgress,
  analysisDetail,
}: CfdiAnalysisLoaderProps) {
  return (
    <div className="w-full max-w-md">
      <div className="w-16 h-16 bg-blue-100 rounded-full flex items-center justify-center mb-4 mx-auto">
        <LoaderCircle className="text-blue-600 w-8 h-8 animate-spin" />
      </div>

      <h3 className="text-lg font-semibold text-gray-900 mb-2 text-center">
        Analizando CFDI
      </h3>
      <p className="text-sm text-gray-500 text-center max-w-md mx-auto">
        {fileName}
      </p>
      <p className="mt-2 text-xs font-mono uppercase tracking-widest text-center text-gray-500">
        {analysisLabel || 'Procesando estructura CFDI'}
      </p>

      <div className="mt-6 border border-[#141414]/10 bg-white/70 p-4 rounded-lg">
        <div className="flex items-center justify-between text-[11px] font-mono uppercase tracking-widest text-gray-500">
          <span>Análisis</span>
          <span>{analysisProgress ?? 100}%</span>
        </div>
        <div className="mt-3 h-2 bg-[#141414]/10 rounded-full overflow-hidden">
          <div
            className="h-full bg-[#141414] transition-[width] duration-200 flex items-center justify-end pr-2"
            style={{ width: `${analysisProgress ?? 100}%` }}
          >
            <span className="text-[9px] font-mono uppercase tracking-widest text-white/85 leading-none" />
          </div>
        </div>
        {analysisDetail ? (
          <div className="mt-3 grid grid-cols-2 gap-3 border-t border-[#141414]/8 pt-3">
            <div>
              <p className="text-[10px] font-mono uppercase tracking-widest text-gray-400">
                Filas detectadas
              </p>
              <p className="mt-1 text-[11px] font-mono text-[#141414]">
                {analysisDetail}
              </p>
            </div>
            <div>
              <p className="text-[10px] font-mono uppercase tracking-widest text-gray-400">
                Progreso actual
              </p>
              <p className="mt-1 text-[11px] font-mono text-[#141414]">
                {analysisLabel || 'Procesando'}
              </p>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
