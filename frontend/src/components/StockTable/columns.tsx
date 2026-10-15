import Box from '@mui/material/Box';
import type { ReactNode } from 'react';
import { OutlookCell } from '../../features/watchlist/Outlook';
import { Sparkline } from '../../features/watchlist/Sparkline';
import type { TermId } from '../../glossary';
import { formatCompactCurrency, formatNumber, formatPrice } from '../../lib/format';
import { Direction } from '../Direction';
import { Term } from '../Term';
import { StaleNote } from './StaleNote';
import {
  SORT_KEYS,
  type SortKey,
  type SortState,
  type StockRow,
  type TableColumns,
} from './sortFilter';

/** Every column after the symbol. The symbol is always first, so it is not in the model. */
export type ColumnId =
  'country' | 'cap' | 'pe' | 'traded' | 'last' | 'change' | 'trend' | 'outlook';

/** The per-list metrics Discover can add to its base columns. */
export type ExtraColumnId = Extract<ColumnId, 'pe' | 'traded'>;

export interface ColumnDef {
  label: string;
  /** Sort key when the header sorts; absent for plain headers. */
  sortKey?: SortKey;
  term?: TermId;
  align?: 'right';
  cell: (row: StockRow) => ReactNode;
  /** The phone layout's line under the price; columns without it are table-only. */
  mobile?: (row: StockRow) => ReactNode;
}

const peText = (row: StockRow) =>
  row.pe_ratio == null ? null : formatNumber(row.pe_ratio, row.exchange, { digits: 1 });
const tradedText = (row: StockRow) =>
  row.avg_traded_value == null
    ? null
    : formatCompactCurrency(row.avg_traded_value, row.currency, row.exchange);

export const COLUMNS: Record<ColumnId, ColumnDef> = {
  country: { label: 'Country', sortKey: 'country', cell: (row) => row.country ?? '–' },
  cap: {
    label: 'Market cap',
    sortKey: 'cap',
    term: 'market_cap',
    align: 'right',
    cell: (row) => formatCompactCurrency(row.market_cap, row.currency, row.exchange),
  },
  pe: {
    label: 'P/E',
    sortKey: 'pe',
    term: 'pe_ratio',
    align: 'right',
    cell: (row) => peText(row) ?? '–',
    mobile: (row) => {
      const text = peText(row);
      return text == null ? null : (
        <>
          <Term id="pe_ratio" label="P/E">
            P/E
          </Term>{' '}
          {text}
        </>
      );
    },
  },
  traded: {
    label: 'Avg daily trading',
    sortKey: 'traded',
    term: 'avg_traded_value',
    align: 'right',
    cell: (row) => tradedText(row) ?? '–',
    mobile: (row) => {
      const text = tradedText(row);
      return text == null ? null : (
        <>
          <Term id="avg_traded_value" label="Avg daily trading">
            Avg daily trading
          </Term>{' '}
          {text}
        </>
      );
    },
  },
  last: {
    label: 'Last',
    sortKey: 'last',
    align: 'right',
    cell: (row) => (
      <>
        <Box sx={{ color: 'ink', fontWeight: 500 }}>
          {formatPrice(row.last_price, row.currency, row.exchange)}
        </Box>
        <StaleNote row={row} />
      </>
    ),
  },
  change: {
    label: '1W change',
    sortKey: 'change',
    align: 'right',
    cell: (row) => <Direction value={row.change_1w_pct} variant="pill" />,
  },
  trend: { label: '1W trend', cell: (row) => <Sparkline values={row.sparkline} /> },
  outlook: {
    label: 'Outlook',
    sortKey: 'outlook',
    term: 'outlook',
    cell: (row) => <OutlookCell lean={row.lean} />,
  },
};

export const WATCHLIST_COLUMNS: readonly ColumnId[] = [
  'country',
  'last',
  'change',
  'trend',
  'outlook',
];

/** Discover adds market cap, and at most one metric of the list's own after it. */
export function discoverColumns(extra?: ExtraColumnId): readonly ColumnId[] {
  return ['country', 'cap', ...(extra ? [extra] : []), 'last', 'change', 'trend', 'outlook'];
}

/** The sort keys a table can show: the symbol plus the sortable columns it has. */
export function visibleSortKeys(columns: readonly ColumnId[]): SortKey[] {
  return [
    'symbol',
    ...columns.flatMap((id) => {
      const key = COLUMNS[id].sortKey;
      return key ? [key] : [];
    }),
  ];
}

/**
 * The sort keys each table offers, in menu order. Discover shows every column; the watchlist only
 * the ones in its own column model (so market cap, P/E and trading value stay Discover-only).
 */
export function sortKeysFor(columns: TableColumns): readonly SortKey[] {
  if (columns === 'discover') return SORT_KEYS;
  const shown = visibleSortKeys(WATCHLIST_COLUMNS);
  return SORT_KEYS.filter((k) => shown.includes(k));
}

/**
 * The shared sort as it applies to one table: a sort on a column this table does not show is
 * ignored, so that list keeps its own order.
 */
export function effectiveSort(
  sort: SortState | null,
  columns: readonly ColumnId[],
): SortState | null {
  return sort && visibleSortKeys(columns).includes(sort.key) ? sort : null;
}
