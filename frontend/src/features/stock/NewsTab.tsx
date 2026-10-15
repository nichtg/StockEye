import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Skeleton from '@mui/material/Skeleton';
import Typography from '@mui/material/Typography';
import { useEffect, useId, useMemo, useRef } from 'react';
import { useSearchParams } from 'react-router';
import { userMessage } from '../../api/errors';
import type { NewsArticle, NewsProgress } from '../../api/types';
import { ErrorState } from '../../components/ErrorState';
import { Term } from '../../components/Term';
import { visuallyHidden } from '../../lib/a11y';
import type { Exchange } from '../../lib/exchange';
import { exchangeDay, formatDate } from '../../lib/format';
import { ArticleRow } from './news/ArticleRow';
import { MonthChips } from './news/MonthChips';
import { MonthChipsSkeleton } from './news/MonthChipsSkeleton';
import { knownMonth, monthName } from './news/months';
import { DataStatusLine } from './StockHeader';
import { useNewsArticles } from './useStockData';

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

function Collecting({ progress }: { progress: NewsProgress | undefined }) {
  if (!progress?.in_progress) return null;
  return (
    <Typography variant="body2" role="status" sx={{ color: 'ink2', mb: 2 }}>
      Still collecting older news: {progress.months_done} of {progress.months_total} months.
    </Typography>
  );
}

const listSkeleton = (
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

const pageSkeleton = (
  <>
    <MonthChipsSkeleton />
    {listSkeleton}
  </>
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
  const [params, setParams] = useSearchParams();
  // The unfiltered list stays mounted: its first page carries the chips, which must not vanish
  // while a month (whose later pages have no counts) is showing.
  const everything = useNewsArticles(symbol);
  const months = everything.data?.pages[0]?.months;
  const month = knownMonth(params.get('month'), months);
  const monthly = useNewsArticles(symbol, month, month !== undefined);
  const query = month ? monthly : everything;
  const headingId = useId();
  const pages = query.data?.pages;
  const articles = useMemo(() => pages?.flatMap((p) => p.articles) ?? [], [pages]);
  const days = useMemo(() => groupByDay(articles, exchange), [articles, exchange]);
  const hasGroups = articles.some((a) => a.similar.length > 0);

  const chooseMonth = (value: string) => {
    setParams(
      (previous) => {
        const next = new URLSearchParams(previous);
        if (value) next.set('month', value);
        else next.delete('month');
        return next;
      },
      { replace: true },
    );
  };

  // A page may be short or even empty while a cursor remains (the server filters after paging),
  // so keep going a few times before handing the choice to the user.
  const autoFetches = useRef(0);
  const last = pages?.[pages.length - 1];
  const emptyTail = !!last && last.articles.length === 0;
  const { hasNextPage, isFetching, isFetchingNextPage, isFetchNextPageError, fetchNextPage } =
    query;
  useEffect(() => {
    if (!emptyTail) {
      autoFetches.current = 0;
      return;
    }
    // A running refetch (news progress) would be cancelled by fetchNextPage: wait for it.
    if (!hasNextPage || isFetching || isFetchingNextPage || isFetchNextPageError) return;
    if (autoFetches.current >= MAX_AUTO_FETCHES) return;
    autoFetches.current += 1;
    void fetchNextPage();
  }, [
    emptyTail,
    hasNextPage,
    isFetching,
    isFetchingNextPage,
    isFetchNextPageError,
    fetchNextPage,
    pages,
  ]);

  if (everything.isError && !everything.data) {
    return (
      <ErrorState
        title="We couldn’t load the news"
        message={userMessage(everything.error)}
        onRetry={() => void everything.refetch()}
      />
    );
  }
  if (!everything.data) return pageSkeleton;

  const period = month ? monthName(month) : 'the past 6 months';

  let body;
  if (query.isError && !pages) {
    body = (
      <ErrorState
        title="We couldn’t load the news"
        message={userMessage(query.error)}
        onRetry={() => void query.refetch()}
      />
    );
  } else if (!pages) {
    body = listSkeleton;
  } else if (articles.length === 0 && !query.hasNextPage) {
    body = <Typography>No news found for {period} yet.</Typography>;
  } else {
    body = (
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
    );
  }

  return (
    <Box>
      <Typography sx={{ color: 'ink2', mb: 2, maxWidth: 720 }}>
        {month
          ? `News about ${name ?? symbol} in ${period}, newest first. `
          : `News about ${name ?? symbol} from the past 6 months, newest first. `}
        Headlines that only report a price move are left out.{' '}
        <Term id="news_sentiment" label="a sentiment label">
          How the labels work
        </Term>
        {hasGroups && (
          <>
            {' '}
            Similar headlines from the same day are grouped.{' '}
            <Term id="grouped_stories" label="grouped stories">
              How grouping works
            </Term>
          </>
        )}
      </Typography>
      {months && months.length > 0 && (
        <Box sx={{ mb: 2 }}>
          <MonthChips months={months} value={month ?? ''} onChange={chooseMonth} />
        </Box>
      )}
      <Typography id={headingId} variant="h2" component="h2" sx={visuallyHidden}>
        Articles
      </Typography>
      <Collecting progress={news} />
      <DataStatusLine statuses={[everything.data.pages[0]?.status]} />
      {body}
    </Box>
  );
}
