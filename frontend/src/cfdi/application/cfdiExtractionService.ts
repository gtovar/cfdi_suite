import { XMLParser } from 'fast-xml-parser';
import type { CFDIIngresoRow, CFDIPagoRow } from './cfdiTypes';

type XmlNode = Record<string, unknown>;
type ProgressReporter = (progress: number, detail: string) => void;

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

export function extractIngresoRowsData(
  xml: string,
  onProgress?: ProgressReporter,
): CFDIIngresoRow[] {
  const comprobante = getComprobanteRoot(xml);
  const timbre = getTimbre(comprobante);
  const emisor = comprobante.Emisor as XmlNode | undefined;
  const receptor = comprobante.Receptor as XmlNode | undefined;
  const conceptosContainer = comprobante.Conceptos as XmlNode | undefined;
  const conceptos = asArray((conceptosContainer?.Concepto as XmlNode | XmlNode[] | undefined));

  const baseRow = {
    uuid: getAttr(timbre, 'UUID'),
    fecha: getAttr(comprobante, 'Fecha'),
    serie: getAttr(comprobante, 'Serie'),
    folio: getAttr(comprobante, 'Folio'),
    rfcEmisor: getAttr(emisor, 'Rfc'),
    nombreEmisor: getAttr(emisor, 'Nombre'),
    rfcReceptor: getAttr(receptor, 'Rfc'),
    nombreReceptor: getAttr(receptor, 'Nombre'),
    usoCfdi: getAttr(receptor, 'UsoCFDI'),
    metodoPago: getAttr(comprobante, 'MetodoPago'),
    formaPago: getAttr(comprobante, 'FormaPago'),
    moneda: getAttr(comprobante, 'Moneda'),
    tipoCambio: getAttr(comprobante, 'TipoCambio'),
    subtotal: getAttr(comprobante, 'SubTotal'),
    descuento: getAttr(comprobante, 'Descuento'),
    total: getAttr(comprobante, 'Total'),
  };

  const rows: CFDIIngresoRow[] = [];
  onProgress?.(0, 'Filas: 0');

  conceptos.forEach((concepto, index) => {
    const conceptBase = {
      ...baseRow,
      claveProdServ: getAttr(concepto, 'ClaveProdServ'),
      cantidad: getAttr(concepto, 'Cantidad'),
      descripcion: getAttr(concepto, 'Descripcion'),
      valorUnitario: getAttr(concepto, 'ValorUnitario'),
      importe: getAttr(concepto, 'Importe'),
      objetoImp: getAttr(concepto, 'ObjetoImp'),
    };

    const impuestos = concepto.Impuestos as XmlNode | undefined;
    const trasladosNode = impuestos?.Traslados as XmlNode | undefined;
    const retencionesNode = impuestos?.Retenciones as XmlNode | undefined;
    const traslados = asArray((trasladosNode?.Traslado as XmlNode | XmlNode[] | undefined));
    const retenciones = asArray((retencionesNode?.Retencion as XmlNode | XmlNode[] | undefined));

    if (traslados.length === 0 && retenciones.length === 0) {
      rows.push({
        ...conceptBase,
        tipoImp: '',
        baseImp: '',
        impuesto: '',
        tipoFactor: '',
        tasaCuota: '',
        importeImp: '',
      });
    } else {
      traslados.forEach((tax) => {
        rows.push({
          ...conceptBase,
          tipoImp: 'Traslado',
          baseImp: getAttr(tax, 'Base'),
          impuesto: getAttr(tax, 'Impuesto'),
          tipoFactor: getAttr(tax, 'TipoFactor'),
          tasaCuota: getAttr(tax, 'TasaOCuota'),
          importeImp: getAttr(tax, 'Importe'),
        });
      });

      retenciones.forEach((tax) => {
        rows.push({
          ...conceptBase,
          tipoImp: 'Retención',
          baseImp: getAttr(tax, 'Base'),
          impuesto: getAttr(tax, 'Impuesto'),
          tipoFactor: getAttr(tax, 'TipoFactor'),
          tasaCuota: getAttr(tax, 'TasaOCuota'),
          importeImp: getAttr(tax, 'Importe'),
        });
      });
    }

    if ((index + 1) % 25 === 0 || index === conceptos.length - 1) {
      onProgress?.(Math.round(((index + 1) / (conceptos.length || 1)) * 100), `Filas: ${rows.length.toLocaleString('es-MX')}`);
    }
  });

  if (conceptos.length === 0) {
    throw new Error('No se encontraron conceptos');
  }

  return rows;
}

export function extractPagoRowsData(
  xml: string,
  onProgress?: ProgressReporter,
): CFDIPagoRow[] {
  const comprobante = getComprobanteRoot(xml);
  const timbre = getTimbre(comprobante);
  const emisor = comprobante.Emisor as XmlNode | undefined;
  const receptor = comprobante.Receptor as XmlNode | undefined;
  const complemento = comprobante.Complemento as XmlNode | undefined;
  const pagosContainer = complemento
    ? Object.entries(complemento).find(([key]) => key.toLowerCase().includes('pagos'))?.[1] as XmlNode | undefined
    : undefined;

  if (!pagosContainer) {
    throw new Error('No se encontró el complemento de pagos o no hay pagos registrados');
  }

  const pagos = asArray((pagosContainer.Pago as XmlNode | XmlNode[] | undefined));
  const rows: CFDIPagoRow[] = [];
  onProgress?.(0, 'Filas: 0');

  pagos.forEach((pago, index) => {
    const doctos = asArray((pago.DoctoRelacionado as XmlNode | XmlNode[] | undefined));
    const fechaPago = getAttr(pago, 'FechaPago');
    const formaPago = getAttr(pago, 'FormaDePagoP') || getAttr(pago, 'FormaPagoP');
    const monedaP = getAttr(pago, 'MonedaP');
    const monto = getAttr(pago, 'Monto');

    if (doctos.length === 0) {
      rows.push({
        uuidCFDI: getAttr(timbre, 'UUID'),
        fechaCFDI: getAttr(comprobante, 'Fecha'),
        rfcEmisor: getAttr(emisor, 'Rfc'),
        rfcReceptor: getAttr(receptor, 'Rfc'),
        fechaPago,
        formaPago,
        monedaP,
        monto,
        uuidDR: '',
        serieFolio: '',
        parcialidad: '',
        impPagado: '',
        saldoInsoluto: '',
        baseDR: '',
        impuestoDR: '',
        tipoFactorDR: '',
        tasaCuotaDR: '',
        importeDR: '',
      });
    } else {
      doctos.forEach((docto) => {
        const baseRow = {
          uuidCFDI: getAttr(timbre, 'UUID'),
          fechaCFDI: getAttr(comprobante, 'Fecha'),
          rfcEmisor: getAttr(emisor, 'Rfc'),
          rfcReceptor: getAttr(receptor, 'Rfc'),
          fechaPago,
          formaPago,
          monedaP,
          monto,
          uuidDR: getAttr(docto, 'IdDocumento'),
          serieFolio: [getAttr(docto, 'Serie'), getAttr(docto, 'Folio')].filter(Boolean).join('-') || 'N/A',
          parcialidad: getAttr(docto, 'NumParcialidad'),
          impPagado: getAttr(docto, 'ImpPagado'),
          saldoInsoluto: getAttr(docto, 'ImpSaldoInsoluto'),
        };

        const impuestosDR = docto.ImpuestosDR as XmlNode | undefined;
        const trasladosDR = asArray(((impuestosDR?.TrasladosDR as XmlNode | undefined)?.TrasladoDR as XmlNode | XmlNode[] | undefined));
        const retencionesDR = asArray(((impuestosDR?.RetencionesDR as XmlNode | undefined)?.RetencionDR as XmlNode | XmlNode[] | undefined));

        if (trasladosDR.length === 0 && retencionesDR.length === 0) {
          rows.push({
            ...baseRow,
            baseDR: '',
            impuestoDR: '',
            tipoFactorDR: '',
            tasaCuotaDR: '',
            importeDR: '',
          });
          return;
        }

        trasladosDR.forEach((tax) => {
          rows.push({
            ...baseRow,
            baseDR: getAttr(tax, 'BaseDR'),
            impuestoDR: getAttr(tax, 'ImpuestoDR'),
            tipoFactorDR: getAttr(tax, 'TipoFactorDR'),
            tasaCuotaDR: getAttr(tax, 'TasaOCuotaDR'),
            importeDR: getAttr(tax, 'ImporteDR'),
          });
        });

        retencionesDR.forEach((tax) => {
          rows.push({
            ...baseRow,
            baseDR: getAttr(tax, 'BaseDR'),
            impuestoDR: getAttr(tax, 'ImpuestoDR'),
            tipoFactorDR: getAttr(tax, 'TipoFactorDR'),
            tasaCuotaDR: getAttr(tax, 'TasaOCuotaDR'),
            importeDR: getAttr(tax, 'ImporteDR'),
          });
        });
      });
    }

    if ((index + 1) % 5 === 0 || index === pagos.length - 1) {
      onProgress?.(Math.round(((index + 1) / (pagos.length || 1)) * 100), `Filas: ${rows.length.toLocaleString('es-MX')}`);
    }
  });

  if (rows.length === 0) {
    throw new Error('No se encontró el complemento de pagos o no hay pagos registrados');
  }

  return rows;
}
