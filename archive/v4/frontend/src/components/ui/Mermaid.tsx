/**
 * Mermaid diagram rendering component
 * SVG output is sanitized with DOMPurify to prevent XSS attacks.
 */

import { useEffect, useRef, useState } from 'react';
import DOMPurify from 'dompurify';
import mermaid from 'mermaid';

// Initialize mermaid with custom theme
mermaid.initialize({
  startOnLoad: false,
  theme: 'base',
  themeVariables: {
    primaryColor: '#6366f1',
    primaryTextColor: '#1f2937',
    primaryBorderColor: '#4f46e5',
    lineColor: '#6b7280',
    secondaryColor: '#f3f4f6',
    tertiaryColor: '#fef3c7',
    background: '#ffffff',
    mainBkg: '#ffffff',
    secondBkg: '#f9fafb',
    border1: '#e5e7eb',
    border2: '#d1d5db',
    arrowheadColor: '#6b7280',
    fontFamily: 'ui-sans-serif, system-ui, sans-serif',
    fontSize: '14px',
    actorBkg: '#f3f4f6',
    actorBorder: '#d1d5db',
    actorTextColor: '#1f2937',
    actorLineColor: '#9ca3af',
    signalColor: '#374151',
    signalTextColor: '#1f2937',
    labelBoxBkgColor: '#f9fafb',
    labelBoxBorderColor: '#e5e7eb',
    labelTextColor: '#374151',
    loopTextColor: '#6b7280',
    noteBkgColor: '#fef3c7',
    noteTextColor: '#92400e',
    noteBorderColor: '#fcd34d',
    activationBkgColor: '#e0e7ff',
    activationBorderColor: '#6366f1',
    sequenceNumberColor: '#ffffff',
  },
  sequence: {
    diagramMarginX: 8,
    diagramMarginY: 16,
    actorMargin: 20,
    width: 130,
    height: 70,
    boxMargin: 4,
    boxTextMargin: 4,
    noteMargin: 8,
    messageMargin: 35,
    mirrorActors: false,
    bottomMarginAdj: 2,
    useMaxWidth: true,
    rightAngles: false,
    showSequenceNumbers: false,
    wrap: true,
    wrapPadding: 8,
  },
  flowchart: {
    htmlLabels: true,
    curve: 'basis',
    padding: 16,
    nodeSpacing: 50,
    rankSpacing: 50,
  },
});

interface MermaidProps {
  chart: string;
  className?: string;
}

export function Mermaid({ chart, className = '' }: MermaidProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [svg, setSvg] = useState<string>('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const renderChart = async () => {
      if (!containerRef.current) return;

      try {
        // Generate unique ID for each render
        const id = `mermaid-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
        const { svg: renderedSvg } = await mermaid.render(id, chart.trim());
        // Sanitize SVG to prevent XSS attacks
        const sanitizedSvg = DOMPurify.sanitize(renderedSvg, {
          USE_PROFILES: { svg: true, svgFilters: true },
        });
        setSvg(sanitizedSvg);
        setError(null);
      } catch (err) {
        console.error('Mermaid render error:', err);
        setError(err instanceof Error ? err.message : 'Failed to render diagram');
      }
    };

    renderChart();
  }, [chart]);

  if (error) {
    return (
      <div className={`rounded-lg border border-red-200 bg-red-50 p-4 dark:border-red-800 dark:bg-red-900/20 ${className}`}>
        <p className="text-sm text-red-600 dark:text-red-400">Diagram error: {error}</p>
        <pre className="mt-2 overflow-x-auto text-xs text-gray-600 dark:text-gray-400">{chart}</pre>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className={`overflow-x-auto ${className}`}
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
}

export default Mermaid;
