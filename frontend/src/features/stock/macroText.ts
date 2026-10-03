import type { MacroReportOut, Reliability } from '../../api/types';
import { formatPct } from '../../lib/format';

export const NOT_ENOUGH_NEWS = 'Not enough news yet to analyse this stock.';

export const RELIABILITY_LABEL: Record<Reliability, string> = {
  likely_real: 'Likely real',
  weak_evidence: 'Weak evidence',
  could_be_chance: 'Could be chance',
};

const LEAD = /^(?:Likely a real effect|Weak evidence|Could be chance): ?(\S)/;

/**
 * The backend writes reliability sentences as "Likely a real effect: if news had no influence ...".
 * The UI shows that label as a chip instead, so drop it from the text and keep the rest.
 */
export function stripReliabilityLead(text: string): string {
  return text.replace(LEAD, (_m, first: string) => first.toUpperCase());
}

export function regimeSentence(label: NonNullable<MacroReportOut['regime']>['label']): string {
  switch (label) {
    case 'more_positive_than_usual':
      return 'News over the last 30 days is more positive than usual.';
    case 'more_negative_than_usual':
      return 'News over the last 30 days is more negative than usual.';
    case 'typical':
      return 'News over the last 30 days is about as positive as usual.';
  }
}

/** Market-adjusted 2-day move from a fraction (0.021 means 2.1% better than expected). */
export function moveText(fraction: number): string {
  const size = formatPct(Math.abs(fraction) * 100);
  if (size === formatPct(0)) return 'In line with expected';
  return `${size} ${fraction > 0 ? 'better' : 'worse'} than expected`;
}

export function pValueText(p: number | null): string {
  if (p == null) return '–';
  return p < 0.001 ? 'under 0.001' : p.toFixed(3);
}

export function newsEventsPhrase(count: number): string {
  return `Based on ${String(count)} news ${count === 1 ? 'event' : 'events'}`;
}

export type Scope = NonNullable<MacroReportOut['primary_scope']>;
