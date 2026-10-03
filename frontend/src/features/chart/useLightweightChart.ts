import {
  createChart,
  type ChartOptions,
  type DeepPartial,
  type IChartApi,
} from 'lightweight-charts';
import { useEffect, useRef, useState, type RefObject } from 'react';

/**
 * Creates the chart once for the host element and keeps it sized and styled. Later option changes
 * (theme, height) are applied in place, so the zoom and scroll position survive them.
 */
export function useLightweightChart(
  hostRef: RefObject<HTMLDivElement | null>,
  options: DeepPartial<ChartOptions>,
): IChartApi | null {
  const [chart, setChart] = useState<IChartApi | null>(null);
  const latest = useRef(options);
  useEffect(() => {
    latest.current = options;
  });

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const created = createChart(host, { ...latest.current, width: host.clientWidth });
    const observer = new ResizeObserver(() => {
      created.applyOptions({ width: host.clientWidth });
    });
    observer.observe(host);
    setChart(created);
    return () => {
      observer.disconnect();
      created.remove();
      setChart(null);
    };
  }, [hostRef]);

  useEffect(() => {
    chart?.applyOptions(options);
  }, [chart, options]);

  return chart;
}
