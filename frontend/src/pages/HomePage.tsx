import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Typography from '@mui/material/Typography';
import { QueryRegion } from '../components/QueryRegion';
import { StockTable, StockTableSkeleton } from '../components/StockTable/StockTable';
import { TableControls } from '../components/StockTable/TableControls';
import { useTableState } from '../components/StockTable/useTableState';
import { focusSearch } from '../features/search/focusSearch';
import { RemoveButton } from '../features/watchlist/RemoveButton';
import { useWatchlistOverview } from '../features/watchlist/useWatchlist';
import { useWatchlistToggle } from '../features/watchlist/useWatchlistToggle';
import { useDocumentTitle } from '../hooks';

export default function HomePage() {
  useDocumentTitle('Watchlist');
  const overview = useWatchlistOverview();
  const { toggle } = useWatchlistToggle();
  const table = useTableState({ columns: 'watchlist' });
  const count = overview.data?.length ?? 0;

  return (
    <Box>
      <Box sx={{ display: 'flex', alignItems: 'baseline', gap: 1.5, mb: 3 }}>
        <Typography variant="h1">Watchlist</Typography>
        {count > 0 && (
          <Typography variant="body2" sx={{ color: 'ink3' }}>
            {count}
          </Typography>
        )}
      </Box>

      <QueryRegion
        query={overview}
        skeleton={<StockTableSkeleton label="Loading watchlist…" />}
        errorTitle="We couldn’t load your watchlist"
      >
        {(rows) =>
          rows.length === 0 ? (
            <Box sx={{ mt: 6, maxWidth: 480 }}>
              <Typography sx={{ mb: 3 }}>
                Your watchlist is empty. Search for a stock to add it.
              </Typography>
              <Button variant="contained" onClick={focusSearch}>
                Search for a stock
              </Button>
            </Box>
          ) : (
            <>
              <TableControls rows={rows} state={table} />
              <StockTable
                rows={rows}
                ariaLabel="Watchlist"
                state={table}
                actionLabel="Remove"
                renderAction={(row) => (
                  <RemoveButton
                    symbol={row.symbol}
                    onRemove={(symbol) => {
                      toggle(symbol, false);
                    }}
                  />
                )}
              />
            </>
          )
        }
      </QueryRegion>
    </Box>
  );
}
