import InfoOutlined from '@mui/icons-material/InfoOutlined';
import Star from '@mui/icons-material/Star';
import StarBorder from '@mui/icons-material/StarBorder';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Skeleton from '@mui/material/Skeleton';
import Typography from '@mui/material/Typography';
import useMediaQuery from '@mui/material/useMediaQuery';
import { useTheme } from '@mui/material/styles';
import type { DataStatus, StockOut } from '../../api/types';
import { Direction } from '../../components/Direction';
import { visuallyHidden } from '../../lib/a11y';
import { formatAsOf, formatPct, formatPrice, formatSigned } from '../../lib/format';
import { ExchangeTag } from '../search/ExchangeTag';
import { useWatchlistSymbols } from '../watchlist/useWatchlist';
import { useWatchlistToggle } from '../watchlist/useWatchlistToggle';

interface Props {
  symbol: string;
  stock: StockOut | undefined;
  loading: boolean;
  statuses: (DataStatus | undefined)[];
}

/** One quiet line, only when something is not fully fresh. Unavailable is the loudest it gets. */
export function DataStatusLine({ statuses }: { statuses: (DataStatus | undefined)[] }) {
  const problems = statuses.filter((s): s is DataStatus => !!s && s.state !== 'ok');
  if (problems.length === 0) return null;
  const unavailable = problems.some((s) => s.state === 'unavailable');
  const reasons = [...new Set(problems.map((s) => s.reason).filter((r): r is string => !!r))];
  const text =
    reasons.join(' ') ||
    (unavailable ? 'Some data is unavailable right now.' : 'Some data may be out of date.');
  return (
    <Typography
      variant="body2"
      role="status"
      sx={{
        display: 'flex',
        alignItems: 'flex-start',
        gap: 0.75,
        mt: 1.5,
        color: 'ink2',
      }}
    >
      <InfoOutlined sx={{ fontSize: 16, mt: '2px', flexShrink: 0 }} aria-hidden="true" />
      <span>{text}</span>
    </Typography>
  );
}

const SWAP_ON_ENGAGE = {
  '& .when-engaged': { display: 'none' },
  '&:hover .when-rest, &:focus-visible .when-rest': { display: 'none' },
  '&:hover .when-engaged, &:focus-visible .when-engaged': { display: 'inline' },
} as const;

function WatchlistToggle({ symbol }: { symbol: string }) {
  const symbols = useWatchlistSymbols();
  const { toggle, snackbar } = useWatchlistToggle();
  const theme = useTheme();
  const compact = useMediaQuery(theme.breakpoints.down('sm'));
  const inList = symbols.data?.includes(symbol) ?? false;

  return (
    <>
      <Button
        variant={inList ? 'outlined' : 'contained'}
        color="primary"
        size={compact ? 'small' : 'medium'}
        disabled={symbols.isPending}
        startIcon={inList ? <Star /> : <StarBorder />}
        onClick={() => {
          toggle(symbol, !inList);
        }}
        sx={{ flexShrink: 0, minWidth: { xs: 0, sm: 210 }, ...(inList && SWAP_ON_ENGAGE) }}
      >
        {inList ? (
          <>
            <span className="when-rest">
              In watchlist
              <Box component="span" sx={visuallyHidden}>
                , activate to remove
              </Box>
            </span>
            <span className="when-engaged">Remove from watchlist</span>
          </>
        ) : (
          'Add to watchlist'
        )}
      </Button>
      {snackbar}
    </>
  );
}

/** "+0.36 (+0.86%)": the day's move in the exchange's number format. */
function changeText(stock: StockOut): string {
  const amount = formatSigned(stock.price - stock.previous_close, 2, stock.exchange);
  if (stock.change_pct == null) return amount;
  return `${amount} (${formatPct(stock.change_pct, { signed: true, digits: 2 })})`;
}

export function StockHeader({ symbol, stock, loading, statuses }: Props) {
  return (
    <Box component="header">
      <Box
        sx={{
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'flex-start',
          justifyContent: 'space-between',
          gap: 2,
        }}
      >
        <Box sx={{ minWidth: 0 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 1.5 }}>
            <Typography variant="h1">{symbol}</Typography>
            {stock && (
              <>
                <ExchangeTag exchange={stock.exchange} />
                <ExchangeTag exchange={stock.exchange} label={stock.currency} />
              </>
            )}
          </Box>
          {stock ? (
            <Typography sx={{ color: 'ink2', mt: 0.25 }}>{stock.name}</Typography>
          ) : (
            loading && <Skeleton width={200} />
          )}
        </Box>
        <WatchlistToggle symbol={symbol} />
      </Box>

      <Box sx={{ mt: 2, minHeight: 64 }}>
        {stock ? (
          <Box sx={{ display: 'flex', flexWrap: 'wrap', alignItems: 'baseline', columnGap: 2 }}>
            <Typography
              variant="display"
              component="p"
              sx={{ fontSize: { xs: '2rem', sm: '2.5rem' } }}
            >
              {formatPrice(stock.price, stock.currency, stock.exchange)}
            </Typography>
            <Typography component="p" sx={{ fontSize: '1rem' }}>
              <Direction value={stock.change_pct} digits={2} text={changeText(stock)} />
            </Typography>
            <Typography variant="body2" sx={{ color: 'ink3' }}>
              as of {formatAsOf(stock.as_of, stock.exchange)}
            </Typography>
          </Box>
        ) : (
          loading && <Skeleton variant="text" width={240} sx={{ fontSize: '2.5rem' }} />
        )}
      </Box>
      <DataStatusLine statuses={statuses} />
    </Box>
  );
}
