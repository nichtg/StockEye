import type { ChartMarker, RangeKey } from '../../api/types';
import type { TermId } from '../../glossary';
import { readStored, writeStored } from '../../lib/storage';

export type MarkerKind = ChartMarker['kind'];

export interface MarkerDef {
  kind: MarkerKind;
  glyph: string;
  label: string;
  term: TermId;
}

export const MARKER_DEFS: MarkerDef[] = [
  { kind: 'earnings', glyph: 'E', label: 'Earnings', term: 'earnings' },
  { kind: 'dividend', glyph: 'D', label: 'Dividends', term: 'dividend' },
  { kind: 'split', glyph: 'S', label: 'Splits', term: 'split' },
  { kind: 'pattern', glyph: '▲▼', label: 'Patterns', term: 'pattern_reliability' },
  { kind: 'news', glyph: '●', label: 'News', term: 'news_event' },
];

/** What a kind with nothing in view is called in "No … in this range". */
const EMPTY_NOUN: Record<MarkerKind, string> = {
  earnings: 'earnings',
  dividend: 'dividends',
  split: 'splits',
  pattern: 'patterns',
  news: 'news events',
};

export function emptyMarkerText(kind: MarkerKind): string {
  return `No ${EMPTY_NOUN[kind]} in this range`;
}

/** Neutral (doji-like) patterns are noise on the chart; they stay in the Technical tab. */
export function isDrawnMarker(m: ChartMarker): boolean {
  return m.kind !== 'pattern' || m.bias === 'bullish' || m.bias === 'bearish';
}

/** How many markers of each kind the chart draws for this data, whether switched on or not. */
export function markerCounts(markers: ChartMarker[]): Record<MarkerKind, number> {
  const counts: Record<MarkerKind, number> = {
    earnings: 0,
    dividend: 0,
    split: 0,
    pattern: 0,
    news: 0,
  };
  for (const m of markers) if (isDrawnMarker(m)) counts[m.kind] += 1;
  return counts;
}

/**
 * News dots grow with the size of the market-adjusted 2-day move, in three steps (under 1%,
 * 1 to 3%, over 3%). Steps read better than a continuous scale; an unmeasured event is smallest.
 */
export function newsMarkerSize(car: number | null | undefined): number {
  const move = Math.abs(car ?? 0);
  if (move < 0.01) return 0.6;
  if (move <= 0.03) return 1;
  return 1.6;
}

/** Marker kinds the viewer has explicitly switched on or off. Unset kinds follow the defaults. */
export type MarkerOverrides = Partial<Record<MarkerKind, boolean>>;

export const MARKERS_STORAGE_KEY = 'stockeye.chart-markers';

const KINDS = new Set<string>(MARKER_DEFS.map((m) => m.kind));

/** Patterns are only legible on the short ranges, where there are few candles. */
export function markerDefault(kind: MarkerKind, range: RangeKey): boolean {
  if (kind === 'pattern') return range === '1W' || range === '1M';
  return true;
}

export function markerVisible(
  kind: MarkerKind,
  range: RangeKey,
  overrides: MarkerOverrides,
): boolean {
  return overrides[kind] ?? markerDefault(kind, range);
}

export function parseMarkerOverrides(raw: string | null): MarkerOverrides {
  if (raw == null) return {};
  try {
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) return {};
    const out: MarkerOverrides = {};
    for (const [key, value] of Object.entries(parsed)) {
      if (KINDS.has(key) && typeof value === 'boolean') out[key as MarkerKind] = value;
    }
    return out;
  } catch {
    return {};
  }
}

export function loadMarkerOverrides(): MarkerOverrides {
  return readStored(MARKERS_STORAGE_KEY, parseMarkerOverrides, {});
}

export function saveMarkerOverrides(overrides: MarkerOverrides): void {
  writeStored(MARKERS_STORAGE_KEY, overrides);
}
