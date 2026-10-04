import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Link from '@mui/material/Link';
import Typography from '@mui/material/Typography';
import { useState } from 'react';
import type { TopEventOut } from '../../api/types';
import { Direction } from '../../components/Direction';
import { SectionTitle } from '../../components/SectionTitle';
import { Term } from '../../components/Term';
import type { Exchange } from '../../lib/exchange';
import { formatDate } from '../../lib/format';
import { moveText } from './macroText';

const TOP_SHOWN = 5;

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

/** The days news moved the price most, newest-relevant first, five at a time. */
export function TopEvents({ events, exchange }: { events: TopEventOut[]; exchange: Exchange }) {
  const [all, setAll] = useState(false);
  const shown = all ? events : events.slice(0, TOP_SHOWN);
  return (
    <section aria-label="Top news events">
      <SectionTitle>Biggest news days</SectionTitle>
      <Box
        sx={{
          display: { xs: 'none', sm: 'flex' },
          justifyContent: 'flex-end',
          color: 'ink3',
          mb: 0.5,
        }}
      >
        <Typography variant="caption" component="span">
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
