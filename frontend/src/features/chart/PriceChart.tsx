import Box from '@mui/material/Box';
import { useMemo, useRef } from 'react';
import type { ChartData } from '../../api/types';
import type { Exchange } from '../../lib/exchange';
import { useColorMode } from '../../theme/colorModeContext';
import { radius, tokens } from '../../theme/tokens';
import { ChartA11yTable } from './ChartA11yTable';
import { chartOptions } from './chartOptions';
import { ChartTooltip } from './ChartTooltip';
import { INDICATORS, type IndicatorId } from './indicators';
import type { MarkerKind } from './markers';
import { SUB_PANE_HEIGHT, TIME_AXIS_HEIGHT, buildSeriesSpecs, markerData } from './model';
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
}

export function PriceChart({
  data,
  selection,
  currency,
  exchange,
  baseHeight,
  sentences,
  shownMarkers,
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
  const candles = useChartSeries(chart, specs, baseHeight, `${data.symbol}|${data.range}`);
  useSeriesMarkers(candles, markers);
  const cursor = useChartCursor(chart, candles, hostRef, { data, currency, exchange, sentences });

  const ctx = { currency, exchange };
  return (
    <Box
      // The chart canvas is not focusable by itself; this wrapper makes the bars reachable by keyboard.
      tabIndex={0}
      role="group"
      aria-label="Price chart. Use the left and right arrow keys to move between bars."
      onKeyDown={cursor.onKeyDown}
      onBlur={cursor.onBlur}
      sx={{ position: 'relative', borderRadius: radius.lg, outlineOffset: 2 }}
    >
      <Box
        ref={hostRef}
        role="img"
        aria-label={chartSummary(data.symbol, data.range, data.candles, ctx)}
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
      <ChartA11yTable candles={data.candles} {...ctx} announcement={cursor.announce} />
    </Box>
  );
}
