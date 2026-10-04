import Close from '@mui/icons-material/Close';
import Box from '@mui/material/Box';
import IconButton from '@mui/material/IconButton';
import Link from '@mui/material/Link';
import Skeleton from '@mui/material/Skeleton';
import Table from '@mui/material/Table';
import TableBody from '@mui/material/TableBody';
import TableCell from '@mui/material/TableCell';
import TableContainer from '@mui/material/TableContainer';
import TableHead from '@mui/material/TableHead';
import TableRow from '@mui/material/TableRow';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import useMediaQuery from '@mui/material/useMediaQuery';
import { useTheme } from '@mui/material/styles';
import { Link as RouterLink, useNavigate } from 'react-router';
import { visuallyHidden } from '../../lib/a11y';
import type { OverviewRow } from '../../api/types';
import { Direction } from '../../components/Direction';
import { Term } from '../../components/Term';
import { formatPrice } from '../../lib/format';
import { radius } from '../../theme/tokens';
import { ExchangeTag } from '../search/ExchangeTag';
import { OutlookCell } from './Outlook';
import { Sparkline } from './Sparkline';

interface Props {
  rows: OverviewRow[];
  onRemove: (symbol: string) => void;
}

const UNAVAILABLE = 'Data unavailable';

function isUnavailable(row: OverviewRow): boolean {
  return row.status === 'unavailable' || row.last_price == null;
}

function RemoveButton({ symbol, onRemove }: { symbol: string; onRemove: Props['onRemove'] }) {
  return (
    <IconButton
      size="small"
      aria-label={`Remove ${symbol} from watchlist`}
      onClick={(e) => {
        e.stopPropagation();
        onRemove(symbol);
      }}
      sx={{ color: 'ink3', '&:hover': { color: 'ink' } }}
    >
      <Close fontSize="small" />
    </IconButton>
  );
}

function SymbolLink({ row }: { row: OverviewRow }) {
  return (
    <Box sx={{ minWidth: 0 }}>
      <Link
        component={RouterLink}
        to={`/stock/${encodeURIComponent(row.symbol)}`}
        underline="none"
        sx={{ fontWeight: 600, color: 'ink', '&:hover': { textDecoration: 'underline' } }}
      >
        {row.symbol}
      </Link>
      {row.name && (
        <Typography variant="body2" noWrap sx={{ color: 'ink3', maxWidth: 260 }}>
          {row.name}
        </Typography>
      )}
    </Box>
  );
}

function StaleNote({ row }: { row: OverviewRow }) {
  if (row.status === 'ok' || row.status === 'unavailable') return null;
  return (
    <Tooltip title={row.status_reason ?? 'This data may be out of date.'}>
      <Typography
        variant="caption"
        tabIndex={0}
        sx={{ display: 'block', color: 'ink3', cursor: 'help' }}
      >
        {row.status === 'stale' ? 'Delayed' : 'Partial data'}
      </Typography>
    </Tooltip>
  );
}

function UnavailableText({ row }: { row: OverviewRow }) {
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

const numCell = { textAlign: 'right', whiteSpace: 'nowrap' } as const;

function DesktopTable({ rows, onRemove }: Props) {
  const navigate = useNavigate();
  return (
    <TableContainer sx={{ border: 1, borderColor: 'line', borderRadius: radius.lg }}>
      <Table aria-label="Watchlist">
        <TableHead>
          <TableRow>
            <TableCell>Symbol</TableCell>
            <TableCell>Exchange</TableCell>
            <TableCell sx={numCell}>Last</TableCell>
            <TableCell sx={numCell}>1W change</TableCell>
            <TableCell>1W trend</TableCell>
            <TableCell>
              <Term id="outlook">Outlook</Term>
            </TableCell>
            <TableCell sx={{ width: 48 }}>
              <Box component="span" sx={visuallyHidden}>
                Remove
              </Box>
            </TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.map((row) => {
            const unavailable = isUnavailable(row);
            return (
              <TableRow
                key={row.symbol}
                hover
                onClick={(e) => {
                  // The link is the keyboard and screen-reader target; this is the mouse shortcut.
                  if (e.target instanceof Element && e.target.closest('a,button')) return;
                  void navigate(`/stock/${encodeURIComponent(row.symbol)}`);
                }}
                sx={{ cursor: 'pointer', '&:last-child td': { borderBottom: 0 } }}
              >
                <TableCell>
                  <SymbolLink row={row} />
                </TableCell>
                {unavailable ? (
                  <TableCell colSpan={5}>
                    <UnavailableText row={row} />
                  </TableCell>
                ) : (
                  <>
                    <TableCell>
                      {row.exchange ? <ExchangeTag exchange={row.exchange} /> : '–'}
                    </TableCell>
                    <TableCell sx={numCell}>
                      <Box sx={{ color: 'ink', fontWeight: 500 }}>
                        {formatPrice(row.last_price, row.currency, row.exchange)}
                      </Box>
                      <StaleNote row={row} />
                    </TableCell>
                    <TableCell sx={numCell}>
                      <Direction value={row.change_1w_pct} />
                    </TableCell>
                    <TableCell>
                      <Sparkline values={row.sparkline} />
                    </TableCell>
                    <TableCell>
                      <OutlookCell lean={row.lean} />
                    </TableCell>
                  </>
                )}
                <TableCell sx={{ textAlign: 'right' }}>
                  <RemoveButton symbol={row.symbol} onRemove={onRemove} />
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </TableContainer>
  );
}

function MobileList({ rows, onRemove }: Props) {
  return (
    <Box
      component="ul"
      aria-label="Watchlist"
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
              <SymbolLink row={row} />
            </Box>
            {unavailable ? (
              <UnavailableText row={row} />
            ) : (
              <>
                <Box sx={{ textAlign: 'right' }}>
                  <Box sx={{ color: 'ink', fontWeight: 500, fontSize: '0.9375rem' }}>
                    {formatPrice(row.last_price, row.currency, row.exchange)}
                  </Box>
                  <Typography variant="body2" component="div">
                    <Direction value={row.change_1w_pct} />
                  </Typography>
                </Box>
                <Sparkline values={row.sparkline} width={64} />
              </>
            )}
            <RemoveButton symbol={row.symbol} onRemove={onRemove} />
          </Box>
        );
      })}
    </Box>
  );
}

export function WatchlistTable(props: Props) {
  const theme = useTheme();
  const compact = useMediaQuery(theme.breakpoints.down('sm'));
  return compact ? <MobileList {...props} /> : <DesktopTable {...props} />;
}

export function WatchlistSkeleton() {
  return (
    <Box aria-busy="true" role="status" aria-label="Loading watchlist…">
      {Array.from({ length: 5 }, (_, i) => (
        <Skeleton key={i} variant="rounded" height={56} sx={{ mb: 1, borderRadius: radius.sm }} />
      ))}
    </Box>
  );
}
