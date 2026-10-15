import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Link from '@mui/material/Link';
import Skeleton from '@mui/material/Skeleton';
import Typography from '@mui/material/Typography';
import { useEffect, useId, useMemo, useRef } from 'react';
import { userMessage } from '../../api/errors';
import type { NewsArticle, NewsProgress } from '../../api/types';
import { ErrorState } from '../../components/ErrorState';
import { Term } from '../../components/Term';
import { visuallyHidden } from '../../lib/a11y';
import type { Exchange } from '../../lib/exchange';
import { exchangeDay, formatClock, formatDate } from '../../lib/format';
import { DataStatusLine } from './StockHeader';
import { useNewsArticles } from './useStockData';

const SENTIMENT_LABEL: Record<NewsArticle['sentiment_label'], string> = {
  positive: 'Positive',
  negative: 'Negative',
  neutral: 'Neutral',
  not_scored: 'Not scored yet',
};

interface Day {
  day: string;
  rows: { article: NewsArticle; key: string }[];
}

/** Groups newest-first articles by exchange-local day; keys stay unique even for a repeated URL. */
function groupByDay(articles: NewsArticle[], exchange: Exchange): Day[] {
  const days: Day[] = [];
  articles.forEach((article, index) => {
    const day = exchangeDay(article.published_at, exchange);
    let group = days[days.length - 1];
    if (group?.day !== day) {
      group = { day, rows: [] };
      days.push(group);
    }
    group.rows.push({ article, key: `${article.published_at}|${article.url}|${String(index)}` });
  });
  return days;
}

function SentimentBadge({ label }: { label: NewsArticle['sentiment_label'] }) {
  return (
    <Chip
      label={SENTIMENT_LABEL[label]}
      size="small"
      variant="outlined"
      sx={{
        height: 20,
        flexShrink: 0,
        color: label === 'not_scored' ? 'ink3' : 'ink2',
        borderColor: 'ink3',
        fontWeight: label === 'neutral' || label === 'not_scored' ? 400 : 500,
      }}
    />
  );
}

function ArticleRow({ article, exchange }: { article: NewsArticle; exchange: Exchange }) {
  return (
    <Box
      component="li"
      sx={{
        display: 'flex',
        flexDirection: { xs: 'column', sm: 'row' },
        alignItems: { sm: 'flex-start' },
        justifyContent: 'space-between',
        gap: { xs: 0.75, sm: 2 },
        py: 1.5,
        borderBottom: 1,
        borderColor: 'line',
      }}
    >
      <Box sx={{ minWidth: 0 }}>
        <Link
          href={article.url}
          target="_blank"
          rel="noopener noreferrer"
          sx={{ overflowWrap: 'anywhere' }}
        >
          {article.title}
        </Link>
        <Typography variant="body2" sx={{ color: 'ink3' }}>
          {article.source}{' '}
          <Box component="span" sx={{ ml: 1 }}>
            {formatClock(article.published_at, exchange)}
          </Box>
        </Typography>
      </Box>
      <SentimentBadge label={article.sentiment_label} />
    </Box>
  );
}

function Collecting({ progress }: { progress: NewsProgress | undefined }) {
  if (!progress?.in_progress) return null;
  return (
    <Typography variant="body2" role="status" sx={{ color: 'ink2', mb: 2 }}>
      Still collecting older news: {progress.months_done} of {progress.months_total} months.
    </Typography>
  );
}

const skeleton = (
  <Box role="status" aria-label="Loading news…">
    <Skeleton width={160} height={28} />
    {[0, 1, 2, 3].map((i) => (
      <Box key={i} sx={{ py: 1.5 }}>
        <Skeleton variant="text" width="85%" />
        <Skeleton variant="text" width={140} />
      </Box>
    ))}
  </Box>
);

const MAX_AUTO_FETCHES = 3;

interface Props {
  symbol: string;
  name: string | undefined;
  exchange: Exchange;
  /** Live collection progress from the stock page's poller. */
  news: NewsProgress | undefined;
}

export function NewsTab({ symbol, name, exchange, news }: Props) {
  const query = useNewsArticles(symbol);
  const headingId = useId();
  const pages = query.data?.pages;
  const articles = useMemo(() => pages?.flatMap((p) => p.articles) ?? [], [pages]);
  const days = useMemo(() => groupByDay(articles, exchange), [articles, exchange]);

  // A page may be short or even empty while a cursor remains (the server filters after paging),
  // so keep going a few times before handing the choice to the user.
  const autoFetches = useRef(0);
  const last = pages?.[pages.length - 1];
  const emptyTail = !!last && last.articles.length === 0;
  const { hasNextPage, isFetchingNextPage, isFetchNextPageError, fetchNextPage } = query;
  useEffect(() => {
    if (!emptyTail) {
      autoFetches.current = 0;
      return;
    }
    if (!hasNextPage || isFetchingNextPage || isFetchNextPageError) return;
    if (autoFetches.current >= MAX_AUTO_FETCHES) return;
    autoFetches.current += 1;
    void fetchNextPage();
  }, [emptyTail, hasNextPage, isFetchingNextPage, isFetchNextPageError, fetchNextPage, pages]);

  if (query.isError && !pages) {
    return (
      <ErrorState
        title="We couldn’t load the news"
        message={userMessage(query.error)}
        onRetry={() => void query.refetch()}
      />
    );
  }
  if (!pages) return skeleton;

  return (
    <Box>
      <Typography sx={{ color: 'ink2', mb: 2, maxWidth: 720 }}>
        News about {name ?? symbol} from the past 6 months, newest first. Headlines that only report
        a price move are left out.{' '}
        <Term id="news_sentiment" label="a sentiment label">
          How the labels work
        </Term>
      </Typography>
      <Typography id={headingId} variant="h2" component="h2" sx={visuallyHidden}>
        Articles
      </Typography>
      <Collecting progress={news} />
      <DataStatusLine statuses={[pages[0]?.status]} />

      {articles.length === 0 && !query.hasNextPage ? (
        <Typography>No news found for the past 6 months yet.</Typography>
      ) : (
        <>
          {days.map((d) => (
            <Box key={d.day} component="section" aria-labelledby={`${headingId}-${d.day}`}>
              <Typography
                id={`${headingId}-${d.day}`}
                variant="h3"
                component="h3"
                sx={{ mt: 3, mb: 0.5, fontSize: '0.9375rem' }}
              >
                {formatDate(d.day, exchange, {
                  weekday: 'short',
                  day: 'numeric',
                  month: 'short',
                  year: 'numeric',
                })}
              </Typography>
              <Box
                component="ul"
                sx={{ listStyle: 'none', m: 0, p: 0, borderTop: 1, borderColor: 'line' }}
              >
                {d.rows.map((r) => (
                  <ArticleRow key={r.key} article={r.article} exchange={exchange} />
                ))}
              </Box>
            </Box>
          ))}
          {query.isFetchNextPageError && (
            <Typography variant="body2" role="status" sx={{ color: 'ink2', mt: 2 }}>
              Couldn’t load more news. {userMessage(query.error)}
            </Typography>
          )}
          {query.hasNextPage && (
            <Button
              variant="outlined"
              sx={{ mt: 3 }}
              disabled={query.isFetchingNextPage}
              onClick={() => void query.fetchNextPage()}
            >
              {query.isFetchingNextPage ? 'Loading…' : 'Load more'}
            </Button>
          )}
        </>
      )}
    </Box>
  );
}
