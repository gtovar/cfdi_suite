/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useState, useRef } from 'react';
import { Upload, FileText, LoaderCircle } from 'lucide-react';
import { motion } from 'motion/react';

interface FileUploadProps {
  onFileSelect: (xml: string) => Promise<void> | void;
  analysisLabel?: string;
  analysisProgress?: number;
  analysisDetail?: string;
}

export default function FileUpload({
  onFileSelect,
  analysisLabel,
  analysisProgress,
  analysisDetail,
}: FileUploadProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [phase, setPhase] = useState<'idle' | 'reading' | 'analyzing'>('idle');
  const [fileName, setFileName] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFile = (file: File) => {
    if (file && (file.type === "text/xml" || file.name.endsWith(".xml"))) {
      const reader = new FileReader();
      setFileName(file.name);
      setIsLoading(true);
      setProgress(0);
      setPhase('reading');
      reader.onprogress = (e) => {
        if (!e.lengthComputable) return;
        const ratio = Math.round((e.loaded / e.total) * 100);
        setProgress(ratio);
      };
      reader.onload = async (e) => {
        const content = e.target?.result as string;
        setProgress(100);
        setPhase('analyzing');
        const analysisStart = Date.now();
        await Promise.resolve(onFileSelect(content));
        const elapsed = Date.now() - analysisStart;
        if (elapsed < 450) {
          await new Promise((resolve) => window.setTimeout(resolve, 450 - elapsed));
        }
        setIsLoading(false);
        setPhase('idle');
      };
      reader.onerror = () => {
        setIsLoading(false);
        setPhase('idle');
        alert("Error al leer el archivo XML.");
      };
      reader.readAsText(file);
    } else {
      alert("Por favor sube un archivo XML válido.");
    }
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files[0];
    handleFile(file);
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className={`relative border-2 border-dashed rounded-xl p-12 transition-all duration-300 flex flex-col items-center justify-center cursor-pointer
        ${isDragging ? 'border-blue-500 bg-blue-50/50' : 'border-gray-300 hover:border-gray-400 bg-white'}`}
      onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
      onDragLeave={() => setIsDragging(false)}
      onDrop={onDrop}
      onClick={() => {
        if (!isLoading) {
          fileInputRef.current?.click();
        }
      }}
    >
      <input
        type="file"
        ref={fileInputRef}
        className="hidden"
        accept=".xml"
        disabled={isLoading}
        onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
      />
      
      {isLoading ? (
        <div className="w-full max-w-md">
          <div className="w-16 h-16 bg-blue-100 rounded-full flex items-center justify-center mb-4 mx-auto">
            {phase === 'reading' ? (
              <FileText className="text-blue-600 w-8 h-8" />
            ) : (
              <LoaderCircle className="text-blue-600 w-8 h-8 animate-spin" />
            )}
          </div>

          <h3 className="text-lg font-semibold text-gray-900 mb-2 text-center">
            {phase === 'reading' ? 'Leyendo archivo XML' : 'Analizando CFDI'}
          </h3>
          <p className="text-sm text-gray-500 text-center max-w-md mx-auto">
            {fileName}
          </p>
          {phase === 'analyzing' ? (
            <p className="mt-2 text-xs font-mono uppercase tracking-widest text-center text-gray-500">
              {analysisLabel || 'Procesando estructura CFDI'}
            </p>
          ) : null}

          <div className="mt-6 border border-[#141414]/10 bg-white/70 p-4 rounded-lg">
            <div className="flex items-center justify-between text-[11px] font-mono uppercase tracking-widest text-gray-500">
              <span>{phase === 'reading' ? 'Lectura' : 'Análisis'}</span>
              <span>{phase === 'reading' ? `${progress}%` : `${analysisProgress ?? 100}%`}</span>
            </div>
            <div className="mt-3 h-2 bg-[#141414]/10 rounded-full overflow-hidden">
              <div
                className="h-full bg-[#141414] transition-[width] duration-200 flex items-center justify-end pr-2"
                style={{ width: `${phase === 'reading' ? progress : (analysisProgress ?? 100)}%` }}
              >
                <span className="text-[9px] font-mono uppercase tracking-widest text-white/85 leading-none" />
              </div>
            </div>
            {phase === 'reading' ? (
              <div className="mt-3 flex items-center justify-between text-[10px] font-mono uppercase tracking-widest text-gray-400">
                <span>Modo de carga</span>
                <span>Lectura local</span>
              </div>
            ) : null}
            {phase === 'analyzing' && analysisDetail ? (
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
      ) : (
        <>
          <div className="w-16 h-16 bg-blue-100 rounded-full flex items-center justify-center mb-4">
            <Upload className="text-blue-600 w-8 h-8" />
          </div>
          
          <h3 className="text-lg font-semibold text-gray-900 mb-2">Cargar XML de Factura</h3>
          <p className="text-sm text-gray-500 text-center max-w-xs">
            Arrastra tu archivo CFDI aquí o haz clic para buscar en tu equipo.
          </p>
          
          <div className="mt-6 flex items-center gap-2 text-xs font-mono text-gray-400">
            <FileText size={14} />
            <span>Soporta CFDI 3.3 y 4.0</span>
          </div>
        </>
      )}
    </motion.div>
  );
}
