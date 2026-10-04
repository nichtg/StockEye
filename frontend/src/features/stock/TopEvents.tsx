import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Link from '@mui/material/Link';
import ToggleButton from '@mui/material/ToggleButton';
import ToggleButtonGroup from '@mui/material/ToggleButtonGroup';
import Typography from '@mui/material/Typography';
import { useState } from 'react';
import type { Theme } from '@mui/material/styles';
import { radius } from '../../theme/tokens';
import type { TopEventOut } from '../../api/types';
import { Direction } from '../../components/Direction';
import { SectionTitle } from '../../components/SectionTitle';
import { Term } from '../../components/Term';
import type { Exchange } from '../../lib/exchange';
import { formatDate, moveText } from '../../lib/format';

const TOP_SHOWN = 5;

type Order = 'newest' | 'biggest';

/** Same look as the Technical/Macro tabs: a grey track, with the chosen option raised in white. */
const SEGMENTED_SX = {
  bgcolor: 'raised',
  borderRadius: radius.sm,
  p: 0.5,
  gap: 0.5,
  '& .MuiToggleButton-root': {
    border: 0,
    borderRadius: '6px !important',
    px: 2,
    py: 0.5,
    color: 'ink2',
    fontWeight: 500,
    textTransform: 'none',
    '&:not(:first-of-type)': { ml: 0, borderLeft: 0 },
    '&:hover': { color: 'ink', bgcolor: 'transparent' },
    '&.Mui-selected, &.Mui-selected:hover': {
      color: 'ink',
      bgcolor: 'bg',
      boxShadow: (theme: Theme) => `inset 0 0 0 1px ${theme.palette.line}`,
    },
  },
} as const;

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
      <Typography variant="body2" sx={{ color: 'ink3' }}>
        {formatDate(e.date, exchange)}
      </Typography>
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
          sx={SEGMENTED_SX}
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
