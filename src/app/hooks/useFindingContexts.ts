import { useMemo } from 'react';
import type { CFDIData } from '../../cfdi/public';
import type { CorrectionStep, FindingConceptLink, FindingContext } from '../../components/FindingsSidebar';
import { formatSignedExact } from '../utils/cfdiFormatters';
import { getConceptPriorityScore, parseMathFindingId } from '../utils/findingUtils';

function buildConceptLink(cfdi: CFDIData, conceptIndex: number, reason: string): FindingConceptLink | null {
  const concept = cfdi.conceptos[conceptIndex];
  if (!concept) return null;
  return { concept, conceptIndex, reason };
}

function sortConceptLinks(links: FindingConceptLink[]) {
  return [...links].sort((left, right) => {
    const scoreDiff = getConceptPriorityScore(right.concept) - getConceptPriorityScore(left.concept);
    if (scoreDiff !== 0) return scoreDiff;
    return left.conceptIndex - right.conceptIndex;
  });
}

export function useFindingContexts(cfdi: CFDIData | null) {
  return useMemo<FindingContext[]>(() => {
    if (!cfdi) return [];

    return cfdi.findings.map((finding) => {
      if (finding.id.startsWith('tax-group-')) {
        const groupKey = finding.id.slice('tax-group-'.length);
        const group = cfdi.taxAuditGroups.find((g) => g.key === groupKey);
        if (!group) {
          return {
            findingId: finding.id,
            explanation: 'Este hallazgo fiscal no pudo mapearse al grupo de impuestos actual.',
            relationshipLabel: 'Sin relacion visible',
            conceptLinks: [],
          };
        }

        const conceptLinks = sortConceptLinks(
          group.conceptos
            .map((conceptIndex) =>
              buildConceptLink(
                cfdi,
                conceptIndex,
                `Participa en el grupo fiscal ${group.impuesto} ${group.tipoFactor} ${(group.tasaOCuota * 100).toFixed(2)}% comparado contra el agrupado.`,
              ),
            )
            .filter((link): link is FindingConceptLink => Boolean(link)),
        );

        return {
          findingId: finding.id,
          explanation: 'Compara la suma de traslados por concepto contra el impuesto agrupado del comprobante. Los conceptos de abajo participan en ese mismo grupo fiscal.',
          relationshipLabel: `${group.conceptos.length} concepto(s) en el grupo ${group.impuesto} ${(group.tasaOCuota * 100).toFixed(2)}%`,
          whyItMatters: 'Si este grupo no cuadra, el impuesto total del comprobante puede verse correcto a simple vista pero estar distribuido de forma inconsistente en el detalle.',
          differenceLabel: `Dif. real ${formatSignedExact(group.diferencia)}`,
          conceptLinks,
        };
      }

      if (finding.id.startsWith('concept-')) {
        const conceptIndex = Number(finding.id.slice('concept-'.length));
        const concepto = cfdi.conceptos[conceptIndex];
        const correctionSteps: CorrectionStep[] = [
          { text: 'Identifica este CFDI en tu sistema de facturación por su UUID', copyValue: cfdi.uuid, copyLabel: 'Copiar UUID' },
          {
            text: concepto
              ? `El concepto "${concepto.descripcion || `#${conceptIndex + 1}`}" tiene Importe="${concepto.importe.toFixed(2)}", pero el cálculo correcto (Cantidad × ValorUnitario) da "${concepto.importeCalculado.toFixed(2)}"`
              : `El concepto #${conceptIndex + 1} tiene un importe que no coincide con Cantidad × ValorUnitario`,
            copyValue: concepto?.importeCalculado.toFixed(2),
            copyLabel: 'Copiar valor correcto',
          },
          { text: 'En el portal del SAT, cancela este CFDI con motivo "01 — Comprobante emitido con errores con relación" y emite uno nuevo corregido' },
          { text: 'Sube el nuevo XML aquí para verificar que el error quedó resuelto' },
        ];
        return {
          findingId: finding.id,
          explanation: 'Este hallazgo señala directamente un concepto cuyo importe no coincide con el cálculo esperado.',
          relationshipLabel: '1 concepto directamente afectado',
          whyItMatters: 'Si el importe del concepto está mal, puede arrastrar discrepancias en subtotal, total o impuestos del comprobante.',
          conceptLinks: [buildConceptLink(cfdi, conceptIndex, 'El importe de este concepto no coincide con cantidad × valor unitario.')]
            .filter((link): link is FindingConceptLink => Boolean(link)),
          correctionSteps,
        };
      }

      if (finding.id.startsWith('math-')) {
        const parsed = parseMathFindingId(finding.id);
        if (parsed?.conceptIndex !== null && parsed?.conceptIndex !== undefined) {
          const concepto = cfdi.conceptos[parsed.conceptIndex];
          const reason =
            parsed.code === 'LINE_TAX_MISMATCH'
              ? 'El traslado de este concepto no coincide con Base × Tasa.'
              : parsed.code === 'LINE_TAX_NOT_RECALCULATED'
                ? 'Este traslado no se recalcula automáticamente por su tipo de factor.'
                : 'Este hallazgo matemático apunta a un concepto específico.';

          const correctionSteps: CorrectionStep[] =
            parsed.code === 'LINE_TAX_MISMATCH'
              ? [
                  { text: 'Identifica este CFDI en tu sistema de facturación', copyValue: cfdi.uuid, copyLabel: 'Copiar UUID' },
                  {
                    text: concepto
                      ? `En el concepto "${concepto.descripcion || `#${parsed.conceptIndex + 1}`}", el importe del traslado no coincide con Base × Tasa. Revisa el cálculo en tu sistema de facturación.`
                      : `El concepto #${parsed.conceptIndex + 1} tiene un traslado que no coincide con Base × Tasa.`,
                  },
                  { text: 'Cancela este CFDI en el portal del SAT (motivo "01 — errores con relación") y emite uno nuevo corregido' },
                  { text: 'Sube el nuevo XML aquí para verificar' },
                ]
              : [];

          return {
            findingId: finding.id,
            explanation: 'Este hallazgo matemático sí apunta a un concepto específico dentro del comprobante.',
            relationshipLabel: '1 concepto directamente afectado',
            whyItMatters: 'Este concepto es una pista directa del origen del problema matemático detectado por el sistema.',
            conceptLinks: [buildConceptLink(cfdi, parsed.conceptIndex, reason)].filter(
              (link): link is FindingConceptLink => Boolean(link),
            ),
            correctionSteps: correctionSteps.length > 0 ? correctionSteps : undefined,
          };
        }

        const declaredVal = finding.declared != null ? parseFloat(finding.declared) : null;
        const expectedVal = finding.expected != null ? parseFloat(finding.expected) : null;
        const diff = declaredVal != null && expectedVal != null ? declaredVal - expectedVal : null;

        return {
          findingId: finding.id,
          explanation: 'Este hallazgo resume una discrepancia global del comprobante y no señala por sí solo un concepto individual.',
          relationshipLabel: 'Sin concepto directo',
          whyItMatters: 'Sirve para interpretar el estado general del comprobante, pero no para elegir por sí solo un concepto específico.',
          differenceLabel: diff != null ? `Dif. ${formatSignedExact(diff)}` : undefined,
          conceptLinks: [],
        };
      }

      if (finding.id.startsWith('sat-rounding-')) {
        const isBase = finding.id.startsWith('sat-rounding-base-');
        const campo = isBase ? 'base gravable' : 'importe de impuesto';

        const correctionSteps: CorrectionStep[] = [
          {
            text: 'Identifica este CFDI en tu sistema de facturación por su UUID',
            copyValue: cfdi.uuid,
            copyLabel: 'Copiar UUID',
          },
          {
            text: isBase
              ? `En el XML, el atributo Base del nodo cfdi:Traslado global debe cambiar de "${finding.declared}" a "${finding.expected}"`
              : `En el XML, el atributo Importe del nodo cfdi:Traslado global debe cambiar de "${finding.declared}" a "${finding.expected}"`,
            copyValue: finding.expected,
            copyLabel: 'Copiar valor correcto',
          },
          {
            text: 'En el portal del SAT, cancela este CFDI con el motivo "01 — Comprobante emitido con errores con relación" y emite uno nuevo corregido',
          },
          {
            text: 'Descarga el nuevo XML y súbelo aquí para verificar que el error quedó resuelto',
          },
        ];

        return {
          findingId: finding.id,
          explanation:
            `La regla del SAT indica que el ${campo} total del comprobante debe ser igual a la suma de los ${campo}s de cada renglón, redondeada al centavo. ` +
            `En esta factura esa suma no coincide con el total declarado.`,
          relationshipLabel: 'Afecta todos los renglones',
          whyItMatters:
            'Aunque la diferencia suele ser de un centavo, el SAT puede rechazar la factura porque la matemática interna no cumple con la norma oficial de acumulación de impuestos.',
          conceptLinks: [],
          correctionSteps,
        };
      }

      const HEADER_CATALOG_PREFIXES: Record<string, { label: string; catalog: string }> = {
        'catalog-uso-cfdi-': { label: 'Uso de CFDI', catalog: 'c_UsoCFDI' },
        'catalog-metodo-pago-': { label: 'Método de pago', catalog: 'c_MetodoPago' },
        'catalog-forma-pago-': { label: 'Forma de pago', catalog: 'c_FormaPago' },
        'catalog-moneda-': { label: 'Moneda', catalog: 'c_Moneda' },
      };
      const matchedHeaderCatalog = Object.entries(HEADER_CATALOG_PREFIXES).find(([prefix]) =>
        finding.id.startsWith(prefix),
      );
      if (matchedHeaderCatalog) {
        const [, { label, catalog }] = matchedHeaderCatalog;
        const invalidCode = finding.declared ?? '';
        const correctionSteps: CorrectionStep[] = [
          { text: 'Identifica este CFDI en tu sistema de facturación por su UUID', copyValue: cfdi.uuid, copyLabel: 'Copiar UUID' },
          { text: `El código '${invalidCode}' no existe en el catálogo SAT ${catalog}. Consulta el catálogo oficial en el portal del SAT para encontrar el valor correcto.` },
          { text: 'Actualiza el valor en tu sistema de facturación y reemite el CFDI corregido' },
        ];
        return {
          findingId: finding.id,
          explanation: `El campo ${label} contiene el código '${invalidCode}' que no está registrado en el catálogo SAT ${catalog}.`,
          relationshipLabel: 'Campo de cabecera del comprobante',
          whyItMatters: `El SAT exige valores válidos del catálogo oficial. Un código incorrecto puede causar rechazo del CFDI.`,
          conceptLinks: [],
          correctionSteps,
        };
      }

      if (finding.id.startsWith('catalog-clave-prod-serv-')) {
        const invalidCode = finding.declared ?? '';
        const affectedConcepts = cfdi.conceptos
          .map((c, i) => ({ c, i }))
          .filter(({ c }) => c.claveProdServ === invalidCode)
          .slice(0, 5);
        const conceptLinks = affectedConcepts
          .map(({ i }) => buildConceptLink(cfdi, i, `Usa la clave SAT inválida '${invalidCode}'.`))
          .filter((l): l is FindingConceptLink => Boolean(l));

        const correctionSteps: CorrectionStep[] = [
          { text: 'Identifica este CFDI en tu sistema de facturación por su UUID', copyValue: cfdi.uuid, copyLabel: 'Copiar UUID' },
          { text: `La clave SAT '${invalidCode}' no existe en el catálogo oficial. Consulta el buscador de claves del SAT (sat.gob.mx) para encontrar la clave correcta según el producto o servicio que facturas.` },
          { text: 'Actualiza la clave en tu sistema de facturación y reemite el CFDI corregido' },
        ];

        const totalAfectados = cfdi.conceptos.filter((c) => c.claveProdServ === invalidCode).length;
        return {
          findingId: finding.id,
          explanation: `La clave '${invalidCode}' no está registrada en el catálogo SAT c_ClaveProdServ. El SAT puede rechazar o marcar este CFDI como inválido.`,
          relationshipLabel: `${totalAfectados} concepto(s) afectados`,
          whyItMatters: 'El SAT exige claves válidas del catálogo c_ClaveProdServ para la correcta identificación del producto o servicio gravado.',
          conceptLinks,
          correctionSteps,
        };
      }

      return {
        findingId: finding.id,
        explanation: 'Hallazgo operativo sin relacion detallada con conceptos en esta version.',
        relationshipLabel: 'Sin relacion detallada',
        whyItMatters: 'Aporta contexto operativo, pero no ofrece todavía una ruta directa hacia conceptos específicos.',
        conceptLinks: [],
      };
    });
  }, [cfdi]);
}
