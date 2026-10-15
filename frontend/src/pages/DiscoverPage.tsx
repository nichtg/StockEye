import SortIcon from '@mui/icons-material/Sort';
import Box from '@mui/material/Box';
import Link from '@mui/material/Link';
import Typography from '@mui/material/Typography';
import { useMemo, useRef } from 'react';
import { QueryRegion } from '../components/QueryRegion';
import { filterRows } from '../components/StockTable/sortFilter';
import {
  discoverColumns,
  effectiveSort,
  type ExtraColumnId,
} from '../components/StockTable/columns';
import { sortPhrase } from '../components/StockTable/sortFilter';
import {
  NoStocksFromCountry,
  StockTable,
  StockTableSkeleton,
} from '../components/StockTable/StockTable';
import { TableControls } from '../components/StockTable/TableControls';
import { useTableState } from '../components/StockTable/useTableState';
import { Term } from '../components/Term';
import { useDiscover } from '../features/discover/useDiscover';
import { WatchStar } from '../features/discover/WatchStar';
import { DataStatusLine } from '../features/stock/StockHeader';
import { useWatchlistSymbols } from '../features/watchlist/useWatchlist';
import { useWatchlistToggle } from '../features/watchlist/useWatchlistToggle';
import { useDocumentTitle } from '../hooks';
import { formatRelative } from '../lib/format';

/** The extra metric each list shows, decided by list id (titles are copy and may change). */
const LIST_COLUMNS: Partial<Record<string, ExtraColumnId>> = {
  us_value_small: 'pe',
  sg_under_radar: 'traded',
};

const PREPARING = 'Discover lists are being prepared. Check back in a few minutes.';

export default function DiscoverPage() {
  useDocumentTitle('Discover');
  const discover = useDiscover();
  const symbols = useWatchlistSymbols();
  const { toggle, isPending } = useWatchlistToggle();
  // One namespaced sort and country filter for the whole page, kept in the URL.
  const table = useTableState({ namespace: 'discover', columns: 'discover' });
  const heading = useRef<HTMLHeadingElement>(null);
  const allRows = useMemo(() => discover.data?.lists.flatMap((l) => l.rows) ?? [], [discover.data]);

  return (
    <Box>
      <Typography variant="h1" ref={heading} tabIndex={-1} sx={{ mb: 1, outline: 'none' }}>
        Discover
      </Typography>
      <Typography sx={{ color: 'ink2', maxWidth: 640, mb: 1 }}>
        Lesser-known US and Singapore stocks, picked by{' '}
        <Term id="discover_lists">simple rules</Term> and refreshed each night. These lists are
        filters, not recommendations.
      </Typography>

      <QueryRegion
        query={discover}
        skeleton={<StockTableSkeleton label="Loading discover lists…" />}
        errorTitle="We couldn’t load the discover lists"
      >
        {(data) => {
          if (data.lists.length === 0) {
            return (
              <Typography sx={{ color: 'ink2', mt: 4, maxWidth: 480 }}>
                {data.data_status.reason ?? PREPARING}
              </Typography>
            );
          }
          // Set only when the chosen country leaves every list empty.
          const emptyCountry =
            table.country != null && filterRows(allRows, table.country).length === 0
              ? table.country
              : null;
          const inWatchlist = new Set(symbols.data ?? []);
          return (
            <>
              {data.updated_at && (
                <Typography variant="body2" sx={{ color: 'ink3' }}>
                  Updated {formatRelative(data.updated_at)}
                </Typography>
              )}
              <DataStatusLine statuses={[data.data_status]} />
              <Box
                sx={{
                  mt: 3,
                  display: 'flex',
                  flexWrap: 'wrap',
                  alignItems: 'flex-end',
                  columnGap: 2,
                }}
              >
                <TableControls rows={allRows} state={table} />
                {table.sort && (
                  <Link
                    component="button"
                    type="button"
                    variant="body2"
                    onClick={() => {
                      table.setSort(null);
                      // The button disappears on reset, so hand focus to the page heading.
                      heading.current?.focus();
                    }}
                    sx={{ mb: 2, py: 1, color: 'ink' }}
                  >
                    Reset to list order
                  </Link>
                )}
              </Box>
              {emptyCountry && (
                <NoStocksFromCountry
                  country={emptyCountry}
                  onShowAll={() => {
                    table.setCountry(null);
                  }}
                />
              )}
              {data.lists.map((list) => {
                const columns = discoverColumns(LIST_COLUMNS[list.id]);
                const sort = effectiveSort(table.sort, columns);
                return (
                  <Box
                    component="section"
                    key={list.id}
                    sx={{ mt: 6, '&:first-of-type': { mt: 3 } }}
                  >
                    <Typography variant="h2" component="h2">
                      {list.title}
                    </Typography>
                    <Typography sx={{ color: 'ink2', mb: 0.5 }}>{list.description}</Typography>
                    <Typography
                      variant="body2"
                      sx={{
                        color: 'ink3',
                        display: 'flex',
                        alignItems: 'center',
                        gap: 0.75,
                        mb: 1,
                      }}
                    >
                      <SortIcon fontSize="inherit" aria-hidden />
                      <span>
                        {sort
                          ? `Sorted by ${sortPhrase(sort.key)}, ${sort.dir === 'asc' ? 'ascending' : 'descending'}.`
                          : `Ordered by: ${list.order_label}`}
                      </span>
                    </Typography>
                    <DataStatusLine statuses={[list.status]} />
                    {list.rows.length === 0 ? (
                      list.status.state === 'ok' && (
                        <Typography sx={{ color: 'ink2', mt: 1.5 }}>
                          Nothing matches this list right now.
                        </Typography>
                      )
                    ) : (
                      <Box sx={{ mt: 1.5 }}>
                        {table.country &&
                          emptyCountry === null &&
                          filterRows(list.rows, table.country).length === 0 && (
                            <Typography variant="body2" sx={{ color: 'ink3' }}>
                              None from {table.country} in this list.
                            </Typography>
                          )}
                        <StockTable
                          rows={list.rows}
                          columns={columns}
                          ariaLabel={list.title}
                          state={table}
                          quietWhenEmpty
                          actionLabel="Watchlist"
                          renderAction={(row) => (
                            <WatchStar
                              symbol={row.symbol}
                              inList={inWatchlist.has(row.symbol)}
                              disabled={symbols.isPending || isPending(row.symbol)}
                              onToggle={toggle}
                            />
                          )}
                        />
                      </Box>
                    )}
                  </Box>
                );
              })}
            </>
          );
        }}
      </QueryRegion>
    </Box>
  );
}
