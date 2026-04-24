import { useMemo } from 'react';
import type { CFDIData } from '../../cfdi/public';
import type { FindingConceptLink, FindingContext } from '../../components/FindingsSidebar';
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
        return {
          findingId: finding.id,
          explanation: 'Este hallazgo señala directamente un concepto cuyo importe no coincide con el cálculo esperado.',
          relationshipLabel: '1 concepto directamente afectado',
          whyItMatters: 'Si el importe del concepto está mal, puede arrastrar discrepancias en subtotal, total o impuestos del comprobante.',
          conceptLinks: [buildConceptLink(cfdi, conceptIndex, 'El importe de este concepto no coincide con cantidad × valor unitario.')]
            .filter((link): link is FindingConceptLink => Boolean(link)),
        };
      }

      if (finding.id.startsWith('math-')) {
        const parsed = parseMathFindingId(finding.id);
        if (parsed?.conceptIndex !== null && parsed?.conceptIndex !== undefined) {
          const reason =
            parsed.code === 'LINE_TAX_MISMATCH'
              ? 'El traslado de este concepto no coincide con Base × Tasa.'
              : parsed.code === 'LINE_TAX_NOT_RECALCULATED'
                ? 'Este traslado no se recalcula automáticamente por su tipo de factor.'
                : 'Este hallazgo matemático apunta a un concepto específico.';

          return {
            findingId: finding.id,
            explanation: 'Este hallazgo matemático sí apunta a un concepto específico dentro del comprobante.',
            relationshipLabel: '1 concepto directamente afectado',
            whyItMatters: 'Este concepto es una pista directa del origen del problema matemático detectado por el sistema.',
            conceptLinks: [buildConceptLink(cfdi, parsed.conceptIndex, reason)].filter(
              (link): link is FindingConceptLink => Boolean(link),
            ),
          };
        }

        return {
          findingId: finding.id,
          explanation: 'Este hallazgo resume una discrepancia global del comprobante y no señala por sí solo un concepto individual.',
          relationshipLabel: 'Sin concepto directo',
          whyItMatters: 'Sirve para interpretar el estado general del comprobante, pero no para elegir por sí solo un concepto específico.',
          conceptLinks: [],
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
