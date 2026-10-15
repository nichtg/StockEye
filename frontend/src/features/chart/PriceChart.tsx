import Box from '@mui/material/Box';
import { useEffect, useMemo, useRef, type KeyboardEvent } from 'react';
import type { ChartData } from '../../api/types';
import type { Exchange } from '../../lib/exchange';
import { useColorMode } from '../../theme/colorModeContext';
import { radius, tokens } from '../../theme/tokens';
import { ChartA11yTable } from './ChartA11yTable';
import { chartOptions } from './chartOptions';
import { ChartTooltip } from './ChartTooltip';
import {
  createNavigator,
  handleNavKey,
  navLimits,
  type ChartNavigator,
  type NavLimits,
  type View,
} from './navigation';
import { INDICATORS, type IndicatorId } from './indicators';
import type { MarkerKind } from './markers';
import { SUB_PANE_HEIGHT, TIME_AXIS_HEIGHT, buildSeriesSpecs, markerData } from './model';
import { startIndex, visibleCandles } from './visible';
import { barLabel, chartSummary, type PatternSentences } from './tooltip';
import { useChartCursor } from './useChartCursor';
import { useChartSeries, useSeriesMarkers } from './useChartSeries';
import { useLightweightChart } from './useLightweightChart';

interface PriceChartProps {
  data: ChartData;
  selection: IndicatorId[];
  currency: string;
  exchange: Exchange;
  /** Height of the main pane in px (420 desktop, 300 mobile). */
  baseHeight: number;
  sentences: PatternSentences;
  /** Marker kinds currently switched on in the legend. */
  shownMarkers: MarkerKind[];
  /** Receives the chart's zoom and pan actions once it exists, and null when it goes away. */
  onNavReady?: (nav: ChartNavigator | null) => void;
  /** Which zoom and pan moves still change the view; reported as the view moves. */
  onNavLimits?: (limits: NavLimits) => void;
}

export function PriceChart({
  data,
  selection,
  currency,
  exchange,
  baseHeight,
  sentences,
  shownMarkers,
  onNavReady,
  onNavLimits,
}: PriceChartProps) {
  const palette = tokens[useColorMode().mode];
  const hostRef = useRef<HTMLDivElement>(null);

  const subPanes = INDICATORS.filter((i) => i.pane === 'sub' && selection.includes(i.id)).length;
  // The panes split what the time axis leaves, so the host is the panes plus the axis.
  const height = baseHeight + subPanes * SUB_PANE_HEIGHT + TIME_AXIS_HEIGHT;
  const firstTime = data.candles[0]?.time;
  const options = useMemo(
    () =>
      chartOptions({
        palette,
        exchange,
        height,
        intraday: data.interval === '1h',
        firstTime,
      }),
    [palette, exchange, height, data.interval, firstTime],
  );
  const specs = useMemo(
    () => buildSeriesSpecs(data, selection, palette),
    [data, selection, palette],
  );
  const markers = useMemo(
    () => markerData(data.markers, palette, (kind) => shownMarkers.includes(kind)),
    [data.markers, palette, shownMarkers],
  );

  const chart = useLightweightChart(hostRef, options);
  // The chart holds all the history; the chosen range only decides where the view starts.
  const barCount = data.candles.length;
  const view = useMemo<View | undefined>(
    () =>
      barCount === 0
        ? undefined
        : { startIndex: startIndex(data.candles, data.visible_from), barCount },
    [data.candles, data.visible_from, barCount],
  );
  const candles = useChartSeries(chart, specs, baseHeight, `${data.symbol}|${data.range}`, view);
  const latest = useRef({ count: data.candles.length, view });
  useEffect(() => {
    latest.current = { count: data.candles.length, view };
  });
  const nav = useRef<ChartNavigator | null>(null);
  const clearCursor = useRef<() => void>(() => undefined);
  useEffect(() => {
    if (!chart) return;
    // Reads through the ref so the actions always see the latest data.
    const base = createNavigator(
      chart,
      () => latest.current.count,
      () => latest.current.view,
    );
    // A moved view makes the keyboard bar cursor stale, so any move clears it first.
    const moved = (run: () => void) => () => {
      clearCursor.current();
      run();
    };
    const navigator: ChartNavigator = {
      zoomIn: moved(base.zoomIn),
      zoomOut: moved(base.zoomOut),
      panLeft: moved(base.panLeft),
      panRight: moved(base.panRight),
      reset: moved(base.reset),
    };
    nav.current = navigator;
    onNavReady?.(navigator);
    return () => {
      nav.current = null;
      onNavReady?.(null);
    };
  }, [chart, onNavReady]);
  useEffect(() => {
    if (!chart) return;
    const report = () => {
      onNavLimits?.(navLimits(chart.timeScale().getVisibleLogicalRange(), latest.current.count));
    };
    report();
    chart.timeScale().subscribeVisibleLogicalRangeChange(report);
    return () => {
      chart.timeScale().unsubscribeVisibleLogicalRangeChange(report);
    };
  }, [chart, onNavLimits, barCount]);
  useSeriesMarkers(candles, markers);
  const cursor = useChartCursor(chart, candles, hostRef, { data, currency, exchange, sentences });

  useEffect(() => {
    clearCursor.current = cursor.clear;
  });
  const ctx = { currency, exchange };
  const shown = useMemo(
    () => visibleCandles(data.candles, data.visible_from),
    [data.candles, data.visible_from],
  );
  const onKeyDown = (e: KeyboardEvent) => {
    if (!handleNavKey(e, nav.current)) cursor.onKeyDown(e);
  };
  return (
    <Box
      // The chart canvas is not focusable by itself; this wrapper makes the bars reachable by keyboard.
      tabIndex={0}
      role="group"
      aria-label="Price chart. Arrow keys move between bars, Shift with arrows scrolls, plus and minus zoom, 0 resets the view."
      onKeyDown={onKeyDown}
      onBlur={cursor.onBlur}
      sx={{
        position: 'relative',
        borderRadius: radius.lg,
        outlineOffset: 2,
        '&:focus-visible': { outline: '2px solid var(--se-ink)' },
      }}
    >
      <Box
        ref={hostRef}
        role="img"
        aria-label={chartSummary(data.symbol, data.range, shown, ctx)}
        sx={{
          height,
          width: '100%',
          borderRadius: radius.lg,
          overflow: 'hidden',
          border: 1,
          borderColor: 'line',
          bgcolor: 'raised',
        }}
      />
      {cursor.tip && (
        <ChartTooltip
          tip={cursor.tip}
          label={barLabel(data.candles[cursor.tip.index]?.time, exchange)}
        />
      )}
      <ChartA11yTable
        candles={shown}
        visibleFrom={data.visible_from}
        {...ctx}
        announcement={cursor.announce}
      />
    </Box>
  );
}
