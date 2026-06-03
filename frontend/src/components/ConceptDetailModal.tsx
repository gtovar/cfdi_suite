import { AnimatePresence, motion } from 'motion/react';
import { ArrowLeft } from 'lucide-react';
import type { CFDIConcept } from '../cfdi/public';

interface ConceptDetailModalProps {
  selectedConcept: CFDIConcept | null;
  onClose: () => void;
  formatExact: (value: number) => string;
  getExplainedMeaning: (key: string, value: string | number | null) => string;
  getExplainedTaxLabel: (code: string) => string;
}

export default function ConceptDetailModal({
  selectedConcept,
  onClose,
  formatExact,
  getExplainedMeaning,
  getExplainedTaxLabel,
}: ConceptDetailModalProps) {
  return (
    <AnimatePresence>
      {selectedConcept && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="absolute inset-0 bg-[#E4E3E0]/95 z-20 flex flex-col p-8"
        >
          <div className="flex items-center justify-between mb-8">
            <button
              onClick={onClose}
              className="flex items-center gap-2 text-xs font-mono uppercase tracking-widest hover:underline"
            >
              <ArrowLeft size={14} /> Volver a la tabla
            </button>
            <span className="text-[10px] font-mono uppercase opacity-50">Detalle de Concepto</span>
          </div>

          <div className="grid grid-cols-2 gap-12">
            <div>
              <h2 className="text-2xl font-serif italic mb-4">{selectedConcept.descripcion}</h2>
              <div className="space-y-4">
                <div>
                  <p className="text-[10px] font-mono uppercase opacity-50">Clave Prod/Serv</p>
                  <p className="text-sm font-mono">{selectedConcept.claveProdServ}</p>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <p className="text-[10px] font-mono uppercase opacity-50">Cantidad</p>
                    <p className="text-sm font-mono">{selectedConcept.cantidad}</p>
                  </div>
                  <div>
                    <p className="text-[10px] font-mono uppercase opacity-50">Valor Unitario</p>
                    <p className="text-sm font-mono">${selectedConcept.valorUnitario.toFixed(6)}</p>
                  </div>
                </div>
                <div className="p-4 border border-[#141414] bg-white/50 rounded">
                  <p className="text-[10px] font-mono uppercase opacity-50 mb-2">Análisis de Importe</p>
                  <div className="flex justify-between text-xs font-mono mb-1">
                    <span>Declarado (XML):</span>
                    <span>${selectedConcept.importe.toFixed(6)}</span>
                  </div>
                  <div className="flex justify-between text-xs font-mono mb-1">
                    <span>Calculado (Cant * Val):</span>
                    <span>${selectedConcept.importeCalculado.toFixed(6)}</span>
                  </div>
                  <div className={`flex justify-between text-xs font-mono pt-2 border-t border-[#141414]/10 mt-2 font-bold ${selectedConcept.diferencia !== 0 ? 'text-red-600' : 'text-green-600'}`}>
                    <span>Diferencia:</span>
                    <span>${formatExact(selectedConcept.diferencia)}</span>
                  </div>
                </div>
              </div>
            </div>

            <div>
              <h3 className="text-xs font-mono uppercase tracking-widest opacity-50 mb-4">Impuestos Trasladados</h3>
              {selectedConcept.impuestos.length === 0 ? (
                <p className="text-xs font-mono italic opacity-50">No hay impuestos registrados para este concepto.</p>
              ) : (
                <div className="space-y-4">
                  {selectedConcept.impuestos.map((imp, idx) => (
                    <div key={idx} className="p-4 border border-[#141414]/20 rounded bg-white/30">
                      <div className="flex justify-between mb-2">
                        <span
                          className="text-[10px] font-mono font-bold uppercase"
                          title={`${getExplainedMeaning('impuesto', imp.impuesto)} ${getExplainedMeaning('tipoFactor', imp.tipoFactor)}`}
                        >
                          {getExplainedTaxLabel(imp.impuesto)} ({imp.tipoFactor})
                        </span>
                        <span
                          className="text-[10px] font-mono"
                          title={getExplainedMeaning('tasaOCuota', imp.tasaOCuota)}
                        >
                          Tasa: {(imp.tasaOCuota * 100).toFixed(2)}%
                        </span>
                      </div>
                      <p className="text-[10px] font-mono opacity-55 mb-3">
                        {getExplainedMeaning('tipoFactor', imp.tipoFactor)}
                      </p>
                      <div className="space-y-1 text-[10px] font-mono opacity-70">
                        <div className="flex justify-between">
                          <span title={getExplainedMeaning('base', imp.base)}>Base:</span>
                          <span>${imp.base.toFixed(6)}</span>
                        </div>
                        <div className="flex justify-between">
                          <span title={getExplainedMeaning('importe', imp.importe)}>Importe XML:</span>
                          <span>${imp.importe.toFixed(6)}</span>
                        </div>
                        <div className="flex justify-between italic">
                          <span>Importe Calc:</span>
                          <span>${imp.importeCalculado.toFixed(6)}</span>
                        </div>
                        <div className={`flex justify-between pt-2 border-t border-[#141414]/10 mt-2 ${imp.diferencia !== 0 ? 'text-red-600 font-bold' : 'text-green-600'}`}>
                          <span>Diferencia:</span>
                          <span>${formatExact(imp.diferencia)}</span>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
