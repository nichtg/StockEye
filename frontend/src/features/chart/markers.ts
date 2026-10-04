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
