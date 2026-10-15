import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Link from '@mui/material/Link';
import Skeleton from '@mui/material/Skeleton';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableContainer from '@mui/material/TableContainer';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import TableSortLabel from '@mui/material/TableSortLabel';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import useMediaQuery from '@mui/material/useMediaQuery';
import { useTheme } from '@mui/material/styles';
import { useMemo } from 'react';
import type { ReactNode } from 'react';
import { Link as RouterLink, useNavigate } from 'react-router';
import { ExchangeTag } from '../../features/search/ExchangeTag';
import { Sparkline } from '../../features/watchlist/Sparkline';
import { visuallyHidden } from '../../lib/a11y';
import { radius } from '../../theme/tokens';
import { Direction } from '../Direction';
import { Term } from '../Term';
import { COLUMNS, effectiveSort, type ColumnId } from './columns';
import { filterRows, sortRows, type SortKey, type SortState, type StockRow } from './sortFilter';
import { formatPrice } from '../../lib/format';
import type { TableState } from './useTableState';

interface ListProps {
  rows: StockRow[];
  /** The columns after the symbol, in order: headers, cells, mobile lines and sort keys all follow it. */
  columns: readonly ColumnId[];
  /** Names the table (and the mobile list) for assistive tech. */
  ariaLabel: string;
  /** The per-row control: remove for the watchlist, a star toggle for Discover. */
  renderAction: (row: StockRow) => ReactNode;
  /** Names the action column for screen readers, since its header is visually empty. */
  actionLabel: string;
}

export interface StockTableProps extends ListProps {
  state: TableState;
  /** Render nothing when the country filter hides every row (the page explains it once). */
  quietWhenEmpty?: boolean;
}

interface ViewProps extends ListProps {
  /** This table's own sort: null when the shared sort is on a column it does not show. */
  sort: SortState | null;
  onSort: (key: SortKey) => void;
}

const UNAVAILABLE = 'Data unavailable';
const numCell = { textAlign: 'right', whiteSpace: 'nowrap' } as const;

function isUnavailable(row: StockRow): boolean {
  return row.status === 'unavailable' || row.last_price == null;
}

// Symbols and names come from third parties: they are only ever rendered as text, and the path
// segment is encoded.
function stockPath(symbol: string): string {
  return `/stock/${encodeURIComponent(symbol)}`;
}

function SymbolLink({ row, showCountry = false }: { row: StockRow; showCountry?: boolean }) {
  return (
    <Box sx={{ minWidth: 0 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
        <Link
          component={RouterLink}
          to={stockPath(row.symbol)}
          underline="none"
          sx={{ fontWeight: 600, color: 'ink', '&:hover': { textDecoration: 'underline' } }}
        >
          {row.symbol}
        </Link>
        {row.exchange && <ExchangeTag exchange={row.exchange} />}
      </Box>
      {row.name && (
        <Typography variant="body2" noWrap sx={{ color: 'ink3', maxWidth: 260 }}>
          {row.name}
        </Typography>
      )}
      {showCountry && row.country && (
        <Typography variant="caption" component="div" sx={{ color: 'ink3' }}>
          {row.country}
        </Typography>
      )}
    </Box>
  );
}

function UnavailableText({ row }: { row: StockRow }) {
  return (
    <Tooltip title={row.status_reason ?? 'We could not load this stock right now.'}>
      <Typography
        variant="body2"
        component="span"
        tabIndex={0}
        sx={{ color: 'ink3', cursor: 'help', textDecoration: 'underline dotted' }}
      >
        {UNAVAILABLE}
      </Typography>
    </Tooltip>
  );
}

interface HeadProps {
  sort: SortState | null;
  onSort: (key: SortKey) => void;
}

function SortHeader({
  sortKey,
  children,
  term,
  align,
  sort,
  onSort,
}: HeadProps & { sortKey: SortKey; children: string; term?: ReactNode; align?: 'right' }) {
  const active = sort?.key === sortKey;
  const dir = active ? sort.dir : undefined;
  return (
    <TableCell sx={align === 'right' ? numCell : undefined} sortDirection={dir ?? false}>
      <TableSortLabel
        active={active}
        direction={dir ?? 'asc'}
        onClick={() => {
          onSort(sortKey);
        }}
      >
        {children}
      </TableSortLabel>
      {/* Outside the label: a help button must not sit inside another button. */}
      {term}
    </TableCell>
  );
}

function DesktopTable(props: ViewProps) {
  const { rows, ariaLabel, columns, sort, onSort, renderAction, actionLabel } = props;
  const navigate = useNavigate();
  return (
    <TableContainer sx={{ border: 1, borderColor: 'line', borderRadius: radius.lg }}>
      <Table aria-label={ariaLabel}>
        <TableHead>
          <TableRow>
            <SortHeader sortKey="symbol" sort={sort} onSort={onSort}>
              Symbol
            </SortHeader>
            {columns.map((id) => {
              const col = COLUMNS[id];
              const term = col.term && <Term id={col.term} />;
              return col.sortKey ? (
                <SortHeader
                  key={id}
                  sortKey={col.sortKey}
                  align={col.align}
                  sort={sort}
                  onSort={onSort}
                  term={term}
                >
                  {col.label}
                </SortHeader>
              ) : (
                <TableCell key={id}>{col.label}</TableCell>
              );
            })}
            <TableCell sx={{ width: 48 }}>
              <Box component="span" sx={visuallyHidden}>
                {actionLabel}
              </Box>
            </TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.map((row) => (
            <TableRow
              key={row.symbol}
              hover
              onClick={(e) => {
                // The link is the keyboard and screen-reader target; this is the mouse shortcut.
                if (e.target instanceof Element && e.target.closest('a,button')) return;
                void navigate(stockPath(row.symbol));
              }}
              sx={{ cursor: 'pointer', '&:last-child td': { borderBottom: 0 } }}
            >
              <TableCell>
                <SymbolLink row={row} />
              </TableCell>
              {isUnavailable(row) ? (
                <TableCell colSpan={columns.length}>
                  <UnavailableText row={row} />
                </TableCell>
              ) : (
                columns.map((id) => (
                  <TableCell key={id} sx={COLUMNS[id].align === 'right' ? numCell : undefined}>
                    {COLUMNS[id].cell(row)}
                  </TableCell>
                ))
              )}
              <TableCell sx={{ textAlign: 'right' }}>{renderAction(row)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );
}

function MobileList({ rows, ariaLabel, renderAction, columns }: ListProps) {
  return (
    <Box
      component="ul"
      aria-label={ariaLabel}
      sx={{ listStyle: 'none', m: 0, p: 0, borderTop: 1, borderColor: 'line' }}
    >
      {rows.map((row) => {
        const unavailable = isUnavailable(row);
        return (
          <Box
            component="li"
            key={row.symbol}
            sx={{
              display: 'flex',
              alignItems: 'center',
              gap: 1,
              py: 1.5,
              borderBottom: 1,
              borderColor: 'line',
            }}
          >
            <Box sx={{ flex: 1, minWidth: 0 }}>
              <SymbolLink row={row} showCountry />
            </Box>
            {unavailable ? (
              <UnavailableText row={row} />
            ) : (
              <>
                <Box sx={{ textAlign: 'right' }}>
                  <Box sx={{ color: 'ink', fontWeight: 500, fontSize: '0.9375rem' }}>
                    {formatPrice(row.last_price, row.currency, row.exchange)}
                  </Box>
                  {columns.map((id) => {
                    const line = COLUMNS[id].mobile?.(row);
                    return line ? (
                      <Typography key={id} variant="caption" component="div" sx={{ color: 'ink3' }}>
                        {line}
                      </Typography>
                    ) : null;
                  })}
                  <Typography variant="body2" component="div">
                    <Direction value={row.change_1w_pct} variant="pill" />
                  </Typography>
                </Box>
                <Sparkline values={row.sparkline} width={64} />
              </>
            )}
            {renderAction(row)}
          </Box>
        );
      })}
    </Box>
  );
}

/**
 * The sortable stock table shared by the watchlist and Discover: a table on wide screens, a
 * compact list on phones. Sort and filter state live with the caller (in the URL), so one control
 * bar can drive several tables.
 */
export function StockTable({ quietWhenEmpty = false, ...props }: StockTableProps) {
  const theme = useTheme();
  const compact = useMediaQuery(theme.breakpoints.down('sm'));
  const { state, columns } = props;
  const sort = effectiveSort(state.sort, columns);
  const sortKey = sort?.key ?? null;
  const sortDir = sort?.dir ?? 'asc';
  const rows = useMemo(
    () => sortRows(filterRows(props.rows, state.country), sortKey, sortDir),
    [props.rows, state.country, sortKey, sortDir],
  );

  if (rows.length === 0 && state.country) {
    if (quietWhenEmpty) return null;
    return (
      <NoStocksFromCountry
        country={state.country}
        onShowAll={() => {
          state.setCountry(null);
        }}
      />
    );
  }
  return compact ? (
    <MobileList {...props} rows={rows} />
  ) : (
    <DesktopTable {...props} rows={rows} sort={sort} onSort={state.toggleSort} />
  );
}

/** The line shown when the country filter leaves nothing to list. */
export function NoStocksFromCountry({
  country,
  onShowAll,
}: {
  country: string;
  onShowAll: () => void;
}) {
  return (
    <Box sx={{ py: 2 }}>
      <Typography sx={{ mb: 1.5 }}>No stocks from {country} here.</Typography>
      <Button variant="outlined" size="small" onClick={onShowAll}>
        Show all countries
      </Button>
    </Box>
  );
}
export function StockTableSkeleton({ label }: { label: string }) {
  return (
    <Box aria-busy="true" role="status" aria-label={label}>
      {Array.from({ length: 5 }, (_, i) => (
        <Skeleton key={i} variant="rounded" height={56} sx={{ mb: 1, borderRadius: radius.sm }} />
      ))}
    </Box>
  );
}
