import Box from '@mui/material/Box';
import Skeleton from '@mui/material/Skeleton';
import Typography from '@mui/material/Typography';
import type { TechnicalReport } from '../../api/types';
import { QueryRegion } from '../../components/QueryRegion';
import { SectionTitle } from '../../components/SectionTitle';
import { Term } from '../../components/Term';
import { exchangeCurrency, type Exchange } from '../../lib/exchange';
import { formatPrice } from '../../lib/format';
import { radius } from '../../theme/tokens';
import { RecentPatterns } from './RecentPatterns';
import { ScoreBar } from './ScoreBar';
import { SignalList } from './SignalList';
import { LEAN_WORD } from './technicalText';
import { useTechnical } from './useStockData';

function Report({ report, exchange }: { report: TechnicalReport; exchange: Exchange }) {
  const { outlook } = report;
  const range = outlook.expected_range;
  const money = (v: number) => formatPrice(v, exchangeCurrency(exchange), exchange);

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <section aria-label="Outlook">
        <Typography sx={{ fontSize: '1.0625rem', color: 'ink' }}>
          <Term id="outlook">Short-term lean:</Term>{' '}
          <Box component="strong" sx={{ fontWeight: 600 }}>
            {LEAN_WORD[outlook.lean]}
          </Box>
        </Typography>
        <ScoreBar score={outlook.score} lean={outlook.lean} />
        {range && (
          <Typography sx={{ mt: 2.5 }}>
            <Term id="expected_range">Typical 1-week range:</Term>{' '}
            <Box
              component="span"
              sx={{ color: 'ink', fontWeight: 500, fontVariantNumeric: 'tabular-nums' }}
            >
              {`${money(range.low)} to ${money(range.high)}`}
            </Box>
          </Typography>
        )}
      </section>

      <section aria-label="Signals">
        <SectionTitle>Signals</SectionTitle>
        <SignalList signals={outlook.signals} />
      </section>

      <section aria-label="Recent patterns">
        <SectionTitle>Recent patterns</SectionTitle>
        <RecentPatterns
          patterns={report.recent_patterns}
          latest={report.latest_pattern}
          exchange={exchange}
        />
      </section>
    </Box>
  );
}

const skeleton = (
  <Box role="status" aria-label="Loading technical outlook…">
    <Skeleton width={260} height={28} />
    <Skeleton height={16} sx={{ maxWidth: 360, mb: 3 }} />
    <Skeleton variant="rounded" height={160} sx={{ borderRadius: radius.sm }} />
  </Box>
);

export function TechnicalTab({ symbol, exchange }: { symbol: string; exchange: Exchange }) {
  const query = useTechnical(symbol);
  return (
    <QueryRegion
      query={query}
      skeleton={skeleton}
      errorTitle="We couldn’t load the technical outlook"
    >
      {(report) => <Report report={report} exchange={exchange} />}
    </QueryRegion>
  );
}
