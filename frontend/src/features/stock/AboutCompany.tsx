import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Link from '@mui/material/Link';
import Skeleton from '@mui/material/Skeleton';
import Typography from '@mui/material/Typography';
import { useId, useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import type { Profile } from '../../api/types';
import { SectionTitle } from '../../components/SectionTitle';
import { Term } from '../../components/Term';
import type { Exchange } from '../../lib/exchange';
import {
  formatCompactCurrency,
  formatCount,
  formatNumber,
  formatPriceRange,
  formatVolume,
  formatYield,
} from '../../lib/format';
import { DataStatusLine } from './StockHeader';
import { useProfile } from './useStockData';

interface Fact {
  key: string;
  label: ReactNode;
  value: ReactNode;
}

/** Only an http(s) address becomes a link; anything else (javascript:, data:) is dropped. */
function safeWebsite(url: string | null | undefined): { href: string; host: string } | null {
  if (!url) return null;
  try {
    const parsed = new URL(url);
    if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') return null;
    return { href: parsed.href, host: parsed.hostname.replace(/^www\./, '') };
  } catch {
    return null;
  }
}

function factsOf(profile: Profile, currency: string, exchange: Exchange): Fact[] {
  const facts: Fact[] = [];
  const add = (key: string, label: ReactNode, value: ReactNode | null) => {
    if (value !== null) facts.push({ key, label, value });
  };
  const cur = profile.currency ?? currency;
  add(
    'cap',
    <Term id="market_cap">Market cap</Term>,
    profile.market_cap == null ? null : formatCompactCurrency(profile.market_cap, cur, exchange),
  );
  add(
    'pe',
    <Term id="pe_ratio">P/E ratio</Term>,
    profile.pe_ratio == null ? null : formatNumber(profile.pe_ratio, exchange, { digits: 1 }),
  );
  add(
    'yield',
    <Term id="dividend_yield">Dividend yield</Term>,
    profile.dividend_yield == null ? null : formatYield(profile.dividend_yield),
  );
  add(
    'range',
    <Term id="week52_range">52-week range</Term>,
    formatPriceRange(profile.week52_low, profile.week52_high, cur, exchange),
  );
  add(
    'volume',
    'Average volume',
    profile.avg_volume == null ? null : formatVolume(profile.avg_volume, exchange),
  );
  add(
    'employees',
    'Employees',
    profile.employees == null ? null : formatCount(profile.employees, exchange),
  );
  const site = safeWebsite(profile.website);
  add(
    'website',
    'Website',
    site && (
      <Link href={site.href} target="_blank" rel="noopener noreferrer">
        {site.host}
      </Link>
    ),
  );
  return facts;
}

const CLAMP_LINES = 4;

/** Body text clamped to 4 lines, with a toggle that only exists when the text is longer. */
function Description({ text }: { text: string }) {
  const id = useId();
  const ref = useRef<HTMLParagraphElement>(null);
  const [expanded, setExpanded] = useState(false);
  const [overflows, setOverflows] = useState(false);

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const measure = () => {
      // Measured only while clamped: once expanded, scrollHeight equals clientHeight.
      if (!expanded) setOverflows(el.scrollHeight > el.clientHeight + 1);
    };
    measure();
    // The width, and so the line count, changes with the layout, not only the window.
    if (typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => {
      observer.disconnect();
    };
  }, [text, expanded]);

  return (
    <Box sx={{ maxWidth: 720 }}>
      <Typography
        ref={ref}
        id={id}
        sx={{
          color: 'ink2',
          ...(!expanded && {
            display: '-webkit-box',
            WebkitBoxOrient: 'vertical',
            WebkitLineClamp: CLAMP_LINES,
            overflow: 'hidden',
          }),
        }}
      >
        {text}
      </Typography>
      {(overflows || expanded) && (
        <Button
          variant="text"
          size="small"
          aria-expanded={expanded}
          aria-controls={id}
          sx={{ mt: 0.5, ml: -1 }}
          onClick={() => {
            setExpanded((v) => !v);
          }}
        >
          {expanded ? 'Show less' : 'Show more'}
        </Button>
      )}
    </Box>
  );
}

const skeleton = (
  <Box role="status" aria-label="Loading company details…">
    <Skeleton width={220} height={28} />
    <Skeleton variant="text" sx={{ maxWidth: 720 }} />
    <Skeleton variant="text" sx={{ maxWidth: 720 }} />
    <Skeleton variant="text" width="60%" sx={{ maxWidth: 480 }} />
  </Box>
);

interface Props {
  symbol: string;
  name: string | undefined;
  exchange: Exchange;
  /** The stock's trading currency, used when the profile does not name one. */
  currency: string;
}

/** "About <company>": description and key facts, below the tabs on every tab. */
export function AboutCompany({ symbol, name, exchange, currency }: Props) {
  const headingId = useId();
  const query = useProfile(symbol);
  const profile = query.data;

  if (!profile) {
    if (query.isError) {
      return (
        <Typography variant="body2" role="status" sx={{ color: 'ink2' }}>
          Company details are unavailable right now.
        </Typography>
      );
    }
    return skeleton;
  }

  const description = profile.description?.trim() ?? '';
  const facts = factsOf(profile, currency, exchange);
  if (!description && facts.length === 0) {
    // Nothing to show; a status problem is still worth one quiet line.
    return <DataStatusLine statuses={[profile.data_status]} />;
  }

  return (
    <section aria-labelledby={headingId}>
      <SectionTitle id={headingId}>About {name ?? symbol}</SectionTitle>
      {description && <Description text={description} />}
      {facts.length > 0 && (
        <Box
          component="dl"
          sx={{
            m: 0,
            mt: description ? 3 : 0,
            display: 'grid',
            gridTemplateColumns: { xs: 'minmax(0, 1fr)', md: 'repeat(2, minmax(0, 1fr))' },
            columnGap: 6,
            maxWidth: 720,
          }}
        >
          {facts.map((f) => (
            <Box
              key={f.key}
              sx={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'baseline',
                gap: 2,
                py: 1,
                borderBottom: 1,
                borderColor: 'line',
              }}
            >
              <Typography component="dt" variant="body2" sx={{ color: 'ink3' }}>
                {f.label}
              </Typography>
              <Typography
                component="dd"
                sx={{ m: 0, textAlign: 'right', color: 'ink', overflowWrap: 'anywhere' }}
              >
                {f.value}
              </Typography>
            </Box>
          ))}
        </Box>
      )}
      <DataStatusLine statuses={[profile.data_status]} />
    </section>
  );
}
