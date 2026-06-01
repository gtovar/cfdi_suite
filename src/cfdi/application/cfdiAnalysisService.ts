import { XMLParser } from 'fast-xml-parser';
import {
  canonicalConceptToCfdiConcept,
  canonicalSummaryTaxesToCfdi,
  enrichCfdiWithMathDiagnosis,
} from './cfdiAnalysisAdapter';
import { normalizeCfdi } from '../domain/normalizeCfdi';
import type { AuditFinding, CFDIConcept, CFDIData, CFDIProfile, TaxAuditGroup } from './cfdiTypes';

type XmlNode = Record<string, unknown>;

const parser = new XMLParser({
  ignoreAttributes: false,
  attributeNamePrefix: '@_',
  removeNSPrefix: true,
  parseTagValue: false,
  trimValues: true,
});

function asArray<T>(value: T | T[] | undefined | null): T[] {
  if (value === undefined || value === null) return [];
  return Array.isArray(value) ? value : [value];
}

function getAttr(node: XmlNode | undefined | null, name: string): string {
  if (!node) return '';
  const value = node[`@_${name}`];
  return typeof value === 'string' || typeof value === 'number' ? String(value) : '';
}

function getNum(node: XmlNode | undefined | null, name: string): number {
  const value = getAttr(node, name);
  return value ? Number(value) : 0;
}

function getComprobanteRoot(xml: string): XmlNode {
  const parsed = parser.parse(xml) as Record<string, unknown>;
  const comprobante = parsed.Comprobante as XmlNode | undefined;
  if (!comprobante) {
    throw new Error('No se encontró el nodo Comprobante');
  }
  return comprobante;
}

function getTimbre(comprobante: XmlNode): XmlNode | null {
  const complemento = comprobante.Complemento as XmlNode | undefined;
  if (!complemento) return null;
  const timbre = complemento.TimbreFiscalDigital as XmlNode | undefined;
  return timbre ?? null;
}

function summarizeDifference(xmlValue: number, calcValue: number) {
  return `XML ${xmlValue.toFixed(2)} vs cálculo ${calcValue.toFixed(2)}.`;
}

export function detectCfdiProfile(xml: string): CFDIProfile {
  const comprobante = getComprobanteRoot(xml);
  const complemento = comprobante.Complemento as XmlNode | undefined;
  const hasPagos = complemento
    ? Object.keys(complemento).some((key) => key.toLowerCase().includes('pagos'))
    : false;
  if (hasPagos) return 'pagos';

  const conceptosContainer = comprobante.Conceptos as XmlNode | undefined;
  const conceptos = asArray((conceptosContainer?.Concepto as XmlNode | XmlNode[] | undefined));
  if (getAttr(comprobante, 'TipoDeComprobante') === 'I' || conceptos.length > 0) {
    return 'ingreso';
  }

  return 'unknown';
}

export function buildCfdiData(xml: string): CFDIData {
  const comprobante = getComprobanteRoot(xml);
  const canonical = normalizeCfdi(xml);
  const emisor = comprobante.Emisor as XmlNode | undefined;
  const receptor = comprobante.Receptor as XmlNode | undefined;
  const timbre = getTimbre(comprobante);
  const conceptosContainer = comprobante.Conceptos as XmlNode | undefined;
  const conceptoNodes = asArray((conceptosContainer?.Concepto as XmlNode | XmlNode[] | undefined));
  const conceptos = canonical.conceptos.map((concepto, index): CFDIConcept => ({
    ...canonicalConceptToCfdiConcept(concepto),
    claveProdServ: getAttr(conceptoNodes[index], 'ClaveProdServ'),
  }));
  const impuestosGlobales = canonicalSummaryTaxesToCfdi(canonical.resumenImpuestos);

  const data: CFDIData = {
    version: getAttr(comprobante, 'Version'),
    fecha: getAttr(comprobante, 'Fecha'),
    uuid: getAttr(timbre, 'UUID'),
    emisor: getAttr(emisor, 'Nombre') || getAttr(emisor, 'Rfc'),
    receptor: getAttr(receptor, 'Nombre') || getAttr(receptor, 'Rfc'),
    subtotal: getNum(comprobante, 'SubTotal'),
    descuento: getNum(comprobante, 'Descuento'),
    total: getNum(comprobante, 'Total'),
    conceptos,
    impuestosGlobales,
    subtotalCalculado: conceptos.reduce((acc, concepto) => acc + concepto.importe, 0),
    totalCalculado: 0,
    hallazgos: [],
    findings: [],
    impactedConceptIndexes: [],
    taxAuditGroups: [],
    verdict: {
      status: 'clean',
      title: 'Sin discrepancias detectadas',
      summary: 'Los importes principales cuadran con el cálculo actual.',
    },
    supportText: '',
  };

  const sumaTraslados = impuestosGlobales.reduce((acc, tax) => acc + tax.importe, 0);
  data.totalCalculado = data.subtotal - data.descuento + sumaTraslados;
  enrichCfdiWithMathDiagnosis(data, canonical);

  const conceptWarnings = conceptos
    .map((concepto, index) => ({ concepto, index }))
    .filter(({ concepto }) => concepto.diferencia !== 0)
    .sort((a, b) => b.concepto.diferencia - a.concepto.diferencia)
    .slice(0, 3);

  conceptWarnings.forEach(({ concepto, index }) => {
    data.findings.push({
      id: `concept-${index}`,
      severity: concepto.diferencia > 0.01 ? 'critical' : 'warning',
      title: `Importe inconsistente en concepto ${index + 1}`,
      summary: `${concepto.descripcion}: ${summarizeDifference(concepto.importe, concepto.importeCalculado)}`,
      declared: String(concepto.importe),
      expected: String(concepto.importeCalculado),
    });
    if (!data.impactedConceptIndexes.includes(index)) data.impactedConceptIndexes.push(index);
  });

  const taxGroupMap = new Map<string, TaxAuditGroup>();

  conceptos.forEach((concepto, conceptIndex) => {
    concepto.impuestos.forEach((impuesto) => {
      const key = `${impuesto.impuesto}|${impuesto.tipoFactor}|${impuesto.tasaOCuota}`;
      const current = taxGroupMap.get(key) ?? {
        key,
        impuesto: impuesto.impuesto,
        tipoFactor: impuesto.tipoFactor,
        tasaOCuota: impuesto.tasaOCuota,
        importeDetalle: 0,
        importeAgrupado: 0,
        diferencia: 0,
        conceptos: [],
      };
      current.importeDetalle += impuesto.importe;
      if (!current.conceptos.includes(conceptIndex)) current.conceptos.push(conceptIndex);
      taxGroupMap.set(key, current);
    });
  });

  impuestosGlobales.forEach((impuesto) => {
    const key = `${impuesto.impuesto}|${impuesto.tipoFactor}|${impuesto.tasaOCuota}`;
    const current = taxGroupMap.get(key) ?? {
      key,
      impuesto: impuesto.impuesto,
      tipoFactor: impuesto.tipoFactor,
      tasaOCuota: impuesto.tasaOCuota,
      importeDetalle: 0,
      importeAgrupado: 0,
      diferencia: 0,
      conceptos: [],
    };
    current.importeAgrupado += impuesto.importe;
    taxGroupMap.set(key, current);
  });

  data.taxAuditGroups = Array.from(taxGroupMap.values())
    .map((group) => ({ ...group, diferencia: group.importeAgrupado - group.importeDetalle }))
    .sort((a, b) => Math.abs(b.diferencia) - Math.abs(a.diferencia));

  data.taxAuditGroups
    .filter((group) => Math.abs(group.diferencia) !== 0)
    .slice(0, 3)
    .forEach((group) => {
      data.findings.push({
        id: `tax-group-${group.key}`,
        severity: Math.abs(group.diferencia) > 0.01 ? 'critical' : 'warning',
        title: `Diferencia en traslado ${group.impuesto} ${(group.tasaOCuota * 100).toFixed(2)}%`,
        summary: `Detalle ${group.importeDetalle.toFixed(2)} vs agrupado ${group.importeAgrupado.toFixed(2)}.`,
      });
      group.conceptos.forEach((index) => {
        if (!data.impactedConceptIndexes.includes(index)) data.impactedConceptIndexes.push(index);
      });
    });

  data.impactedConceptIndexes.sort((a, b) => a - b);

  if (data.findings.length === 0 && data.hallazgos.length === 0) {
    data.hallazgos = [];
  }

  const uniqueFindings = new Map<string, AuditFinding>();
  data.findings.forEach((finding) => {
    const key = `${finding.severity}|${finding.title}|${finding.summary}`;
    if (!uniqueFindings.has(key)) uniqueFindings.set(key, finding);
  });

  data.findings = Array.from(uniqueFindings.values()).sort((a, b) => {
    if (a.severity !== b.severity) return a.severity === 'critical' ? -1 : 1;
    return a.title.localeCompare(b.title, 'es');
  });

  const criticalFindings = data.findings.filter((finding) => finding.severity === 'critical').length;
  const warningFindings = data.findings.filter((finding) => finding.severity === 'warning').length;

  if (criticalFindings > 0) {
    data.verdict = {
      status: 'critical',
      title: 'CFDI con discrepancias críticas',
      summary: `Se detectaron ${criticalFindings} hallazgo(s) críticos que requieren revisión operativa.`,
    };
  } else if (warningFindings > 0) {
    data.verdict = {
      status: 'review',
      title: 'CFDI requiere revisión',
      summary: `Hay ${warningFindings} alerta(s) menores, probablemente asociadas a redondeo o captura.`,
    };
  }

  data.supportText = [
    data.verdict.title,
    data.verdict.summary,
    ...data.findings.slice(0, 5).map((finding) => `${finding.title}: ${finding.summary}`),
  ].join('\n');

  return data;
}
