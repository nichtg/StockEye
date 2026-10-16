import type { Choice } from '../../../components/Choice';
import type { NewsArticlesPage } from '../../../api/types';

export type NewsMonth = NonNullable<NewsArticlesPage['months']>[number];

/** "October 2026" from "2026-10": spelled out for speech and the intro line. */
export function monthName(key: string): string {
  const [year, month] = key.split('-').map(Number);
  return new Date(Date.UTC(year ?? 1970, (month ?? 1) - 1, 1)).toLocaleDateString('en-US', {
    month: 'long',
    year: 'numeric',
    timeZone: 'UTC',
  });
}

/** "" (All) plus one choice per month, newest first as the server sends them. Counts are articles. */
export function monthChoices(months: readonly NewsMonth[]): Choice[] {
  return [
    { value: '', label: 'All', name: 'All months' },
    ...months.map((m) => ({
      value: m.month,
      label: m.label,
      name: monthName(m.month),
      count: m.count,
    })),
  ];
}

/** The URL's month if the server listed it, else undefined (so a stale or made-up value means All). */
export function knownMonth(
  value: string | null,
  months: readonly NewsMonth[] | null | undefined,
): string | undefined {
  return value && months?.some((m) => m.month === value) ? value : undefined;
}

/**
 * The phone menu's options: full month names, and "All months" carries the total so the menu reads
 * "All months [744]". The total is the sum of the month counts (every article sits in one month).
 */
export function monthSelectChoices(months: readonly NewsMonth[]): Choice[] {
  return [
    { value: '', label: 'All months', count: months.reduce((sum, m) => sum + m.count, 0) },
    ...months.map((m) => ({ value: m.month, label: monthName(m.month), count: m.count })),
  ];
}
