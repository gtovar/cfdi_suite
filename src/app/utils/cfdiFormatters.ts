import { explainCfdiField } from '../../cfdi/domain/explainCfdiField';

export function formatExact(value: number) {
  return value.toLocaleString('es-MX', {
    useGrouping: false,
    minimumFractionDigits: 0,
    maximumFractionDigits: 20,
  });
}

export function formatSignedExact(value: number) {
  if (value === 0) return '0';
  return `${value > 0 ? '+' : '-'}${formatExact(Math.abs(value))}`;
}

export function getExplainedMeaning(key: string, value: string | number | null) {
  return explainCfdiField(key, value).meaning;
}

export function getExplainedTaxLabel(code: string) {
  const explained = explainCfdiField('impuesto', code);
  return explained.meaning.includes('sin catalogo')
    ? code
    : `${code} · ${explained.meaning.split('.')[0]}`;
}
