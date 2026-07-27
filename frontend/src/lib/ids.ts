const UUID_RE = /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/;

export function assertBatchId(v: unknown): string {
  if (typeof v !== 'string' || !UUID_RE.test(v)) throw new Error('Identificador de lote inválido');
  return v;
}
