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

const line = (
  id: IndicatorId,
  label: string,
  term: TermId,
  lineStyle: LineStyle,
  width: number,
  tone: IndicatorDef['tone'],
): IndicatorDef => ({ id, label, term, lineStyle, width, tone, pane: 'overlay', seriesKeys: [id] });

/** The single source of truth for how each indicator looks, in legend and chart alike. */
export const INDICATORS: IndicatorDef[] = [
  line('vwap', 'VWAP', 'vwap', LineStyle.Dotted, 2, 'ink'),
  line('sma20', 'SMA 20', 'sma', LineStyle.Solid, 1, 'ink2'),
  line('sma50', 'SMA 50', 'sma', LineStyle.Solid, 2, 'ink'),
  line('ema9', 'EMA 9', 'ema', LineStyle.Dashed, 1, 'ink3'),
  line('ema21', 'EMA 21', 'ema', LineStyle.Dashed, 1.5, 'ink'),
  {
    ...line('bollinger', 'Bollinger', 'bollinger', LineStyle.Solid, 1, 'ink3'),
    seriesKeys: ['bollinger_upper', 'bollinger_lower'],
  },
  { ...line('rsi', 'RSI', 'rsi', LineStyle.Solid, 1.5, 'ink'), pane: 'sub' },
  {
    ...line('macd', 'MACD', 'macd', LineStyle.Solid, 1.5, 'ink'),
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
