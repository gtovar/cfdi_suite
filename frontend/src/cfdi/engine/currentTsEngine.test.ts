import { describe, expect, it } from 'vitest';
import * as publicApi from '../public';
import { analyzeCfdiWithCurrentTsEngine } from './currentTsEngine';

const CFDI_NS = 'http://www.sat.gob.mx/cfd/4';
const TFD_NS = 'http://www.sat.gob.mx/TimbreFiscalDigital';
const PAGOS20_NS = 'http://www.sat.gob.mx/Pagos20';

function buildIngresoXml() {
  return `<?xml version="1.0" encoding="UTF-8"?>
  <cfdi:Comprobante xmlns:cfdi="${CFDI_NS}" xmlns:tfd="${TFD_NS}" Version="4.0" TipoDeComprobante="I" Fecha="2026-04-17T10:00:00" SubTotal="100.00" Total="116.00" Moneda="MXN">
    <cfdi:Emisor Rfc="AAA010101AAA" Nombre="EMISOR SA DE CV" />
    <cfdi:Receptor Rfc="BBB010101BBB" Nombre="RECEPTOR SA DE CV" UsoCFDI="G03" />
    <cfdi:Conceptos>
      <cfdi:Concepto ClaveProdServ="10101504" Cantidad="1" Descripcion="Servicio" ValorUnitario="100.00" Importe="100.00" ObjetoImp="02">
        <cfdi:Impuestos>
          <cfdi:Traslados>
            <cfdi:Traslado Base="100.00" Impuesto="002" TipoFactor="Tasa" TasaOCuota="0.160000" Importe="16.00" />
          </cfdi:Traslados>
        </cfdi:Impuestos>
      </cfdi:Concepto>
    </cfdi:Conceptos>
    <cfdi:Impuestos>
      <cfdi:Traslados>
        <cfdi:Traslado Base="100.00" Impuesto="002" TipoFactor="Tasa" TasaOCuota="0.160000" Importe="16.00" />
      </cfdi:Traslados>
    </cfdi:Impuestos>
    <cfdi:Complemento>
      <tfd:TimbreFiscalDigital UUID="INGRESO-UUID-123" />
    </cfdi:Complemento>
  </cfdi:Comprobante>`;
}

function buildPagosXml() {
  return `<?xml version="1.0" encoding="UTF-8"?>
  <cfdi:Comprobante xmlns:cfdi="${CFDI_NS}" xmlns:tfd="${TFD_NS}" xmlns:pago20="${PAGOS20_NS}" Version="4.0" TipoDeComprobante="P" Fecha="2026-04-17T10:00:00" SubTotal="0" Total="0" Moneda="XXX">
    <cfdi:Emisor Rfc="AAA010101AAA" Nombre="EMISOR SA DE CV" />
    <cfdi:Receptor Rfc="BBB010101BBB" Nombre="RECEPTOR SA DE CV" UsoCFDI="CP01" />
    <cfdi:Conceptos>
      <cfdi:Concepto ClaveProdServ="84111506" Cantidad="1" Descripcion="Pago" ValorUnitario="0" Importe="0" ObjetoImp="01" />
    </cfdi:Conceptos>
    <cfdi:Complemento>
      <pago20:Pagos Version="2.0">
        <pago20:Pago FechaPago="2026-04-17T10:00:00" FormaDePagoP="03" MonedaP="MXN" Monto="116.00">
          <pago20:DoctoRelacionado IdDocumento="DOC-UUID-001" Serie="A" Folio="123" NumParcialidad="1" ImpPagado="116.00" ImpSaldoInsoluto="0.00" />
        </pago20:Pago>
      </pago20:Pagos>
      <tfd:TimbreFiscalDigital UUID="PAGO-UUID-123" />
    </cfdi:Complemento>
  </cfdi:Comprobante>`;
}

describe('currentTsEngine contract', () => {
  it('exposes only the contract-oriented public analysis API', () => {
    expect(publicApi.analyzeCFDIContract(buildIngresoXml()).profile).toBe('ingreso');
    expect('analyzeCFDI' in publicApi).toBe(false);
  });

  it('returns a clean contract result for ingreso without pago rows', () => {
    const result = publicApi.analyzeCFDIContract(buildIngresoXml());

    expect(result.engine).toBe('current-ts');
    expect(result.profile).toBe('ingreso');
    expect(result.issues).toEqual([]);
    expect(result.cfdi?.uuid).toBe('INGRESO-UUID-123');
    expect(result.ingresoRows).toHaveLength(1);
    expect(result.pagoRows).toEqual([]);
  });

  it('returns a clean contract result for pagos without ingreso rows', () => {
    const result = publicApi.analyzeCFDIContract(buildPagosXml());

    expect(result.engine).toBe('current-ts');
    expect(result.profile).toBe('pagos');
    expect(result.issues).toEqual([]);
    expect(result.cfdi?.uuid).toBe('PAGO-UUID-123');
    expect(result.ingresoRows).toEqual([]);
    expect(result.pagoRows).toHaveLength(1);
  });

  it('reports fatal issues for invalid xml', () => {
    const result = publicApi.analyzeCFDIContract('<cfdi:Comprobante');

    expect(result.cfdi).toBeNull();
    expect(result.issues).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          fatal: true,
        }),
      ]),
    );
  });

  it('degrades to a non-fatal issue when ingreso extraction fails after parsing', () => {
    const result = analyzeCfdiWithCurrentTsEngine(buildIngresoXml(), {
      extractIngresoRows() {
        throw new Error('fallo controlado en ingresos');
      },
      extractPagoRows(xml) {
        return [];
      },
    });

    expect(result.cfdi?.uuid).toBe('INGRESO-UUID-123');
    expect(result.ingresoRows).toEqual([]);
    expect(result.issues).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          code: 'INGRESO_EXTRACTION_FAILED',
          fatal: false,
        }),
      ]),
    );
  });

  it('degrades to a non-fatal issue when pago extraction fails after parsing', () => {
    const result = analyzeCfdiWithCurrentTsEngine(buildPagosXml(), {
      extractIngresoRows(xml) {
        return [];
      },
      extractPagoRows() {
        throw new Error('fallo controlado en pagos');
      },
    });

    expect(result.cfdi?.uuid).toBe('PAGO-UUID-123');
    expect(result.pagoRows).toEqual([]);
    expect(result.issues).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          code: 'PAGO_EXTRACTION_FAILED',
          fatal: false,
        }),
      ]),
    );
  });
});
