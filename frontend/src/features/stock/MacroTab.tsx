import CheckCircleOutline from '@mui/icons-material/CheckCircleOutline';
import InfoOutlined from '@mui/icons-material/InfoOutlined';
import Box from '@mui/material/Box';
import Chip from '@mui/material/Chip';
import LinearProgress from '@mui/material/LinearProgress';
import Skeleton from '@mui/material/Skeleton';
import Typography from '@mui/material/Typography';
import type { Ingestion, MacroResponse, NewsProgress } from '../../api/types';
import { QueryRegion } from '../../components/QueryRegion';
import { SectionTitle } from '../../components/SectionTitle';
import { Term } from '../../components/Term';
import type { Exchange } from '../../lib/exchange';
import { formatRelative } from '../../lib/format';
import { radius } from '../../theme/tokens';
import { NOT_ENOUGH_NEWS, primaryStatsOf, regimeSentence } from './macroText';
import { BucketChart } from './macro/BucketChart';
import { hasTestedBucket } from './macro/chartScale';
import { MethodDetails } from './macro/MethodDetails';
import { VerdictList } from './macro/VerdictList';
import { TopEvents } from './TopEvents';
import { useMacro } from './useStockData';
import { WeeklySentiment } from './WeeklySentiment';

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
  const primaryStats = primaryStatsOf(report);
  // One headline state: all-insufficient answers with no tested bucket collapse to a single line.
  const tested = hasTestedBucket(primaryStats);
  const thin =
    report.verdicts.length > 0 &&
    !tested &&
    report.verdicts.every((v) => v.answer_kind === 'insufficient');
  const showAnswers = report.verdicts.length > 0 && !thin;
  const noAnswer = thin || (report.verdicts.length === 0 && report.primary_findings.length === 0);

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
              sx={{ alignSelf: 'center', mb: 1.5, '& .MuiChip-label': { overflow: 'visible' } }}
            />
          )}
        </Box>
        {report.value_statement && (
          <Typography sx={{ color: 'ink2', mb: 3, maxWidth: 720 }}>
            {report.value_statement}
          </Typography>
        )}
        {showAnswers && (
          <>
            <VerdictList verdicts={report.verdicts} />
            {tested && (
              <Box sx={{ mt: 3, maxWidth: 720 }}>
                <BucketChart stats={primaryStats} />
              </Box>
            )}
          </>
        )}
        {noAnswer && <Typography>{NOT_ENOUGH_NEWS}</Typography>}
        {(showAnswers || report.primary_findings.length > 0) && (
          <Box sx={{ mt: 3 }}>
            <MethodDetails report={report} />
          </Box>
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

      <TopEvents events={report.top_events} since={report.top_events_since} exchange={exchange} />
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
  const updated = progress.updated_at ? `, updated ${formatRelative(progress.updated_at)}` : '';
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
