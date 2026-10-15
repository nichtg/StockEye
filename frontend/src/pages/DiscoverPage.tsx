import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import { QueryRegion } from '../components/QueryRegion';
import { countryOptions } from '../components/StockTable/sortFilter';
import { StockTable, StockTableSkeleton } from '../components/StockTable/StockTable';
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

const PREPARING = 'Discover lists are being prepared. Check back in a few minutes.';

export default function DiscoverPage() {
  useDocumentTitle('Discover');
  const discover = useDiscover();
  const symbols = useWatchlistSymbols();
  const { toggle } = useWatchlistToggle();
  // One namespaced sort and country filter for the whole page, kept in the URL.
  const table = useTableState('discover');

  return (
    <Box>
      <Typography variant="h1" sx={{ mb: 1 }}>
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
          const allRows = data.lists.flatMap((list) => list.rows);
          const inWatchlist = new Set(symbols.data ?? []);
          return (
            <>
              {data.updated_at && (
                <Typography variant="body2" sx={{ color: 'ink3', mb: 3 }}>
                  Updated {formatRelative(data.updated_at)}
                </Typography>
              )}
              <TableControls
                countries={countryOptions(allRows)}
                country={table.country}
                onCountry={table.setCountry}
                sort={table.sort}
                onSort={table.setSort}
                showMarketCap
              />
              {data.lists.map((list) => (
                <Box component="section" key={list.id} sx={{ mt: 6, '&:first-of-type': { mt: 3 } }}>
                  <Typography variant="h2" component="h2">
                    {list.title}
                  </Typography>
                  <Typography sx={{ color: 'ink2', mb: 1.5 }}>{list.description}</Typography>
                  <DataStatusLine statuses={[list.status]} />
                  {list.rows.length === 0 ? (
                    list.status.state === 'ok' && (
                      <Typography sx={{ color: 'ink2', mt: 1.5 }}>
                        Nothing matches this list right now.
                      </Typography>
                    )
                  ) : (
                    <Box sx={{ mt: 1.5 }}>
                      <StockTable
                        rows={list.rows}
                        ariaLabel={list.title}
                        sort={table.sort}
                        onSort={table.toggleSort}
                        country={table.country}
                        onShowAllCountries={() => {
                          table.setCountry(null);
                        }}
                        showMarketCap
                        actionLabel="Watchlist"
                        renderAction={(row) => (
                          <WatchStar
                            symbol={row.symbol}
                            inList={inWatchlist.has(row.symbol)}
                            disabled={symbols.isPending}
                            onToggle={toggle}
                          />
                        )}
                      />
                    </Box>
                  )}
                </Box>
              ))}
            </>
          );
        }}
      </QueryRegion>
    </Box>
  );
}
