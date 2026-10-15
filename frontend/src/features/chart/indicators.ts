import { LineStyle } from 'lightweight-charts';
import type { RangeKey } from '../../api/types';
import type { TermId } from '../../glossary';
import { readStored, writeStored } from '../../lib/storage';

export type IndicatorId =
  'vwap' | 'sma20' | 'sma50' | 'ema9' | 'ema21' | 'bollinger' | 'rsi' | 'macd';

export interface IndicatorDef {
  id: IndicatorId;
  label: string;
  term: TermId;
  /** One plain-English line shown on hover and keyboard focus of the toolbar chip. */
  hint: (range: RangeKey) => string;
  /** Line style on the chart; the legend swatch is drawn from the same value. */
  lineStyle: LineStyle;
  /** Pixels. Half pixels are valid on the canvas even though the typings only list integers. */
  width: number;
  /** Palette key; indicators differ by dash and weight, never hue. */
  tone: 'ink' | 'ink2' | 'ink3';
  pane: 'overlay' | 'sub';
  /** Keys of `ChartData.indicators` this indicator draws. */
  seriesKeys: string[];
}

const line = (spec: {
  id: IndicatorId;
  label: string;
  term: TermId;
  hint: IndicatorDef['hint'];
  lineStyle: LineStyle;
  width: number;
  tone: IndicatorDef['tone'];
}): IndicatorDef => ({ ...spec, pane: 'overlay', seriesKeys: [spec.id] });

const fixed = (text: string) => () => text;

/** The single source of truth for how each indicator looks, in legend and chart alike. */
export const INDICATORS: IndicatorDef[] = [
  line({
    id: 'vwap',
    label: 'VWAP',
    term: 'vwap',
    hint: (range) => vwapVariant(range).hint,
    lineStyle: LineStyle.Dotted,
    width: 2,
    tone: 'ink',
  }),
  line({
    id: 'sma20',
    label: 'SMA 20',
    term: 'sma',
    hint: fixed('Average closing price over the last 20 trading days.'),
    lineStyle: LineStyle.Solid,
    width: 1,
    tone: 'ink2',
  }),
  line({
    id: 'sma50',
    label: 'SMA 50',
    term: 'sma',
    hint: fixed('Average closing price over the last 50 trading days, a slower trend line.'),
    lineStyle: LineStyle.Solid,
    width: 2,
    tone: 'ink',
  }),
  line({
    id: 'ema9',
    label: 'EMA 9',
    term: 'ema',
    hint: fixed('Average of the last 9 days that weights recent days more, so it turns quickly.'),
    lineStyle: LineStyle.Dashed,
    width: 1,
    tone: 'ink3',
  }),
  line({
    id: 'ema21',
    label: 'EMA 21',
    term: 'ema',
    hint: fixed('Average of the last 21 days that weights recent days more.'),
    lineStyle: LineStyle.Dashed,
    width: 1.5,
    tone: 'ink',
  }),
  {
    ...line({
      id: 'bollinger',
      label: 'Bollinger',
      term: 'bollinger',
      hint: fixed('A band around the 20-day average that widens when the price swings more.'),
      lineStyle: LineStyle.Solid,
      width: 1,
      tone: 'ink3',
    }),
    seriesKeys: ['bollinger_upper', 'bollinger_lower'],
  },
  {
    ...line({
      id: 'rsi',
      label: 'RSI',
      term: 'rsi',
      hint: fixed('A 0 to 100 gauge of recent buying or selling pressure; shown in its own panel.'),
      lineStyle: LineStyle.Solid,
      width: 1.5,
      tone: 'ink',
    }),
    pane: 'sub',
  },
  {
    ...line({
      id: 'macd',
      label: 'MACD',
      term: 'macd',
      hint: fixed(
        'Momentum from the gap between a fast and a slow average; shown in its own panel.',
      ),
      lineStyle: LineStyle.Solid,
      width: 1.5,
      tone: 'ink',
    }),
    pane: 'sub',
    seriesKeys: ['macd', 'macd_signal', 'macd_histogram'],
  },
];

/** What every chart request asks for: toggling an indicator then never refetches. */
export const ALL_INDICATORS = INDICATORS.map((i) => i.id).join(',');

/** SVG stroke-dasharray matching a chart line style, for legend swatches. */
export function dashArray(style: LineStyle): string | undefined {
  if (style === LineStyle.Dotted) return '1 3';
  if (style === LineStyle.Dashed) return '4 3';
  return undefined;
}

/**
 * Daily ranges (6M and longer) have no intraday session to reset on, so the API anchors VWAP at
 * the first bar of the range. The short ranges use hourly bars and a daily VWAP.
 */
export function vwapVariant(range: RangeKey): { label: string; term: TermId; hint: string } {
  if (range === '1W' || range === '1M') {
    return {
      label: 'VWAP (daily)',
      term: 'vwap',
      hint: 'Average price paid, weighted by volume, restarting each trading day.',
    };
  }
  return {
    label: 'VWAP (from range start)',
    term: 'anchored_vwap',
    hint: 'Average price paid since the first day shown on the chart, weighted by volume.',
  };
}

export const DEFAULT_INDICATORS: IndicatorId[] = ['vwap', 'sma50'];
export const INDICATORS_STORAGE_KEY = 'stockeye.chart-indicators';

const IDS = new Set<string>(INDICATORS.map((i) => i.id));

/** Keeps only known ids, in the canonical display order. */
export function canonicalSelection(ids: readonly unknown[]): IndicatorId[] {
  const wanted = new Set(ids.filter((v): v is string => typeof v === 'string' && IDS.has(v)));
  return INDICATORS.filter((i) => wanted.has(i.id)).map((i) => i.id);
}

/** Stored selection; anything unusable falls back to the default. */
export function parseIndicatorSelection(raw: string | null): IndicatorId[] {
  if (raw == null) return DEFAULT_INDICATORS;
  try {
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? canonicalSelection(parsed) : DEFAULT_INDICATORS;
  } catch {
    return DEFAULT_INDICATORS;
  }
}

export function loadIndicatorSelection(): IndicatorId[] {
  return readStored(INDICATORS_STORAGE_KEY, parseIndicatorSelection, DEFAULT_INDICATORS);
}

export function saveIndicatorSelection(selection: IndicatorId[]): void {
  writeStored(INDICATORS_STORAGE_KEY, selection);
}
