import type { OverviewRow } from '../../api/types';

export const SORT_KEYS = ['symbol', 'country', 'last', 'change', 'outlook', 'cap'] as const;
export type SortKey = (typeof SORT_KEYS)[number];
export type SortDir = 'asc' | 'desc';
export interface SortState {
  key: SortKey;
  dir: SortDir;
}

export const SORT_LABELS: Record<SortKey, string> = {
  symbol: 'Symbol',
  country: 'Country',
  last: 'Last price',
  change: '1W change',
  outlook: 'Outlook',
  cap: 'Market cap',
};

const OUTLOOK_ORDER = { bearish: 0, neutral: 1, bullish: 2 } as const;

export type TableColumns = 'watchlist' | 'discover';

/** Market cap is shown, and so sortable, on Discover only. */
export function sortKeysFor(columns: TableColumns): readonly SortKey[] {
  return columns === 'discover' ? SORT_KEYS : SORT_KEYS.filter((k) => k !== 'cap');
}

export function parseSortKey(
  value: string | null,
  allowed: readonly SortKey[] = SORT_KEYS,
): SortKey | null {
  return allowed.find((k) => k === value) ?? null;
}

export function parseSortDir(value: string | null): SortDir {
  return value === 'desc' ? 'desc' : 'asc';
}

function valueOf(row: OverviewRow, key: SortKey): string | number | null {
  switch (key) {
    case 'symbol':
      return row.symbol;
    case 'country':
      return row.country;
    case 'last':
      return row.last_price;
    case 'change':
      return row.change_1w_pct;
    case 'outlook':
      return row.lean ? OUTLOOK_ORDER[row.lean] : null;
    case 'cap':
      return row.market_cap;
  }
}

function compareValues(a: string | number, b: string | number): number {
  if (typeof a === 'string' && typeof b === 'string') {
    return a.localeCompare(b, undefined, { sensitivity: 'base' });
  }
  return Number(a) - Number(b);
}

/**
 * A sorted copy. Missing values always go last, whichever way the column is sorted, so a
 * descending sort never buries real figures under blanks. Ties keep their original order.
 */
export function sortRows(
  rows: readonly OverviewRow[],
  key: SortKey | null,
  dir: SortDir,
): OverviewRow[] {
  if (!key) return [...rows];
  const sign = dir === 'asc' ? 1 : -1;
  return [...rows].sort((a, b) => {
    const va = valueOf(a, key);
    const vb = valueOf(b, key);
    if (va == null && vb == null) return 0;
    if (va == null) return 1;
    if (vb == null) return -1;
    return sign * compareValues(va, vb);
  });
}

/** Rows from one country, or all rows when `country` is null. */
export function filterRows(rows: readonly OverviewRow[], country: string | null): OverviewRow[] {
  if (!country) return [...rows];
  return rows.filter((r) => r.country === country);
}

export interface CountryOption {
  country: string;
  count: number;
}

/** Each country present in the rows with its row count, alphabetical. A symbol on several lists counts once. */
export function countryOptions(rows: readonly OverviewRow[]): CountryOption[] {
  const counts = new Map<string, number>();
  const seen = new Set<string>();
  for (const row of rows) {
    if (!row.country || seen.has(row.symbol)) continue;
    seen.add(row.symbol);
    counts.set(row.country, (counts.get(row.country) ?? 0) + 1);
  }
  return [...counts]
    .map(([country, count]) => ({ country, count }))
    .sort((a, b) => a.country.localeCompare(b.country, undefined, { sensitivity: 'base' }));
}

/** Asc, then desc, then off; a different column starts again at asc. */
export function nextSort(current: SortState | null, key: SortKey): SortState | null {
  if (current?.key !== key) return { key, dir: 'asc' };
  return current.dir === 'asc' ? { key, dir: 'desc' } : null;
}
