import { useMemo, useRef, useState } from 'react';
import type { BatchFileResult } from './batch-api-client';

export interface QueueEntry {
  file: File;
  result: BatchFileResult | null;
}

export interface BatchStats {
  completed: number;
  ok: number;
  conErrores: number;
  errors: number;
  totalMonto: number;
  filesPerSecond: number;
  estimatedRemainingSeconds: number;
  topEmisores: Array<{ rfc: string; nombre: string; count: number }>;
  topMonth: { month: string; count: number } | null;
}

const MESES_SHORT = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic'];

export function formatTopMonth(month: string): string {
  const [year, m] = month.split('-');
  const mes = MESES_SHORT[parseInt(m, 10) - 1] ?? month;
  return `${mes} ${year}`;
}

export function formatMonto(n: number): string {
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M MXN`;
  if (n >= 1_000) return `$${(n / 1_000).toFixed(0)}K MXN`;
  return n.toLocaleString('es-MX', { style: 'currency', currency: 'MXN' });
}

export function formatRemainingTime(seconds: number): string {
  if (seconds < 60) return `${Math.ceil(seconds)}s`;
  const mins = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  return secs > 0 ? `${mins}m ${secs}s` : `${mins}m`;
}

export function useBatchStats(queue: QueueEntry[], totalFiles: number): BatchStats {
  const tsRef = useRef<number[]>([]);
  const [fps, setFps] = useState(0);
  const [prevCompleted, setPrevCompleted] = useState(0);

  const base = useMemo(() => {
    const emisorMap = new Map<string, { nombre: string; count: number }>();
    const monthMap = new Map<string, number>();
    let completed = 0, ok = 0, conErrores = 0, errors = 0, totalMonto = 0;

    for (const e of queue) {
      if (e.result === null) continue;
      completed++;
      if (e.result.status === 'ok') ok++;
      else if (e.result.status === 'con_errores') conErrores++;
      else errors++;

      const n = parseFloat(e.result.total);
      if (!isNaN(n) && n > 0) totalMonto += n;

      const rfc = e.result.rfc_emisor;
      if (rfc && rfc !== 'XAXX010101000' && rfc !== 'XEXX010101000') {
        const ex = emisorMap.get(rfc);
        if (ex) ex.count++;
        else emisorMap.set(rfc, { nombre: e.result.nombre_emisor || rfc, count: 1 });
      }

      if (e.result.fecha && e.result.fecha.length >= 7) {
        const m = e.result.fecha.slice(0, 7);
        monthMap.set(m, (monthMap.get(m) ?? 0) + 1);
      }
    }

    const topEmisores = [...emisorMap.entries()]
      .sort((a, b) => b[1].count - a[1].count)
      .slice(0, 3)
      .map(([rfc, v]) => ({ rfc, nombre: v.nombre, count: v.count }));

    let topMonth: { month: string; count: number } | null = null;
    for (const [month, count] of monthMap.entries()) {
      if (!topMonth || count > topMonth.count) topMonth = { month, count };
    }

    return { completed, ok, conErrores, errors, totalMonto, topEmisores, topMonth };
  }, [queue]);

  if (base.completed !== prevCompleted) {
    const newItems = base.completed - prevCompleted;
    setPrevCompleted(base.completed);

    if (base.completed === 0) {
      setFps(0);
      tsRef.current = [];
    } else if (newItems > 0) {
      const now = Date.now();
      // Offset batched completions by 1ms each so span is never 0
      for (let i = 0; i < newItems; i++) tsRef.current.push(now + i);
      if (tsRef.current.length > 30) tsRef.current = tsRef.current.slice(-30);

      const ts = tsRef.current;
      if (ts.length >= 2) {
        const span = (ts[ts.length - 1] - ts[0]) / 1000;
        if (span > 0) setFps((ts.length - 1) / span);
      }
    }
  }

  return {
    ...base,
    filesPerSecond: fps,
    estimatedRemainingSeconds: fps > 0 ? (totalFiles - base.completed) / fps : 0,
  };
}
