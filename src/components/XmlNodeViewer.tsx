import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import type { AuditFinding } from '../cfdi/public';
import {
  applyChange,
  extractXmlSnippet,
  findFragmentLines,
  splitTokensIntoLines,
  tokenizeXml,
  type XmlToken,
} from '../lib/xml-snippet';

interface XmlNodeViewerProps {
  finding: AuditFinding | null;
  sourceFile: File | undefined;
  modifiedXml?: string | null;
  onAcceptChange?: (xml: string) => void;
}

function renderToken(
  token: XmlToken,
  i: number,
  showApply: boolean,
  onApply?: () => void,
): ReactNode {
  switch (token.kind) {
    case 'tag':
      return <span key={i} className="text-blue-300">{token.text}</span>;
    case 'attr':
      return <span key={i} className="text-violet-300">{token.text}</span>;
    case 'value':
      return <span key={i} className="text-emerald-300">{token.text}</span>;
    case 'value-error':
      return (
        <span key={i}>
          <span
            className="text-red-400 line-through"
            style={{ animation: 'xml-highlight 1.4s ease-out forwards' }}
          >
            {token.text}
          </span>
          <span className="ml-1 text-emerald-400">&rarr; &quot;{token.expected}&quot;</span>
          {showApply && onApply && (
            <button
              type="button"
              onClick={onApply}
              className="ml-2 rounded px-1.5 py-0.5 text-tiny font-medium bg-emerald-900/50 text-emerald-400 border border-emerald-700/50 hover:bg-emerald-800/50 transition-colors duration-150"
            >
              Aplicar
            </button>
          )}
        </span>
      );
    case 'value-warn':
      return (
        <span
          key={i}
          className="text-amber-400 font-semibold"
          style={{ animation: 'xml-highlight 1.4s ease-out forwards' }}
        >
          {token.text}
        </span>
      );
    case 'punct':
      return <span key={i} className="text-gray-500">{token.text}</span>;
    default:
      return <span key={i} className="text-gray-400">{token.text}</span>;
  }
}

export default function XmlNodeViewer({
  finding,
  sourceFile,
  modifiedXml,
  onAcceptChange,
}: XmlNodeViewerProps) {
  const [xmlContent, setXmlContent] = useState('');

  useEffect(() => {
    if (!sourceFile) { setXmlContent(''); return; }
    sourceFile.text().then(setXmlContent);
  }, [sourceFile]);

  const displayXml = modifiedXml ?? xmlContent ?? '';

  const snippet = useMemo(
    () => (finding && displayXml ? extractXmlSnippet(displayXml, finding) : null),
    [displayXml, finding],
  );

  const highlightRange = useMemo(
    () => (snippet ? findFragmentLines(displayXml, snippet.fragment) : null),
    [displayXml, snippet],
  );

  const canAccept = !!(snippet && finding?.declared && finding?.expected);

  // Tokenization is deferred so React can render the loading state first.
  // tokenizeXml on large XMLs creates ~400k objects — cannot run synchronously in render.
  const [lineTokens, setLineTokens] = useState<XmlToken[][]>([]);
  const [isTokenizing, setIsTokenizing] = useState(false);
  const tokenizeKeyRef = useRef('');

  useEffect(() => {
    if (!displayXml) {
      setLineTokens([]);
      setIsTokenizing(false);
      return;
    }
    const key = `${displayXml.length}|${snippet?.highlightAttr ?? ''}|${finding?.declared ?? ''}`;
    if (key === tokenizeKeyRef.current) return; // same inputs, skip
    tokenizeKeyRef.current = key;
    setIsTokenizing(true);

    const id = setTimeout(() => {
      const tokens = tokenizeXml(
        displayXml,
        snippet?.highlightAttr ?? '',
        finding?.declared,
        finding?.expected,
      );
      setLineTokens(splitTokensIntoLines(tokens));
      setIsTokenizing(false);
    }, 0);
    return () => clearTimeout(id);
  }, [displayXml, snippet?.highlightAttr, finding?.declared, finding?.expected]);

  const parentRef = useRef<HTMLDivElement>(null);

  const virtualizer = useVirtualizer({
    count: lineTokens.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 22,
    overscan: 20,
  });

  // Scroll to finding when finding changes or when tokenization completes
  useEffect(() => {
    if (!highlightRange || lineTokens.length === 0) return;
    virtualizer.scrollToIndex(highlightRange.start, { align: 'center' });
  }, [finding?.id, lineTokens.length]);

  function handleAcceptChange() {
    if (!snippet || !finding?.declared || !finding?.expected) return;
    const newXml = applyChange(
      displayXml,
      snippet.fragment,
      snippet.highlightAttr,
      finding.declared,
      finding.expected,
    );
    onAcceptChange?.(newXml);
  }

  return (
    <div className="flex flex-1 min-h-0 flex-col overflow-hidden bg-gray-950">
      {finding && (
        <div className="shrink-0 px-5 py-2.5 border-b border-gray-800">
          <p className="text-tiny font-medium uppercase tracking-wider text-gray-500">
            {finding.title}
          </p>
        </div>
      )}

      {isTokenizing ? (
        <div className="flex flex-1 items-center justify-center gap-2 text-gray-600 text-xs font-mono uppercase tracking-widest">
          <span className="animate-spin">⟳</span>
          Cargando XML
        </div>
      ) : (
        <div ref={parentRef} className="flex-1 overflow-auto px-2 py-4">
          <pre
            className="font-mono text-tiny leading-relaxed"
            style={{ position: 'relative', height: `${virtualizer.getTotalSize()}px` }}
          >
            {virtualizer.getVirtualItems().map((vRow) => {
              const lineIdx = vRow.index;
              const tokens = lineTokens[lineIdx] ?? [];
              const isHighlighted = highlightRange
                ? lineIdx >= highlightRange.start && lineIdx <= highlightRange.end
                : false;

              return (
                <div
                  key={lineIdx}
                  style={{
                    position: 'absolute',
                    top: 0,
                    left: 0,
                    width: '100%',
                    height: `${vRow.size}px`,
                    transform: `translateY(${vRow.start}px)`,
                  }}
                  className={
                    isHighlighted
                      ? 'bg-amber-400/15 border-l-2 border-amber-400/80 pl-2'
                      : 'pl-[calc(0.5rem+2px)]'
                  }
                >
                  <span className="select-none inline-block w-8 text-right mr-4 text-gray-700 text-tiny">
                    {lineIdx + 1}
                  </span>
                  {tokens.map((t, i) =>
                    renderToken(
                      t,
                      i,
                      canAccept && isHighlighted,
                      canAccept && isHighlighted ? handleAcceptChange : undefined,
                    ),
                  )}
                </div>
              );
            })}
          </pre>
        </div>
      )}
    </div>
  );
}
