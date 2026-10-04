import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Link from '@mui/material/Link';
import ToggleButton from '@mui/material/ToggleButton';
import ToggleButtonGroup from '@mui/material/ToggleButtonGroup';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import type { Theme } from '@mui/material/styles';
import { useState } from 'react';
import type { TopEventOut } from '../../api/types';
import { Direction } from '../../components/Direction';
import { SectionTitle } from '../../components/SectionTitle';
import { Term } from '../../components/Term';
import type { Exchange } from '../../lib/exchange';
import { formatDate, moveText } from '../../lib/format';
import { segmentedStyles } from '../../theme/segmented';

const TOP_SHOWN = 5;
const EARNINGS_TAG_HELP =
  'Within a day of an earnings release, so the move may reflect the results rather than the news.';

type Order = 'newest' | 'biggest';

/** The Technical/Macro tabs' segmented look, applied to this group's buttons. */
const segmentedSx = (theme: Theme) => {
  const seg = segmentedStyles(theme.palette);
  return {
    ...seg.track,
    display: 'flex',
    gap: 0.5,
    '& .MuiToggleButton-root': {
      ...seg.item,
      border: 0,
      // Grouped buttons carry their own corner and divider rules; the track replaces them.
      borderRadius: '6px !important',
      '&:not(:first-of-type)': { ml: 0, borderLeft: 0 },
      '&.Mui-selected, &.Mui-selected:hover': seg.selected,
    },
  };
};

/** The same events, re-ordered; which events appear is decided by the backend, by impact. */
function ordered(events: TopEventOut[], order: Order): TopEventOut[] {
  const sorted = [...events];
  if (order === 'newest') return sorted.sort((a, b) => b.date.localeCompare(a.date));
  return sorted.sort((a, b) => Math.abs(b.car_0_1) - Math.abs(a.car_0_1));
}

function EventRow({ event: e, exchange }: { event: TopEventOut; exchange: Exchange }) {
  return (
    <Box
      component="li"
      sx={{
        display: 'grid',
        gridTemplateColumns: { xs: '1fr', sm: '110px 1fr 210px' },
        columnGap: 2,
        rowGap: 0.5,
        py: 1.5,
        borderBottom: 1,
        borderColor: 'line',
      }}
    >
      <Box>
        <Typography variant="body2" sx={{ color: 'ink3' }}>
          {formatDate(e.date, exchange)}
        </Typography>
        {e.near_earnings && (
          <Tooltip title={EARNINGS_TAG_HELP} describeChild>
            <Chip
              label="Earnings"
              size="small"
              variant="outlined"
              tabIndex={0}
              sx={{ mt: 0.5, height: 20, color: 'ink2', borderColor: 'ink3' }}
            />
          </Tooltip>
        )}
      </Box>
      <Box sx={{ minWidth: 0 }}>
        {e.headlines.length === 0 && (
          <Typography variant="body2" sx={{ color: 'ink3' }}>
            No headlines saved for this day.
          </Typography>
        )}
        {e.headlines.map((h) => (
          <Typography key={h.url} sx={{ mb: 0.5 }}>
            <Link href={h.url} target="_blank" rel="noopener noreferrer">
              {h.title}
            </Link>
            <Typography component="span" variant="body2" sx={{ color: 'ink3', ml: 1 }}>
              {h.source}
            </Typography>
          </Typography>
        ))}
      </Box>
      <Typography component="div" sx={{ textAlign: { sm: 'right' } }}>
        <Direction value={e.car_0_1 * 100} text={moveText(e.car_0_1)} />
      </Typography>
    </Box>
  );
}

/** The days news moved the price most, newest first or biggest move first, five at a time. */
export function TopEvents({ events, exchange }: { events: TopEventOut[]; exchange: Exchange }) {
  const [all, setAll] = useState(false);
  const [order, setOrder] = useState<Order>('newest');
  const sorted = ordered(events, order);
  const shown = all ? sorted : sorted.slice(0, TOP_SHOWN);
  return (
    <section aria-label="Top news events">
      <SectionTitle>Biggest news days</SectionTitle>
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: 1,
          mb: 1,
        }}
      >
        <ToggleButtonGroup
          exclusive
          size="small"
          value={order}
          aria-label="Order of the biggest news days"
          sx={segmentedSx}
          onChange={(_e, value: Order | null) => {
            if (value) setOrder(value);
          }}
        >
          <ToggleButton value="newest">Newest</ToggleButton>
          <ToggleButton value="biggest">Biggest move</ToggleButton>
        </ToggleButtonGroup>
        <Typography
          variant="caption"
          component="span"
          sx={{ color: 'ink3', display: { xs: 'none', sm: 'inline' } }}
        >
          <Term id="market_adjusted_return">Market-adjusted move</Term> over 2 days
        </Typography>
      </Box>
      <Box component="ul" sx={{ listStyle: 'none', m: 0, p: 0, borderTop: 1, borderColor: 'line' }}>
        {shown.map((e) => (
          <EventRow key={`${e.date}-${e.headlines[0]?.url ?? ''}`} event={e} exchange={exchange} />
        ))}
      </Box>
      {events.length > TOP_SHOWN && (
        <Button
          variant="text"
          size="small"
          aria-expanded={all}
          sx={{ mt: 1.5, ml: -1 }}
          onClick={() => {
            setAll((v) => !v);
          }}
        >
          {all ? 'Show fewer' : `Show all ${String(events.length)}`}
        </Button>
      )}
    </section>
  );
}
