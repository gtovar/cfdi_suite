import type { AuditFinding } from '../cfdi/public';

export interface XmlSnippetResult {
  fragment: string;
  highlightAttr: string;
}

export type XmlToken =
  | { kind: 'tag'; text: string }
  | { kind: 'attr'; text: string }
  | { kind: 'value'; text: string }
  | { kind: 'value-error'; text: string; expected: string }
  | { kind: 'value-warn'; text: string }
  | { kind: 'punct'; text: string }
  | { kind: 'text'; text: string };

export function extractXmlSnippet(xml: string, finding: AuditFinding): XmlSnippetResult | null {
  if (finding.id.startsWith('catalog-clave-prod-serv-')) {
    const invalidCode = finding.declared;
    if (!invalidCode) return null;
    const searchStr = `ClaveProdServ="${invalidCode}"`;
    const attrPos = xml.indexOf(searchStr);
    if (attrPos === -1) return null;
    const tagStart = xml.lastIndexOf('<cfdi:Concepto', attrPos);
    if (tagStart === -1) return null;
    const tagEnd = xml.indexOf('>', tagStart);
    if (tagEnd === -1) return null;
    return { fragment: xml.slice(tagStart, tagEnd + 1).trim(), highlightAttr: 'ClaveProdServ' };
  }

  if (finding.id.startsWith('sat-rounding-')) {
    const highlightAttr = finding.id.startsWith('sat-rounding-base-') ? 'Base' : 'Importe';
    const fragment = extractGlobalImpuestos(xml);
    return fragment ? { fragment, highlightAttr } : null;
  }

  if (finding.id.startsWith('concept-')) {
    const conceptIndex = Number(finding.id.slice('concept-'.length));
    if (isNaN(conceptIndex)) return null;
    const fragment = extractConcepto(xml, conceptIndex);
    return fragment ? { fragment, highlightAttr: 'Importe' } : null;
  }

  if (finding.id.startsWith('math-')) {
    const parts = finding.id.split('-');
    // format: math-{CODE}-{level}-{conceptIndex}-{taxIndex}
    if (parts.length >= 5 && parts[3] !== 'na') {
      const conceptIndex = Number(parts[3]);
      if (!isNaN(conceptIndex)) {
        const fragment = extractConceptoImpuestos(xml, conceptIndex);
        return fragment ? { fragment, highlightAttr: 'Importe' } : null;
      }
    }
    return null;
  }

  return null;
}

export function findFragmentLines(xml: string, fragment: string): { start: number; end: number } | null {
  const searchFor = fragment.slice(0, Math.min(60, fragment.length)).trim();
  if (!searchFor) return null;
  const offset = xml.indexOf(searchFor);
  if (offset === -1) return null;
  // Count newlines manually — avoids creating a large string slice and array
  let start = 0;
  for (let j = 0; j < offset; j++) {
    if (xml[j] === '\n') start++;
  }
  let fragmentLines = 0;
  for (let j = 0; j < fragment.length; j++) {
    if (fragment[j] === '\n') fragmentLines++;
  }
  return { start, end: start + fragmentLines };
}

export function applyChange(
  xml: string,
  fragment: string,
  attr: string,
  declared: string,
  expected: string,
): string {
  const target = `${attr}="${declared}"`;
  const replacement = `${attr}="${expected}"`;
  const anchor = fragment.slice(0, Math.min(60, fragment.length)).trim();
  const fragStart = xml.indexOf(anchor);
  if (fragStart === -1) return xml.replace(target, replacement);
  const fragEnd = fragStart + fragment.length + 30;
  return (
    xml.slice(0, fragStart) +
    xml.slice(fragStart, Math.min(fragEnd, xml.length)).replace(target, replacement) +
    xml.slice(Math.min(fragEnd, xml.length))
  );
}

function extractGlobalImpuestos(xml: string): string | null {
  const afterConceptos = xml.indexOf('</cfdi:Conceptos>');
  const searchFrom = afterConceptos === -1 ? 0 : afterConceptos;
  const tail = xml.slice(searchFrom);
  const start = tail.indexOf('<cfdi:Impuestos');
  if (start === -1) return null;
  const end = tail.indexOf('</cfdi:Impuestos>', start);
  if (end === -1) return null;
  return tail.slice(start, end + '</cfdi:Impuestos>'.length).trim();
}

function extractConcepto(xml: string, index: number): string | null {
  const openTag = '<cfdi:Concepto';
  const closeTag = '</cfdi:Concepto>';
  let found = -1;
  let pos = 0;
  for (let count = 0; count <= index; count++) {
    const next = xml.indexOf(openTag, pos);
    if (next === -1) return null;
    if (count === index) { found = next; break; }
    pos = next + openTag.length;
  }
  if (found === -1) return null;
  const end = xml.indexOf(closeTag, found);
  if (end === -1) return null;
  return xml.slice(found, end + closeTag.length).trim();
}

function extractConceptoImpuestos(xml: string, conceptIndex: number): string | null {
  const concepto = extractConcepto(xml, conceptIndex);
  if (!concepto) return null;
  const start = concepto.indexOf('<cfdi:Impuestos');
  if (start === -1) return null;
  const end = concepto.indexOf('</cfdi:Impuestos>', start);
  if (end === -1) return null;
  return concepto.slice(start, end + '</cfdi:Impuestos>'.length).trim();
}

export function splitTokensIntoLines(tokens: XmlToken[]): XmlToken[][] {
  const lines: XmlToken[][] = [[]];
  for (const token of tokens) {
    if (!token.text.includes('\n')) {
      lines[lines.length - 1].push(token);
      continue;
    }
    const parts = token.text.split('\n');
    if (parts[0]) lines[lines.length - 1].push({ ...token, text: parts[0] });
    for (let j = 1; j < parts.length; j++) {
      lines.push(parts[j] ? [{ ...token, text: parts[j] }] : []);
    }
  }
  return lines;
}

export function tokenizeXml(
  fragment: string,
  highlightAttr: string,
  declared: string | undefined,
  expected: string | undefined,
): XmlToken[] {
  const tokens: XmlToken[] = [];
  let i = 0;

  while (i < fragment.length) {
    if (fragment[i] !== '<') {
      const start = i;
      while (i < fragment.length && fragment[i] !== '<') i++;
      tokens.push({ kind: 'text', text: fragment.slice(start, i) });
      continue;
    }

    // Comment
    if (fragment.startsWith('<!--', i)) {
      const end = fragment.indexOf('-->', i);
      const endPos = end === -1 ? fragment.length : end + 3;
      tokens.push({ kind: 'text', text: fragment.slice(i, endPos) });
      i = endPos;
      continue;
    }

    // Closing tag
    if (fragment[i + 1] === '/') {
      const end = fragment.indexOf('>', i);
      if (end === -1) { tokens.push({ kind: 'text', text: fragment.slice(i) }); break; }
      tokens.push({ kind: 'punct', text: '</' });
      tokens.push({ kind: 'tag', text: fragment.slice(i + 2, end) });
      tokens.push({ kind: 'punct', text: '>' });
      i = end + 1;
      continue;
    }

    // Opening tag
    tokens.push({ kind: 'punct', text: '<' });
    i++;

    // Tag name
    const tagStart = i;
    while (i < fragment.length) {
      const c = fragment[i];
      if (c === ' ' || c === '\t' || c === '\n' || c === '\r' || c === '/' || c === '>') break;
      i++;
    }
    tokens.push({ kind: 'tag', text: fragment.slice(tagStart, i) });

    // Attributes until end of opening tag
    let tagOpen = true;
    while (i < fragment.length && tagOpen) {
      const c0 = fragment[i];
      if (c0 === '/' && fragment[i + 1] === '>') {
        tokens.push({ kind: 'punct', text: '/>' });
        i += 2;
        tagOpen = false;
      } else if (c0 === '>') {
        tokens.push({ kind: 'punct', text: '>' });
        i++;
        tagOpen = false;
      } else if (c0 === ' ' || c0 === '\t' || c0 === '\n' || c0 === '\r') {
        const start = i;
        while (i < fragment.length) {
          const c = fragment[i];
          if (c !== ' ' && c !== '\t' && c !== '\n' && c !== '\r') break;
          i++;
        }
        tokens.push({ kind: 'text', text: fragment.slice(start, i) });
      } else {
        // Attribute name
        const attrStart = i;
        while (i < fragment.length) {
          const c = fragment[i];
          if (c === '=' || c === '>' || c === ' ' || c === '\t' || c === '\n' || c === '\r') break;
          if (c === '/' && fragment[i + 1] === '>') break;
          i++;
        }
        const attrName = fragment.slice(attrStart, i);
        if (!attrName) { i++; continue; }
        tokens.push({ kind: 'attr', text: attrName });

        if (fragment[i] === '=') {
          tokens.push({ kind: 'punct', text: '=' });
          i++;
          if (fragment[i] === '"') {
            i++; // skip opening quote
            const valStart = i;
            while (i < fragment.length && fragment[i] !== '"') i++;
            const value = fragment.slice(valStart, i);
            if (i < fragment.length) i++; // skip closing quote

            if (attrName === highlightAttr && declared !== undefined && value === declared) {
              if (expected !== undefined) {
                tokens.push({ kind: 'value-error', text: `"${value}"`, expected });
              } else {
                tokens.push({ kind: 'value-warn', text: `"${value}"` });
              }
            } else {
              tokens.push({ kind: 'value', text: `"${value}"` });
            }
          }
        }
      }
    }
  }

  return tokens;
}
