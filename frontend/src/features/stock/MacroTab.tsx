import CheckCircleOutline from '@mui/icons-material/CheckCircleOutline';
import InfoOutlined from '@mui/icons-material/InfoOutlined';
import Box from '@mui/material/Box';
import Chip from '@mui/material/Chip';
import LinearProgress from '@mui/material/LinearProgress';
import Skeleton from '@mui/material/Skeleton';
import Typography from '@mui/material/Typography';
import type { Ingestion, MacroResponse, NewsProgress } from '../../api/types';
import { DetailsAccordion } from '../../components/DetailsAccordion';
import { QueryRegion } from '../../components/QueryRegion';
import { SectionTitle } from '../../components/SectionTitle';
import { Term } from '../../components/Term';
import type { Exchange } from '../../lib/exchange';
import { formatRelative } from '../../lib/format';
import { radius } from '../../theme/tokens';
import { FindingList } from './FindingList';
import { NOT_ENOUGH_NEWS, regimeSentence, type Scope } from './macroText';
import { ScopeTable } from './ScopeTable';
import { TopEvents } from './TopEvents';
import { useMacro } from './useStockData';
import { WeeklySentiment } from './WeeklySentiment';

/** Quiet label saying which news days a set of findings covers. Renders nothing for no scope. */
function ScopeLabel({ scope }: { scope: Scope | null | undefined }) {
  if (!scope) return null;
  return scope === 'excluding_earnings' ? (
    <>
      Excluding days near <Term id="earnings">earnings releases</Term>
    </>
  ) : (
    <>All news days</>
  );
}

function Results({
  data,
  exchange,
  collecting,
}: {
  data: MacroResponse;
  exchange: Exchange;
  collecting: boolean;
}) {
  const report = data.report;
  if (!report) return null;
  const empty =
    report.events_total === 0 && report.top_events.length === 0 && report.timeline.length === 0;
  if (empty && !collecting) return <Typography>{NOT_ENOUGH_NEWS}</Typography>;
  const showScopes = report.secondary_findings.length > 0;

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <section aria-label="Findings">
        <Box sx={{ display: 'flex', alignItems: 'baseline', flexWrap: 'wrap', columnGap: 1.5 }}>
          <SectionTitle>What the news has done to the price</SectionTitle>
          {collecting && (
            <Chip
              variant="outlined"
              size="small"
              label={<Term id="preliminary">Preliminary</Term>}
              sx={{ alignSelf: 'center', mb: 1.5 }}
            />
          )}
        </Box>
        {report.primary_findings.length > 0 ? (
          <>
            <Typography variant="caption" component="p" sx={{ color: 'ink3', mb: 1.5 }}>
              <ScopeLabel scope={report.primary_scope} />
            </Typography>
            <FindingList findings={report.primary_findings} />
          </>
        ) : (
          <Typography>{NOT_ENOUGH_NEWS}</Typography>
        )}
      </section>

      {report.regime && (
        <section aria-label="Sentiment now">
          <SectionTitle>
            <Term id="sentiment_regime">Sentiment now</Term>
          </SectionTitle>
          <Typography sx={{ color: 'ink' }}>{regimeSentence(report.regime.label)}</Typography>
        </section>
      )}

      {report.timeline.length > 0 && (
        <section aria-label="Weekly sentiment">
          <SectionTitle>
            Weekly <Term id="sentiment">sentiment</Term>
          </SectionTitle>
          <WeeklySentiment points={report.timeline} exchange={exchange} />
        </section>
      )}

      {report.top_events.length > 0 && <TopEvents events={report.top_events} exchange={exchange} />}

      <DetailsAccordion title="Details" unmountOnExit>
        {showScopes && (
          <Box sx={{ p: 2 }}>
            <Typography variant="subtitle1" sx={{ color: 'ink', mb: 1 }}>
              <ScopeLabel scope={report.secondary_scope} />
            </Typography>
            <FindingList findings={report.secondary_findings} />
          </Box>
        )}
        <ScopeTable
          title={showScopes ? 'Excluding earnings periods' : 'All news events'}
          stats={report.stats_ex_earnings}
        />
        {showScopes && <ScopeTable title="Including earnings periods" stats={report.stats_all} />}
        <Typography variant="body2" sx={{ px: 2, pb: 2, color: 'ink2' }}>
          {report.events_total} news {report.events_total === 1 ? 'event' : 'events'} found;{' '}
          {report.events_insufficient} left out because there was too little price history around
          them.
        </Typography>
      </DetailsAccordion>
    </Box>
  );
}

function CollectionProgress({ progress }: { progress: Ingestion }) {
  return (
    <Box sx={{ mb: 4, maxWidth: 480 }} role="status">
      <Typography variant="body2" sx={{ mb: 1 }}>
        Collecting news: {progress.months_done} of {progress.months_total} months
      </Typography>
      <LinearProgress
        variant="determinate"
        value={progress.months_total ? (progress.months_done / progress.months_total) * 100 : 0}
        aria-label="News collection progress"
      />
    </Box>
  );
}

/** Replaces the progress bar once every month is in: a quiet, permanent "all done". */
function CollectionComplete({ progress }: { progress: Ingestion }) {
  const updated = progress.updated_at ? ` · updated ${formatRelative(progress.updated_at)}` : '';
  return (
    <Typography
      variant="body2"
      sx={{ display: 'flex', alignItems: 'center', gap: 0.75, color: 'ink3', mb: 3 }}
    >
      <CheckCircleOutline sx={{ fontSize: 16 }} aria-hidden="true" />
      <span>
        News complete: {progress.months_total} months{updated}
      </span>
    </Typography>
  );
}

function Content({
  data,
  exchange,
  news,
}: {
  data: MacroResponse;
  exchange: Exchange;
  news: NewsProgress | undefined;
}) {
  // The page's poller is the live source; the macro answer's own copy covers the first moment.
  const progress = news ?? data.ingestion;
  const collecting = progress.in_progress;
  const complete =
    !collecting && progress.months_total > 0 && progress.months_done >= progress.months_total;
  const newsStatus = news?.status ?? data.data_status.news;
  return (
    <Box>
      {collecting && <CollectionProgress progress={progress} />}
      {complete && <CollectionComplete progress={progress} />}
      {newsStatus.state === 'unavailable' && (
        <Typography
          role="status"
          sx={{
            display: 'flex',
            alignItems: 'flex-start',
            gap: 1,
            color: 'ink2',
            mb: 3,
            maxWidth: 640,
          }}
        >
          <InfoOutlined sx={{ fontSize: 18, mt: '3px', flexShrink: 0 }} aria-hidden="true" />
          <span>{newsStatus.reason ?? 'News sentiment is unavailable right now.'}</span>
        </Typography>
      )}
      {data.report ? (
        <Results data={data} exchange={exchange} collecting={collecting} />
      ) : (
        !collecting && <Typography>{NOT_ENOUGH_NEWS}</Typography>
      )}
    </Box>
  );
}

const skeleton = (
  <Box role="status" aria-label="Loading news analysis…">
    <Skeleton width={280} height={28} />
    <Skeleton variant="rounded" height={120} sx={{ borderRadius: radius.sm, mt: 2 }} />
  </Box>
);

interface Props {
  symbol: string;
  exchange: Exchange;
  /** Live collection progress from the stock page's poller. */
  news?: NewsProgress;
}

export function MacroTab({ symbol, exchange, news }: Props) {
  const query = useMacro(symbol);
  return (
    <QueryRegion query={query} skeleton={skeleton} errorTitle="We couldn’t load the news analysis">
      {(data) => <Content data={data} exchange={exchange} news={news} />}
    </QueryRegion>
  );
}
