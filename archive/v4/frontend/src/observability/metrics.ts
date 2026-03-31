/**
 * Performance metrics tracking
 */

import { logger } from './logger';

/**
 * Track page load performance
 */
export function trackPageLoad(pageName: string): void {
  // Use Performance API if available
  if (typeof window === 'undefined' || !window.performance) {
    return;
  }

  // Wait for page to fully load
  if (document.readyState === 'complete') {
    recordMetrics(pageName);
  } else {
    window.addEventListener('load', () => recordMetrics(pageName));
  }
}

function recordMetrics(pageName: string): void {
  const entries = performance.getEntriesByType('navigation');
  if (entries.length === 0) return;

  const timing = entries[0] as PerformanceNavigationTiming;

  logger.info('page_load', {
    page: pageName,
    dns_ms: Math.round(timing.domainLookupEnd - timing.domainLookupStart),
    tcp_ms: Math.round(timing.connectEnd - timing.connectStart),
    ttfb_ms: Math.round(timing.responseStart - timing.requestStart),
    dom_interactive_ms: Math.round(timing.domInteractive - timing.startTime),
    dom_complete_ms: Math.round(timing.domComplete - timing.startTime),
    load_event_ms: Math.round(timing.loadEventEnd - timing.startTime),
  });
}

/**
 * Track component render time
 */
export function trackRender(componentName: string, startTime: number): void {
  const duration = performance.now() - startTime;

  if (duration > 100) {
    // Only log slow renders (>100ms)
    logger.warn('slow_render', {
      component: componentName,
      duration_ms: Math.round(duration),
    });
  }
}

/**
 * Create a performance mark and measure
 */
export function measureOperation(name: string): () => void {
  const startMark = `${name}-start`;
  const endMark = `${name}-end`;

  performance.mark(startMark);

  return () => {
    performance.mark(endMark);
    performance.measure(name, startMark, endMark);

    const entries = performance.getEntriesByName(name, 'measure');
    if (entries.length > 0) {
      logger.info('operation_measured', {
        operation: name,
        duration_ms: Math.round(entries[0].duration),
      });
    }

    // Cleanup
    performance.clearMarks(startMark);
    performance.clearMarks(endMark);
    performance.clearMeasures(name);
  };
}
