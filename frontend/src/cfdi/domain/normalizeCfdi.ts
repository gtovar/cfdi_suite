import { XMLParser, XMLValidator } from 'fast-xml-parser';
import type { CanonicalCfdi, CanonicalConcept, CanonicalTaxLine, CanonicalTaxSummary } from './canonicalCfdi';

type XmlNode = Record<string, unknown>;

const parser = new XMLParser({
  ignoreAttributes: false,
  attributeNamePrefix: '@_',
  removeNSPrefix: true,
  parseTagValue: false,
  trimValues: true,
});

function parseXml(xmlString: string): XmlNode {
  const validation = XMLValidator.validate(xmlString);
  if (validation !== true) {
    throw new Error('XML inválido');
  }

  return parser.parse(xmlString) as XmlNode;
}

function asArray<T>(value: T | T[] | undefined | null): T[] {
  if (value === undefined || value === null) return [];
  return Array.isArray(value) ? value : [value];
}

function getNode(node: XmlNode | undefined | null, key: string): XmlNode | null {
  const value = node?.[key];
  if (!value || Array.isArray(value) || typeof value !== 'object') return null;
  return value as XmlNode;
}

function getChildren(node: XmlNode | undefined | null, key: string): XmlNode[] {
  return asArray(node?.[key] as XmlNode | XmlNode[] | undefined);
}

function getAttr(element: XmlNode | null | undefined, name: string): string | null {
  if (!element) return null;
  const value = element[`@_${name}`];
  if (typeof value === 'string' || typeof value === 'number') return String(value);
  return null;
}

function getNumberAttr(element: XmlNode | null | undefined, name: string): number | null {
  const value = getAttr(element, name);
  if (value === null || value === '') return null;

  const parsed = Number(value);
  return Number.isNaN(parsed) ? null : parsed;
}

function normalizeTaxLine(element: XmlNode): CanonicalTaxLine {
  return {
    base: getNumberAttr(element, 'Base'),
    impuesto: getAttr(element, 'Impuesto'),
    tipoFactor: getAttr(element, 'TipoFactor'),
    tasaOCuota: getNumberAttr(element, 'TasaOCuota'),
    importe: getNumberAttr(element, 'Importe'),
  };
}

function normalizeTaxSummary(container: XmlNode | null): CanonicalTaxSummary {
  if (!container) {
    return {
      traslados: [],
      retenciones: [],
    };
  }

  const trasladosNode = getNode(container, 'Traslados');
  const retencionesNode = getNode(container, 'Retenciones');

  return {
    traslados: getChildren(trasladosNode, 'Traslado').map(normalizeTaxLine),
    retenciones: getChildren(retencionesNode, 'Retencion').map(normalizeTaxLine),
  };
}

function normalizeConcept(element: XmlNode): CanonicalConcept {
  const impuestosNode = getNode(element, 'Impuestos');
  const impuestos = normalizeTaxSummary(impuestosNode);

  return {
    descripcion: getAttr(element, 'Descripcion'),
    cantidad: getNumberAttr(element, 'Cantidad'),
    valorUnitario: getNumberAttr(element, 'ValorUnitario'),
    importe: getNumberAttr(element, 'Importe'),
    objetoImp: getAttr(element, 'ObjetoImp'),
    traslados: impuestos.traslados,
    retenciones: impuestos.retenciones,
  };
}

export function normalizeCfdi(xmlString: string): CanonicalCfdi {
  const xmlDoc = parseXml(xmlString);

  const comprobante = getNode(xmlDoc, 'Comprobante');
  if (!comprobante) {
    throw new Error('No se encontró el nodo Comprobante');
  }

  const conceptosNode = getNode(comprobante, 'Conceptos');
  const impuestosNode = getNode(comprobante, 'Impuestos');

  return {
    version: getAttr(comprobante, 'Version'),
    tipoDeComprobante: getAttr(comprobante, 'TipoDeComprobante'),
    subTotal: getNumberAttr(comprobante, 'SubTotal'),
    total: getNumberAttr(comprobante, 'Total'),
    moneda: getAttr(comprobante, 'Moneda'),
    descuento: getNumberAttr(comprobante, 'Descuento'),
    conceptos: getChildren(conceptosNode, 'Concepto').map(normalizeConcept),
    resumenImpuestos: normalizeTaxSummary(impuestosNode),
  };
}
