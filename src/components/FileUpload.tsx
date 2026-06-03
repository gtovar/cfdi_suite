/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useState, useRef } from 'react';
import { Upload, FileText, LoaderCircle } from 'lucide-react';
import { motion } from 'motion/react';

interface FileUploadProps {
  onFileSelect: (file: File) => Promise<void> | void;
  onFilesSelect?: (files: File[]) => void;
  multiple?: boolean;
  analysisLabel?: string;
  analysisProgress?: number;
  analysisDetail?: string;
}

export default function FileUpload({
  onFileSelect,
  onFilesSelect,
  multiple,
  analysisLabel,
  analysisProgress,
  analysisDetail,
}: FileUploadProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [fileName, setFileName] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFile = async (file: File) => {
    if (file && (file.type === "text/xml" || file.name.endsWith(".xml"))) {
      setFileName(file.name);
      setIsLoading(true);
      const analysisStart = Date.now();
      await Promise.resolve(onFileSelect(file));
      const elapsed = Date.now() - analysisStart;
      if (elapsed < 450) {
        await new Promise((resolve) => window.setTimeout(resolve, 450 - elapsed));
      }
      setIsLoading(false);
    } else {
      alert("Por favor sube un archivo XML válido.");
    }
  };

  const handleFiles = (raw: FileList | File[]) => {
    const xmlFiles = Array.from(raw).filter((f) => f.type === 'text/xml' || f.name.endsWith('.xml'));
    if (xmlFiles.length === 0) { alert('Por favor sube archivos XML válidos.'); return; }
    if (multiple && xmlFiles.length > 1 && onFilesSelect) { onFilesSelect(xmlFiles); return; }
    handleFile(xmlFiles[0]);
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    handleFiles(e.dataTransfer.files);
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
        multiple={multiple}
        disabled={isLoading}
        onChange={(e) => e.target.files && handleFiles(e.target.files)}
      />
      
      {isLoading ? (
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
      ) : (
        <>
          <div className="w-16 h-16 bg-blue-100 rounded-full flex items-center justify-center mb-4">
            <Upload className="text-blue-600 w-8 h-8" />
          </div>

          <h3 className="text-lg font-semibold text-gray-900 mb-2">
            {multiple ? 'Cargar facturas XML' : 'Cargar XML de Factura'}
          </h3>
          <p className="text-sm text-gray-500 text-center max-w-xs">
            {multiple
              ? 'Arrastra uno o varios CFDI aquí, o haz clic para seleccionar archivos.'
              : 'Arrastra tu archivo CFDI aquí o haz clic para buscar en tu equipo.'}
          </p>

          <div className="mt-6 flex items-center gap-2 text-xs font-mono text-gray-400">
            <FileText size={14} />
            <span>{multiple ? 'CFDI 3.3 y 4.0 · individual o en lote' : 'Soporta CFDI 3.3 y 4.0'}</span>
          </div>
        </>
      )}
    </motion.div>
  );
}
