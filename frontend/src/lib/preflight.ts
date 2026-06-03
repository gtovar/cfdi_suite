export interface PreflightSummary {
  totalFiles: number;
  sampleScanned: number;
  validCfdi: number;
  possibleDuplicates: number;
  dateRange: { min: string; max: string } | null;
  topRfcEmisores: string[];
}

export async function runPreflight(files: File[]): Promise<PreflightSummary> {
  const SAMPLE_SIZE = Math.min(50, files.length);
  const sample = files.slice(0, SAMPLE_SIZE);

  const uuidsSeen = new Set<string>();
  const dates: string[] = [];
  const rfcMap = new Map<string, number>();
  let validCfdi = 0;
  let possibleDuplicates = 0;

  await Promise.all(
    sample.map(async (file) => {
      try {
        const text = await file.text();
        if (!text.includes('cfdi.sat.gob.mx') && !text.includes('<cfdi:Comprobante')) return;
        validCfdi++;

        const uuidMatch = text.match(/UUID="([A-Fa-f0-9-]{36})"/);
        if (uuidMatch) {
          if (uuidsSeen.has(uuidMatch[1])) possibleDuplicates++;
          else uuidsSeen.add(uuidMatch[1]);
        }

        const fechaMatch = text.match(/Fecha="(\d{4}-\d{2}-\d{2})/);
        if (fechaMatch) dates.push(fechaMatch[1]);

        const rfcMatch = text.match(/RfcEmisor="([A-Z&Ñ]{3,4}\d{6}[A-Z0-9]{3})"/i);
        if (rfcMatch) rfcMap.set(rfcMatch[1], (rfcMap.get(rfcMatch[1]) ?? 0) + 1);
      } catch {
        // ignore unreadable files
      }
    }),
  );

  dates.sort();

  const topRfcEmisores = [...rfcMap.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 3)
    .map(([rfc]) => rfc);

  const ratio = SAMPLE_SIZE < files.length ? files.length / SAMPLE_SIZE : 1;

  return {
    totalFiles: files.length,
    sampleScanned: SAMPLE_SIZE,
    validCfdi: Math.round(validCfdi * ratio),
    possibleDuplicates,
    dateRange: dates.length >= 1 ? { min: dates[0], max: dates[dates.length - 1] } : null,
    topRfcEmisores,
  };
}
