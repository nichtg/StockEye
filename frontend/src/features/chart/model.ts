import {
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
  LineStyle,
  type CandlestickData,
  type HistogramData,
  type LineData,
  type LineWidth,
  type SeriesMarker,
  type SeriesDefinition,
  type SeriesPartialOptionsMap,
  type Time,
} from 'lightweight-charts';
import type { Candle, ChartData, ChartMarker, SeriesPoint } from '../../api/types';
import type { Tokens } from '../../theme/tokens';
import type { Band } from './bandFill';
import { INDICATORS, type IndicatorDef, type IndicatorId } from './indicators';
import { isDrawnMarker, newsMarkerSize } from './markers';

export const SUB_PANE_HEIGHT = 100;
/** The time scale under the lowest pane. */
export const TIME_AXIS_HEIGHT = 28;

/** The API sends "YYYY-MM-DD" (a business day) or UNIX seconds; the chart accepts both as `Time`. */
function chartTime(value: string | number): Time {
  return value as Time;
}

export function candleData(candles: Candle[]): CandlestickData[] {
  return candles.map((c) => ({
    time: chartTime(c.time),
    open: c.open,
    high: c.high,
    low: c.low,
    close: c.close,
  }));
}

export function volumeData(candles: Candle[]): HistogramData[] {
  return candles.map((c) => ({ time: chartTime(c.time), value: c.volume }));
}

export function lineData(points: SeriesPoint[] | undefined): LineData[] {
  return (points ?? []).map((p) => ({ time: chartTime(p.time), value: p.value }));
}

/** 8-digit hex with the given opacity, for the canvas (which has no CSS opacity per series). */
export function withAlpha(hex: string, alpha: number): string {
  const clean = hex.replace('#', '');
  const a = Math.round(Math.min(1, Math.max(0, alpha)) * 255)
    .toString(16)
    .padStart(2, '0');
  return `#${clean}${a}`;
}

interface SpecData {
  Candlestick: CandlestickData;
  Histogram: HistogramData;
  Line: LineData;
}

/** Everything needed to draw one series; `chart.addSeries` is the only thing missing. */
export interface SpecOf<K extends keyof SpecData> {
  /** Stable identity: the same key on the next build means "update", never "recreate". */
  key: string;
  kind: K;
  /** What `chart.addSeries` instantiates. */
  definition: SeriesDefinition<K>;
  pane: number;
  options: SeriesPartialOptionsMap[K];
  data: SpecData[K][];
  /** What `data` and `options` derive from; the series is rewritten only when one changes. */
  deps: readonly unknown[];
  scaleMargins?: { top: number; bottom: number };
  /** Horizontal guide lines (the RSI 30/70 levels). */
  levels?: { prices: number[]; color: string };
  /** Shaded area between this line and `lower` (Bollinger bands). */
  band?: Band;
}

export type SeriesSpec = SpecOf<'Candlestick'> | SpecOf<'Histogram'> | SpecOf<'Line'>;

function lineSpec(
  key: string,
  points: SeriesPoint[] | undefined,
  p: Tokens,
  look: { color: string; width: number; style: LineStyle },
  pane = 0,
  extra: Partial<SpecOf<'Line'>> = {},
): SpecOf<'Line'> {
  return {
    key,
    kind: 'Line',
    definition: LineSeries,
    pane,
    options: {
      color: look.color,
      // Half pixels draw fine on the canvas; the typings only list whole ones.
      lineWidth: look.width as LineWidth,
      lineStyle: look.style,
      lastValueVisible: false,
      priceLineVisible: false,
      crosshairMarkerVisible: false,
    },
    data: lineData(points),
    deps: [points, p],
    ...extra,
  };
}

function overlaySpecs(def: IndicatorDef, data: ChartData, p: Tokens): SpecOf<'Line'>[] {
  const look = { color: p[def.tone], width: def.width, style: def.lineStyle };
  return def.seriesKeys.map((key) => {
    const points = data.indicators[key];
    if (key !== 'bollinger_upper') return lineSpec(key, points, p, look);
    const lower = data.indicators.bollinger_lower;
    const spec = lineSpec(key, points, p, look, 0, {
      band: { lower: lineData(lower), color: withAlpha(p.ink, 0.06) },
    });
    return { ...spec, deps: [points, lower, p] };
  });
}

function rsiSpec(def: IndicatorDef, data: ChartData, p: Tokens, pane: number): SpecOf<'Line'> {
  const look = { color: p[def.tone], width: def.width, style: def.lineStyle };
  const spec = lineSpec('rsi', data.indicators.rsi, p, look, pane, {
    levels: { prices: [30, 70], color: p.ink3 },
    scaleMargins: { top: 0.1, bottom: 0.1 },
  });
  return {
    ...spec,
    options: {
      ...spec.options,
      title: 'RSI',
      lastValueVisible: true,
      autoscaleInfoProvider: () => ({ priceRange: { minValue: 0, maxValue: 100 } }),
    },
  };
}

function macdSpecs(def: IndicatorDef, data: ChartData, p: Tokens, pane: number): SeriesSpec[] {
  const histogram = data.indicators.macd_histogram;
  const hist: SpecOf<'Histogram'> = {
    key: 'macd_histogram',
    kind: 'Histogram',
    definition: HistogramSeries,
    pane,
    options: {
      lastValueVisible: false,
      priceLineVisible: false,
      priceFormat: { type: 'price', precision: 2, minMove: 0.01 },
    },
    // Up and down at 60% opacity, as in the design spec.
    data: (histogram ?? []).map((pt) => ({
      time: chartTime(pt.time),
      value: pt.value,
      color: withAlpha(pt.value >= 0 ? p.up : p.down, 0.6),
    })),
    deps: [histogram, p],
  };
  const look = { color: p[def.tone], width: def.width, style: def.lineStyle };
  const main = lineSpec('macd', data.indicators.macd, p, look, pane);
  const signal = lineSpec(
    'macd_signal',
    data.indicators.macd_signal,
    p,
    { ...look, color: p.ink3, style: LineStyle.Dashed },
    pane,
  );
  return [
    hist,
    { ...main, options: { ...main.options, title: 'MACD', lastValueVisible: true } },
    signal,
  ];
}

/**
 * Pure description of every series the chart should show for this data and selection: candles,
 * volume, the chosen overlays on the price pane, then RSI and MACD in their own panes.
 */
export function buildSeriesSpecs(
  data: ChartData,
  selection: readonly IndicatorId[],
  p: Tokens,
): SeriesSpec[] {
  const specs: SeriesSpec[] = [
    {
      key: 'candles',
      kind: 'Candlestick',
      definition: CandlestickSeries,
      pane: 0,
      options: {
        // Up candles are hollow (the pane colour) so shape, not just colour, tells direction.
        upColor: p.raised,
        borderUpColor: p.up,
        wickUpColor: p.up,
        downColor: p.down,
        borderDownColor: p.down,
        wickDownColor: p.down,
        priceLineVisible: false,
        lastValueVisible: true,
      },
      data: candleData(data.candles),
      deps: [data.candles, p],
      scaleMargins: { top: 0.08, bottom: 0.22 },
    },
    {
      key: 'volume',
      kind: 'Histogram',
      definition: HistogramSeries,
      pane: 0,
      options: {
        priceFormat: { type: 'volume' },
        priceScaleId: 'volume',
        lastValueVisible: false,
        priceLineVisible: false,
        // Volume bars are ink3 at 35% opacity, regardless of direction.
        color: withAlpha(p.ink3, 0.35),
      },
      data: volumeData(data.candles),
      deps: [data.candles, p],
      scaleMargins: { top: 0.82, bottom: 0 },
    },
  ];
  let pane = 1; // RSI and MACD each get their own pane below the price
  for (const def of INDICATORS) {
    if (!selection.includes(def.id)) continue;
    if (def.id === 'rsi') specs.push(rsiSpec(def, data, p, pane++));
    else if (def.id === 'macd') specs.push(...macdSpecs(def, data, p, pane++));
    else specs.push(...overlaySpecs(def, data, p));
  }
  return specs;
}

function compareTime(a: string | number, b: string | number): number {
  if (typeof a === 'number' && typeof b === 'number') return a - b;
  return String(a).localeCompare(String(b));
}

/** Maps API markers to chart markers. Output is sorted by time, as the chart requires. */
export function markerData(
  markers: ChartMarker[],
  p: Tokens,
  visible?: (kind: ChartMarker['kind']) => boolean,
): SeriesMarker<Time>[] {
  const out: { at: string | number; marker: SeriesMarker<Time> }[] = [];
  for (const m of markers) {
    if (visible && !visible(m.kind)) continue;
    if (!isDrawnMarker(m)) continue;
    const time = chartTime(m.time);
    let marker: SeriesMarker<Time>;
    switch (m.kind) {
      case 'earnings':
        marker = { time, position: 'aboveBar', shape: 'circle', color: p.ink, text: 'E' };
        break;
      case 'dividend':
        marker = { time, position: 'belowBar', shape: 'circle', color: p.ink2, text: 'D' };
        break;
      case 'split':
        marker = { time, position: 'aboveBar', shape: 'square', color: p.ink2, text: 'S' };
        break;
      case 'pattern':
        marker =
          m.bias === 'bullish'
            ? { time, position: 'belowBar', shape: 'arrowUp', color: p.up }
            : { time, position: 'aboveBar', shape: 'arrowDown', color: p.down };
        break;
      case 'news':
        // Direction in tone, size by impact; the tooltip says it in words.
        marker = {
          time,
          position: 'aboveBar',
          shape: 'circle',
          color: m.car_0_1 == null ? p.ink : m.car_0_1 >= 0 ? p.up : p.down,
          size: newsMarkerSize(m.car_0_1),
        };
        break;
    }
    out.push({ at: m.time, marker });
  }
  return out.sort((a, b) => compareTime(a.at, b.at)).map((o) => o.marker);
}
